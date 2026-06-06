"""Credit wallet / ledger / hold service — core paths (DB-backed, SQLite)."""
from datetime import timedelta

import pytest
from sqlalchemy import func, select, update

from llm.usage_context import UsageAccumulator
from models.credit import CreditHold, CreditLedger, CreditWallet
from models.game import TokenUsage
from models.model_management import ModelProvider, ProviderModel
from models.user import User
from services import credit_service as cs
from utils import utcnow

GRANT = 500 * 10_000  # default signup grant in units
EST_GAME = 25 * 10_000
EST_SCRIPT = 200 * 10_000


async def _mk_user(db, _label: str = "") -> str:
    user = User(nickname="c")  # id auto-generated (valid UUID)
    db.add(user)
    await db.commit()
    return user.id


async def _mk_priced_model(db, *, name="P", model="m1", in_price=313, out_price=626):
    provider = ModelProvider(name=name, provider_type="deepseek", api_key_env_name="X")
    db.add(provider)
    await db.flush()
    db.add(
        ProviderModel(
            provider_id=provider.id,
            model_id=model,
            display_name=model,
            model_kind="text",
            input_price_cents_per_million_tokens=in_price,
            output_price_cents_per_million_tokens=out_price,
        )
    )
    await db.commit()


async def _ledger_sum(db, uid) -> int:
    return int(
        (
            await db.execute(
                select(func.coalesce(func.sum(CreditLedger.delta_units), 0)).where(
                    CreditLedger.user_id == uid
                )
            )
        ).scalar_one()
    )


async def _active_held_sum(db, uid) -> int:
    return int(
        (
            await db.execute(
                select(func.coalesce(func.sum(CreditHold.estimate_units), 0)).where(
                    CreditHold.user_id == uid, CreditHold.status == "held"
                )
            )
        ).scalar_one()
    )


async def _assert_invariants(db, uid):
    wallet = await cs.get_or_create_wallet(db, uid)
    await db.refresh(wallet)
    assert wallet.balance_units == await _ledger_sum(db, uid), "I1: balance == Σledger"
    assert wallet.held_units == await _active_held_sum(db, uid), "I2: held == Σ active holds"


# --- signup grant -----------------------------------------------------------

async def test_signup_grant_on_wallet_creation(db):
    uid = await _mk_user(db)
    wallet = await cs.get_or_create_wallet(db, uid)
    assert wallet.balance_units == GRANT
    assert wallet.held_units == 0
    rows = (await db.execute(select(CreditLedger).where(CreditLedger.user_id == uid))).scalars().all()
    assert len(rows) == 1 and rows[0].kind == "signup_grant"


async def test_signup_grant_is_once(db):
    uid = await _mk_user(db)
    await cs.get_or_create_wallet(db, uid)
    await cs.get_or_create_wallet(db, uid)
    rows = (await db.execute(select(CreditLedger).where(CreditLedger.user_id == uid))).scalars().all()
    assert len(rows) == 1


# --- reserve (L3 gate) ------------------------------------------------------

async def test_reserve_blocks_when_unaffordable(db):
    uid = await _mk_user(db)
    # 5,000,000 available; each script reservation is 2,000,000.
    h1 = await cs.reserve(db, uid, action="script")
    h2 = await cs.reserve(db, uid, action="script")
    assert h1 != h2
    wallet = await cs.get_or_create_wallet(db, uid)
    await db.refresh(wallet)
    assert wallet.held_units == 2 * EST_SCRIPT  # I2
    # Third needs 2M but only 1M is available -> blocked, held unchanged.
    with pytest.raises(cs.InsufficientCredits):
        await cs.reserve(db, uid, action="script")
    await db.refresh(wallet)
    assert wallet.held_units == 2 * EST_SCRIPT
    await _assert_invariants(db, uid)


# --- settle -----------------------------------------------------------------

async def test_settle_hold_charges_and_releases(db):
    uid = await _mk_user(db)
    await _mk_priced_model(db)
    hold_id = await cs.reserve(db, uid, action="game", ref_type="session", ref_id="s1")

    acc = UsageAccumulator()
    acc.add(provider_name="P", model_id="m1", input_tokens=1_000_000, output_tokens=1_000_000)
    charged = await cs.settle_hold(db, hold_id, acc, delivered=True)

    assert charged == 939 * 10_000  # (313 + 626) fen x1
    wallet = await cs.get_or_create_wallet(db, uid)
    await db.refresh(wallet)
    assert wallet.balance_units == GRANT - 939 * 10_000  # bounded overshoot allowed
    assert wallet.held_units == 0
    debit = (
        await db.execute(
            select(CreditLedger).where(CreditLedger.user_id == uid, CreditLedger.kind == "debit_game")
        )
    ).scalar_one()
    assert debit.delta_units == -939 * 10_000 and debit.cost_cents == 939
    await _assert_invariants(db, uid)


async def test_settle_full_failure_is_free(db):
    uid = await _mk_user(db)
    await _mk_priced_model(db)
    hold_id = await cs.reserve(db, uid, action="world", ref_type="task", ref_id="t1")

    acc = UsageAccumulator()
    acc.add(provider_name="P", model_id="m1", input_tokens=500_000, output_tokens=100_000)
    charged = await cs.settle_hold(db, hold_id, acc, delivered=False)

    assert charged == 0
    wallet = await cs.get_or_create_wallet(db, uid)
    await db.refresh(wallet)
    assert wallet.balance_units == GRANT and wallet.held_units == 0
    failed = (
        await db.execute(
            select(CreditLedger).where(CreditLedger.kind == "debit_world_gen_failed")
        )
    ).scalar_one()
    assert failed.delta_units == 0 and failed.cost_cents is not None and failed.cost_cents > 0
    await _assert_invariants(db, uid)


async def test_settle_no_pricing_is_free(db):
    uid = await _mk_user(db)
    hold_id = await cs.reserve(db, uid, action="game")
    acc = UsageAccumulator()
    acc.add(provider_name="unknown", model_id="nope", input_tokens=5000, output_tokens=5000)
    assert await cs.settle_hold(db, hold_id, acc, delivered=True) == 0
    wallet = await cs.get_or_create_wallet(db, uid)
    await db.refresh(wallet)
    assert wallet.balance_units == GRANT and wallet.held_units == 0
    await _assert_invariants(db, uid)


# --- sweep ------------------------------------------------------------------

async def test_sweep_replays_settle_failed(db):
    uid = await _mk_user(db)
    await _mk_priced_model(db)
    hold_id = await cs.reserve(db, uid, action="game")
    # Simulate a real-time settle that failed after capturing usage.
    hold = await db.get(CreditHold, hold_id)
    hold.status = "settle_failed"
    hold.usage_json = [
        {"provider_name": "P", "model_id": "m1", "input_tokens": 1_000_000,
         "output_tokens": 0, "image_count": 0, "cache_hit_tokens": 0, "cache_miss_tokens": 0}
    ]
    await db.commit()

    res = await cs.sweep_holds(db)
    assert res["replayed"] == 1
    hold = await db.get(CreditHold, hold_id)
    assert hold.status == "settled" and hold.charged_units == 313 * 10_000
    await _assert_invariants(db, uid)


async def test_sweep_orphan_forgiven(db):
    uid = await _mk_user(db)
    hold_id = await cs.reserve(db, uid, action="game")  # no token_usage, no settle
    hold = await db.get(CreditHold, hold_id)
    hold.created_at = utcnow() - timedelta(seconds=cs.CREDIT_HOLD_TTL_SECONDS + 60)
    await db.commit()

    res = await cs.sweep_holds(db)
    assert res["orphan_forgiven"] == 1
    wallet = await cs.get_or_create_wallet(db, uid)
    await db.refresh(wallet)
    assert wallet.held_units == 0 and wallet.balance_units == GRANT
    await _assert_invariants(db, uid)


async def test_sweep_orphan_charged_from_token_usage(db):
    import uuid

    uid = await _mk_user(db)
    await _mk_priced_model(db)
    sess_id = str(uuid.uuid4())
    hold_id = await cs.reserve(db, uid, action="game", ref_type="session", ref_id=sess_id)
    db.add(
        TokenUsage(
            purpose="game", provider="x", model="x",
            provider_name="P", model_id="m1", input_tokens=1_000_000, output_tokens=0,
            session_id=sess_id, cost_cents=0,
        )
    )
    hold = await db.get(CreditHold, hold_id)
    hold.created_at = utcnow() - timedelta(seconds=cs.CREDIT_HOLD_TTL_SECONDS + 60)
    await db.commit()

    res = await cs.sweep_holds(db)
    assert res["orphan_charged"] == 1
    wallet = await cs.get_or_create_wallet(db, uid)
    await db.refresh(wallet)
    assert wallet.balance_units == GRANT - 313 * 10_000 and wallet.held_units == 0
    await _assert_invariants(db, uid)


async def test_sweep_orphan_charged_only_for_its_own_window(db):
    """Regression: a leaked hold in a MULTI-turn session must be charged only
    its own turn's usage, not the whole session's cumulative token_usage.

    The orphan recovery reconstructs usage from ``token_usage``; scoping it to
    the hold's own action window ([created_at, next-hold-reserve)) prevents a
    single leaked turn from being billed every later turn that already settled.
    """
    import uuid

    uid = await _mk_user(db)
    await _mk_priced_model(db)
    sess_id = str(uuid.uuid4())
    base = utcnow() - timedelta(seconds=cs.CREDIT_HOLD_TTL_SECONDS + 600)

    # Turn 1 — settle never ran → orphaned hold; its usage written just after.
    orphan_id = await cs.reserve(db, uid, action="game", ref_type="session", ref_id=sess_id)
    orphan = await db.get(CreditHold, orphan_id)
    orphan.created_at = base
    db.add(
        TokenUsage(
            purpose="game", provider="x", model="x", provider_name="P", model_id="m1",
            input_tokens=1_000_000, output_tokens=0, session_id=sess_id, cost_cents=0,
            created_at=base + timedelta(seconds=1),
        )
    )

    # Turn 2 — a later, already-settled hold in the SAME session, with its own
    # usage. The orphan must NOT be charged for this later turn.
    later_id = await cs.reserve(db, uid, action="game", ref_type="session", ref_id=sess_id)
    later = await db.get(CreditHold, later_id)
    later.created_at = base + timedelta(seconds=30)
    later.status = "settled"
    db.add(
        TokenUsage(
            purpose="game", provider="x", model="x", provider_name="P", model_id="m1",
            input_tokens=1_000_000, output_tokens=0, session_id=sess_id, cost_cents=0,
            created_at=base + timedelta(seconds=31),
        )
    )
    await db.commit()

    res = await cs.sweep_holds(db)
    assert res["orphan_charged"] == 1
    orphan = await db.get(CreditHold, orphan_id)
    # Only turn-1's 1M tokens (313*10_000), NOT both turns' 2M (626*10_000).
    assert orphan.charged_units == 313 * 10_000


# --- reconcile --------------------------------------------------------------

async def test_reconcile_detects_and_repairs(db):
    uid = await _mk_user(db)
    await cs.get_or_create_wallet(db, uid)
    # Inject drift directly (simulating a bug / manual edit).
    await db.execute(
        update(CreditWallet)
        .where(CreditWallet.user_id == uid)
        .values(balance_units=CreditWallet.balance_units + 12_345, held_units=999)
    )
    await db.commit()

    report = await cs.reconcile(db, user_id=uid, repair=False)
    assert report["balance_drift"] == 12_345 and report["held_drift"] == 999
    assert report["repaired"] is False

    report = await cs.reconcile(db, user_id=uid, repair=True)
    assert report["repaired"] is True
    await _assert_invariants(db, uid)


# --- admin adjust -----------------------------------------------------------

async def test_admin_adjust_signed(db):
    uid = await _mk_user(db)
    await cs.get_or_create_wallet(db, uid)
    after_deduct = await cs.grant(db, uid, -100 * 10_000, kind="admin_adjust", category="adjust", note="x")
    assert after_deduct == GRANT - 100 * 10_000
    after_add = await cs.grant(db, uid, 50 * 10_000, kind="admin_adjust", category="adjust")
    assert after_add == GRANT - 100 * 10_000 + 50 * 10_000
    await _assert_invariants(db, uid)
