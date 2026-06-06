import uuid
from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, Index, Integer, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from database import Base
from utils import utcnow

# Internal fixed-point scale: 1 credit == CREDIT_UNIT_SCALE units (4 decimals).
# Structural constant (not admin-tunable) — every *_units column is in this unit.
CREDIT_UNIT_SCALE = 10_000


class CreditWallet(Base):
    """Per-user credit balance. Cached source-of-truth; reconcilable from CreditLedger."""

    __tablename__ = "credit_wallets"

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("users.id"), unique=True, index=True
    )
    # Signed: bounded-negative allowed (single-action overshoot, see design §6).
    balance_units: Mapped[int] = mapped_column(BigInteger, default=0)
    # Phase 2 (L3): total currently reserved by in-flight actions.
    # available = balance_units - held_units. Invariant I2:
    # held_units == Σ (credit_holds WHERE status='held').estimate_units.
    held_units: Mapped[int] = mapped_column(BigInteger, default=0)
    lifetime_granted_units: Mapped[int] = mapped_column(BigInteger, default=0)
    lifetime_spent_units: Mapped[int] = mapped_column(BigInteger, default=0)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class CreditLedger(Base):
    """Append-only credit movement log. Single source of truth for all credit changes.

    Grants/adjustments are recorded here; per-action debits (game turn /
    generation task) are also recorded here at action granularity. ``cost_cents``
    stores the real cost behind a debit so true margin stays visible alongside
    the charged ``delta_units``.
    """

    __tablename__ = "credit_ledger"
    __table_args__ = (Index("idx_credit_ledger_user_created", "user_id", "created_at"),)

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("users.id"), index=True)
    # + for grants, - for debits.
    delta_units: Mapped[int] = mapped_column(BigInteger)
    balance_after_units: Mapped[int] = mapped_column(BigInteger)
    # signup_grant / backfill_grant / admin_adjust / debit_game /
    # debit_world_gen / debit_script_gen / debit_image_gen
    kind: Mapped[str] = mapped_column(String(32))
    # play / creation / image / grant / adjust — for grouped display.
    category: Mapped[str | None] = mapped_column(String(16), nullable=True)
    ref_type: Mapped[str | None] = mapped_column(String(16), nullable=True)  # session / task
    ref_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    cost_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)  # real cost (fen) behind a debit
    note: Mapped[str | None] = mapped_column(Text, nullable=True)  # admin reason etc.
    actor_user_id: Mapped[str | None] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("users.id"), nullable=True
    )  # admin who made an adjustment
    created_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)


class CreditHold(Base):
    """Phase 2 (L3): per-action reservation + reliable-settlement outbox.

    Reserved at the action boundary (``reserve``), resolved at settlement
    (``settle_hold``). A row in ``held`` whose action crashed mid-flight, or a
    row left ``settle_failed`` after a DB hiccup, is recovered by the sweep
    (see design §5.4) — so ``held_units`` can never leak permanently.
    """

    __tablename__ = "credit_holds"
    __table_args__ = (
        Index("idx_credit_holds_status_created", "status", "created_at"),
        Index("idx_credit_holds_user_status", "user_id", "status"),
    )

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("users.id"), index=True)
    action: Mapped[str] = mapped_column(String(16))  # game / world / script
    ref_type: Mapped[str | None] = mapped_column(String(16), nullable=True)  # session / task
    ref_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    estimate_units: Mapped[int] = mapped_column(BigInteger)  # reserved amount
    charged_units: Mapped[int | None] = mapped_column(BigInteger, nullable=True)  # actual after settle
    # Accumulator snapshot captured when a real-time settle fails, for replay.
    usage_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="held")  # held / settled / settle_failed
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    settled_at: Mapped[datetime | None] = mapped_column(nullable=True)


class CreditConfig(Base):
    """Singleton (id=1) economy config — admin-editable, live (no redeploy).

    Multiplier stored as milli-int (1000 == 1.0x) to avoid float drift; the
    grant/estimate amounts are in credit units (CREDIT_UNIT_SCALE per credit).
    """

    __tablename__ = "credit_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    # Billing multiplier x1000: charged = real_cost * (milli/1000). 1000 == break-even.
    billing_multiplier_milli: Mapped[int] = mapped_column(Integer, default=1_000)
    signup_grant_units: Mapped[int] = mapped_column(BigInteger, default=500 * CREDIT_UNIT_SCALE)
    estimate_game_units: Mapped[int] = mapped_column(BigInteger, default=25 * CREDIT_UNIT_SCALE)
    estimate_world_units: Mapped[int] = mapped_column(BigInteger, default=70 * CREDIT_UNIT_SCALE)
    estimate_script_units: Mapped[int] = mapped_column(BigInteger, default=200 * CREDIT_UNIT_SCALE)
    # Phase 2: credit-subsystem failure posture. 'open' = allow + log on error
    # (pre-revenue default); 'safe' = block on error (flip before charging money).
    gate_fail_mode: Mapped[str] = mapped_column(String(8), default="open")
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)
