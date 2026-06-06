"""Credit wallet / ledger service — Phase 1 (metering + L2 gate).

* Wallet balance is the cached source of truth; the append-only ledger is
  authoritative and can reconcile it.
* Credits are cost-pegged: a debit = real cost (fen, fine precision) ×
  billing multiplier. Settlement happens at the action boundary against a
  ``UsageAccumulator`` (not the best-effort sink), so it is reliable.
* The signup grant is tied to *wallet creation* (lazy get-or-create) so it is
  issued exactly once regardless of how/where the user row was created.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import structlog
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from llm.usage_context import UsageAccumulator
from models.credit import CREDIT_UNIT_SCALE, CreditConfig, CreditHold, CreditLedger, CreditWallet
from models.game import TokenUsage
from services import notification_service as ns
from services.credit_pricing import cost_fen_to_units, usage_to_cost_fen
from services.pricing_lookup import get_pricing_for
from utils import utcnow

logger = structlog.get_logger("credit_service")

# A held reservation older than this with no settlement is an orphan (its action
# crashed mid-flight); the sweep recovers it so held_units never leaks. Generous
# margin over the longest real action (a generation task).
CREDIT_HOLD_TTL_SECONDS = 1800
# Cap on settle-replay attempts before the sweep force-resolves a hold.
CREDIT_SETTLE_MAX_ATTEMPTS = 5


class InsufficientCredits(Exception):
    """Raised by the gate when balance can't cover an action's estimate."""

    def __init__(self, balance_units: int, needed_units: int):
        self.balance_units = balance_units
        self.needed_units = needed_units
        super().__init__(f"insufficient credits: {balance_units} < {needed_units}")


@dataclass(frozen=True)
class EconomyConfig:
    billing_multiplier_milli: int
    signup_grant_units: int
    estimate_game_units: int
    estimate_world_units: int
    estimate_script_units: int
    gate_fail_mode: str = "open"


_DEFAULT_CONFIG = EconomyConfig(
    billing_multiplier_milli=1_000,
    signup_grant_units=500 * CREDIT_UNIT_SCALE,
    estimate_game_units=25 * CREDIT_UNIT_SCALE,
    estimate_world_units=70 * CREDIT_UNIT_SCALE,
    estimate_script_units=200 * CREDIT_UNIT_SCALE,
    gate_fail_mode="open",
)

# Map workshop task kind / usage purpose → (ledger kind, category, estimate attr).
_ACTION_META = {
    "game": ("debit_game", "play"),
    "world": ("debit_world_gen", "creation"),
    "script": ("debit_script_gen", "creation"),
}


async def get_config(db: AsyncSession) -> EconomyConfig:
    row = (await db.execute(select(CreditConfig).where(CreditConfig.id == 1))).scalar_one_or_none()
    if row is None:
        return _DEFAULT_CONFIG
    return EconomyConfig(
        billing_multiplier_milli=row.billing_multiplier_milli,
        signup_grant_units=row.signup_grant_units,
        estimate_game_units=row.estimate_game_units,
        estimate_world_units=row.estimate_world_units,
        estimate_script_units=row.estimate_script_units,
        gate_fail_mode=row.gate_fail_mode or "open",
    )


async def get_or_create_wallet(db: AsyncSession, user_id: str) -> CreditWallet:
    wallet = (
        await db.execute(select(CreditWallet).where(CreditWallet.user_id == user_id))
    ).scalar_one_or_none()
    if wallet is not None:
        return wallet

    config = await get_config(db)
    grant_units = config.signup_grant_units
    wallet = CreditWallet(
        user_id=user_id,
        balance_units=grant_units,
        lifetime_granted_units=grant_units,
        lifetime_spent_units=0,
    )
    db.add(wallet)
    db.add(
        CreditLedger(
            user_id=user_id,
            delta_units=grant_units,
            balance_after_units=grant_units,
            kind="signup_grant",
            category="grant",
        )
    )
    # 欢迎通知，与钱包创建同事务（race 落败方一并回滚 → 每用户恰一条）
    await ns.notify(
        db,
        user_id=user_id,
        type="signup_grant",
        title="欢迎加入 InkWild",
        body=f"已为你送上 {grant_units // CREDIT_UNIT_SCALE} 积分，开始你的第一段故事吧。",
        link="/discover",
        payload={"units": grant_units},
    )
    try:
        await db.commit()
    except IntegrityError:
        # Lost a race to create the wallet — re-read the winner.
        await db.rollback()
        wallet = (
            await db.execute(select(CreditWallet).where(CreditWallet.user_id == user_id))
        ).scalar_one()
        return wallet
    await db.refresh(wallet)
    return wallet


async def get_balance_units(db: AsyncSession, user_id: str) -> int:
    return (await get_or_create_wallet(db, user_id)).balance_units


async def reserve(
    db: AsyncSession,
    user_id: str,
    *,
    action: str,
    ref_type: str | None = None,
    ref_id: str | None = None,
) -> str:
    """L3 gate: atomically reserve the action's estimate against the wallet.

    Closes the cross-action overspend leak — a single ``UPDATE`` checks
    ``available = balance − held`` and increments ``held`` in one shot, so two
    concurrent actions can't both pass on the same balance. Returns the hold id;
    raises :class:`InsufficientCredits` if the reservation can't be made.
    """
    config = await get_config(db)
    estimate = estimate_units_for(config, action)
    await get_or_create_wallet(db, user_id)

    reserved = (
        await db.execute(
            update(CreditWallet)
            .where(
                CreditWallet.user_id == user_id,
                CreditWallet.balance_units - CreditWallet.held_units >= estimate,
            )
            .values(held_units=CreditWallet.held_units + estimate)
            .returning(CreditWallet.balance_units)
        )
    ).scalar_one_or_none()
    if reserved is None:
        await db.rollback()
        row = (
            await db.execute(
                select(CreditWallet.balance_units, CreditWallet.held_units).where(
                    CreditWallet.user_id == user_id
                )
            )
        ).first()
        available = (row[0] - row[1]) if row else 0
        raise InsufficientCredits(balance_units=available, needed_units=estimate)

    hold = CreditHold(
        user_id=user_id,
        action=action,
        ref_type=ref_type,
        ref_id=ref_id,
        estimate_units=estimate,
        status="held",
    )
    db.add(hold)
    await db.commit()
    await db.refresh(hold)
    return hold.id


def estimate_units_for(config: EconomyConfig, action: str) -> int:
    return {
        "game": config.estimate_game_units,
        "world": config.estimate_world_units,
        "script": config.estimate_script_units,
    }.get(action, 0)


async def grant(
    db: AsyncSession,
    user_id: str,
    delta_units: int,
    *,
    kind: str,
    category: str = "grant",
    note: str | None = None,
    actor_user_id: str | None = None,
) -> int:
    """Apply a signed credit change (grant or admin adjustment). Returns new balance."""
    await get_or_create_wallet(db, user_id)
    values: dict = {"balance_units": CreditWallet.balance_units + delta_units}
    if delta_units >= 0:
        values["lifetime_granted_units"] = CreditWallet.lifetime_granted_units + delta_units
    balance_after = (
        await db.execute(
            update(CreditWallet)
            .where(CreditWallet.user_id == user_id)
            .values(**values)
            .returning(CreditWallet.balance_units)
        )
    ).scalar_one()
    db.add(
        CreditLedger(
            user_id=user_id,
            delta_units=delta_units,
            balance_after_units=balance_after,
            kind=kind,
            category=category,
            note=note,
            actor_user_id=actor_user_id,
        )
    )
    await db.commit()
    return balance_after


async def _price_entries(db: AsyncSession, entries: list[dict]) -> float:
    """Sum the real (fractional-fen, cache-aware) cost of accumulated usage."""
    cost_fen = 0.0
    for entry in entries:
        pricing = await get_pricing_for(
            db, provider_name=entry.get("provider_name"), model_id=entry.get("model_id")
        )
        cost_fen += usage_to_cost_fen(
            input_tokens=entry.get("input_tokens", 0),
            output_tokens=entry.get("output_tokens", 0),
            image_count=entry.get("image_count", 0),
            pricing=pricing,
            cache_hit_tokens=entry.get("cache_hit_tokens", 0),
            cache_miss_tokens=entry.get("cache_miss_tokens", 0),
        )
    return cost_fen


async def _settle_core(
    db: AsyncSession, hold: CreditHold, entries: list[dict], *, delivered: bool
) -> int:
    """Apply settlement for a held reservation in one transaction.

    Releases the reservation; on ``delivered`` charges the real cost (one debit
    row), else charges nothing and writes a delta=0 "failed, not charged" row
    (design §5.2). Maintains invariants I1 (``balance == Σledger``) and I2
    (``held == Σ active holds``). Raises on DB failure (caller decides recovery).
    """
    config = await get_config(db)
    cost_fen = await _price_entries(db, entries)
    kind, category = _ACTION_META.get(hold.action, ("debit_other", "play"))

    if not delivered:
        balance_after = (
            await db.execute(
                update(CreditWallet)
                .where(CreditWallet.user_id == hold.user_id)
                .values(held_units=CreditWallet.held_units - hold.estimate_units)
                .returning(CreditWallet.balance_units)
            )
        ).scalar_one()
        db.add(
            CreditLedger(
                user_id=hold.user_id,
                delta_units=0,
                balance_after_units=balance_after,
                kind=f"{kind}_failed",
                category=category,
                ref_type=hold.ref_type,
                ref_id=hold.ref_id,
                cost_cents=round(cost_fen) if cost_fen > 0 else None,
            )
        )
        hold.status = "settled"
        hold.charged_units = 0
        hold.settled_at = utcnow()
        await db.commit()
        return 0

    units = cost_fen_to_units(cost_fen, billing_multiplier_milli=config.billing_multiplier_milli)
    values: dict = {"held_units": CreditWallet.held_units - hold.estimate_units}
    if units > 0:
        values["balance_units"] = CreditWallet.balance_units - units
        values["lifetime_spent_units"] = CreditWallet.lifetime_spent_units + units
    balance_after = (
        await db.execute(
            update(CreditWallet)
            .where(CreditWallet.user_id == hold.user_id)
            .values(**values)
            .returning(CreditWallet.balance_units)
        )
    ).scalar_one()
    if units > 0:
        db.add(
            CreditLedger(
                user_id=hold.user_id,
                delta_units=-units,
                balance_after_units=balance_after,
                kind=kind,
                category=category,
                ref_type=hold.ref_type,
                ref_id=hold.ref_id,
                cost_cents=round(cost_fen),
            )
        )
    hold.status = "settled"
    hold.charged_units = units
    hold.settled_at = utcnow()
    # 余额不足以再玩一回合 → 提醒（去重，避免每回合刷屏）。
    # 通知失败绝不能拖垮计费，吞掉并记日志。
    if units > 0 and balance_after < config.estimate_game_units:
        try:
            await ns.notify_low_credit_once(db, user_id=hold.user_id, balance_units=balance_after)
        except Exception:  # noqa: BLE001
            logger.warning("credit.low_credit_notify_failed", user_id=hold.user_id, exc_info=True)
    await db.commit()
    return units


async def _release_only(db: AsyncSession, hold: CreditHold) -> None:
    """Release a hold's reservation without charging (forgive / recover)."""
    await db.execute(
        update(CreditWallet)
        .where(CreditWallet.user_id == hold.user_id)
        .values(held_units=CreditWallet.held_units - hold.estimate_units)
    )
    hold.status = "settled"
    hold.charged_units = 0
    hold.settled_at = utcnow()
    await db.commit()


async def settle_hold(
    db: AsyncSession,
    hold_id: str,
    accumulator: UsageAccumulator,
    *,
    delivered: bool,
    ref_id: str | None = None,
) -> int:
    """Settle a reservation against real usage. Returns units charged.

    ``delivered=False`` (action produced nothing) → free. On DB failure the
    reservation is kept and the usage captured so the sweep can replay it; a
    failed *free* settle just releases the reservation (nothing to replay).

    ``ref_id``: late-bound session reference. The opening turn reserves before
    the session exists (``ref_id=None``); the id arrives mid-stream via
    ``session_created``. When given and the hold has no ref yet, stamp it so the
    debit ledger row carries the session link (lets the play「本局积分」抽屉
    find this turn's row).
    """
    hold = await db.get(CreditHold, hold_id)
    if hold is None or hold.status != "held":
        return 0
    if ref_id and not hold.ref_id:
        hold.ref_type = "session"
        hold.ref_id = ref_id
    try:
        return await _settle_core(db, hold, list(accumulator.entries), delivered=delivered)
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        hold = await db.get(CreditHold, hold_id)
        if hold is None or hold.status != "held":
            return 0
        if not delivered:
            try:
                await _release_only(db, hold)
            except Exception:  # noqa: BLE001
                await db.rollback()
                logger.warning("credit.settle_release_failed", hold_id=hold_id, exc_info=True)
            return 0
        hold.status = "settle_failed"
        hold.usage_json = list(accumulator.entries)
        hold.attempts = (hold.attempts or 0) + 1
        hold.last_error = str(exc)[:500]
        try:
            await db.commit()
        except Exception:  # noqa: BLE001
            await db.rollback()  # leave as 'held' → orphan sweep handles it
        logger.warning("credit.settle_failed", hold_id=hold_id, exc_info=True)
        return 0


async def _reconstruct_entries_from_usage(db: AsyncSession, hold: CreditHold) -> list[dict]:
    """Best-effort rebuild of an orphaned action's usage from ``token_usage``.

    Scoped to the hold's own action window — from its ``created_at`` up to the
    next hold's reserve time for the same ref — so a single leaked turn isn't
    billed every later turn of a multi-turn session that already settled (each
    game turn reserves its own hold against the same ``session_id``).
    """
    if not hold.ref_id:
        return []
    col = TokenUsage.task_id if hold.ref_type == "task" else TokenUsage.session_id
    next_reserve_at = (
        await db.execute(
            select(func.min(CreditHold.created_at)).where(
                CreditHold.ref_type == hold.ref_type,
                CreditHold.ref_id == hold.ref_id,
                CreditHold.created_at > hold.created_at,
            )
        )
    ).scalar_one()
    conds = [col == hold.ref_id, TokenUsage.created_at >= hold.created_at]
    if next_reserve_at is not None:
        conds.append(TokenUsage.created_at < next_reserve_at)
    rows = (
        await db.execute(
            select(
                TokenUsage.provider_name,
                TokenUsage.model_id,
                func.coalesce(func.sum(TokenUsage.input_tokens), 0),
                func.coalesce(func.sum(TokenUsage.output_tokens), 0),
                func.coalesce(func.sum(TokenUsage.image_count), 0),
                func.coalesce(func.sum(func.coalesce(TokenUsage.cache_hit_tokens, 0)), 0),
                func.coalesce(func.sum(func.coalesce(TokenUsage.cache_miss_tokens, 0)), 0),
            )
            .where(*conds)
            .group_by(TokenUsage.provider_name, TokenUsage.model_id)
        )
    ).all()
    return [
        {
            "provider_name": r[0],
            "model_id": r[1],
            "input_tokens": int(r[2] or 0),
            "output_tokens": int(r[3] or 0),
            "image_count": int(r[4] or 0),
            "cache_hit_tokens": int(r[5] or 0),
            "cache_miss_tokens": int(r[6] or 0),
        }
        for r in rows
    ]


async def sweep_holds(db: AsyncSession, *, now: datetime | None = None) -> dict:
    """Recover holds that real-time settlement couldn't finish (design §5.4).

    * ``settle_failed`` → replay captured usage; past the attempt cap, release
      so the reservation can't leak.
    * ``held`` beyond TTL → orphan (crashed action): charge reconstructed usage
      from ``token_usage`` if any, else forgive (release).
    """
    now = now or utcnow()
    cutoff = now - timedelta(seconds=CREDIT_HOLD_TTL_SECONDS)
    result = {"replayed": 0, "orphan_charged": 0, "orphan_forgiven": 0, "gave_up": 0}

    failed = (
        await db.execute(select(CreditHold).where(CreditHold.status == "settle_failed"))
    ).scalars().all()
    for hold in failed:
        hid = hold.id
        try:
            await _settle_core(db, hold, hold.usage_json or [], delivered=True)
            result["replayed"] += 1
        except Exception:  # noqa: BLE001
            await db.rollback()
            fresh = await db.get(CreditHold, hid)
            if fresh is None or fresh.status != "settle_failed":
                continue
            fresh.attempts = (fresh.attempts or 0) + 1
            gave_up = fresh.attempts >= CREDIT_SETTLE_MAX_ATTEMPTS
            await db.commit()
            if gave_up:
                doomed = await db.get(CreditHold, hid)
                if doomed is not None and doomed.status == "settle_failed":
                    await _release_only(db, doomed)
                logger.error("credit.settle_gave_up", hold_id=hid)
                result["gave_up"] += 1

    orphans = (
        await db.execute(
            select(CreditHold).where(CreditHold.status == "held", CreditHold.created_at < cutoff)
        )
    ).scalars().all()
    for hold in orphans:
        hid = hold.id
        entries = await _reconstruct_entries_from_usage(db, hold)
        if entries:
            try:
                await _settle_core(db, hold, entries, delivered=True)
                result["orphan_charged"] += 1
                continue
            except Exception:  # noqa: BLE001
                await db.rollback()
                logger.warning("credit.orphan_settle_failed", hold_id=hid, exc_info=True)
        fresh = await db.get(CreditHold, hid)
        if fresh is not None and fresh.status == "held":
            await _release_only(db, fresh)
        result["orphan_forgiven"] += 1
        logger.info("credit.hold_orphaned", hold_id=hid)
    return result


async def reconcile(db: AsyncSession, *, user_id: str | None = None, repair: bool = False):
    """Verify (and optionally repair) the wallet invariants I1 / I2.

    Per user: ``balance == Σ ledger.delta`` and ``held == Σ active holds``.
    With ``user_id=None`` reconciles every wallet and returns a list of reports.
    """
    if user_id is None:
        ids = (await db.execute(select(CreditWallet.user_id))).scalars().all()
        return [await reconcile(db, user_id=uid, repair=repair) for uid in ids]

    wallet = await get_or_create_wallet(db, user_id)
    expected_balance = int(
        (
            await db.execute(
                select(func.coalesce(func.sum(CreditLedger.delta_units), 0)).where(
                    CreditLedger.user_id == user_id
                )
            )
        ).scalar_one()
    )
    expected_held = int(
        (
            await db.execute(
                select(func.coalesce(func.sum(CreditHold.estimate_units), 0)).where(
                    CreditHold.user_id == user_id, CreditHold.status == "held"
                )
            )
        ).scalar_one()
    )
    balance_drift = wallet.balance_units - expected_balance
    held_drift = wallet.held_units - expected_held
    report = {
        "user_id": user_id,
        "balance_units": wallet.balance_units,
        "expected_balance_units": expected_balance,
        "balance_drift": balance_drift,
        "held_units": wallet.held_units,
        "expected_held_units": expected_held,
        "held_drift": held_drift,
        "repaired": False,
    }
    if balance_drift != 0 or held_drift != 0:
        logger.warning(
            "credit.leak_detected",
            user_id=user_id,
            balance_drift=balance_drift,
            held_drift=held_drift,
        )
        if repair:
            await db.execute(
                update(CreditWallet)
                .where(CreditWallet.user_id == user_id)
                .values(balance_units=expected_balance, held_units=expected_held)
            )
            await db.commit()
            report["repaired"] = True
    return report
