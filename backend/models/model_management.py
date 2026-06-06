import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Index, Integer, JSON, String, Text, Uuid, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from database import Base
from utils import utcnow


class ModelProvider(Base):
    __tablename__ = "model_providers"
    __table_args__ = (
        UniqueConstraint("name", name="uq_model_providers_name"),
        Index("idx_model_providers_type_status", "provider_type", "status"),
    )

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(80))
    provider_type: Mapped[str] = mapped_column(String(32))
    base_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    api_key_env_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    # 直填的原始 API key（明文，admin 管理）。非空时优先于 api_key_env_name。
    # 多个 key 用于分散单 key 并发上限，见 llm/key_pool.py。序列化时必须打码。
    api_keys: Mapped[list] = mapped_column(JSON, default=list)
    extra_config: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="active")
    last_healthcheck_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_healthcheck_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class ProviderModel(Base):
    __tablename__ = "provider_models"
    __table_args__ = (
        UniqueConstraint("provider_id", "model_id", "model_kind", name="uq_provider_models_identity"),
        Index("idx_provider_models_provider_kind", "provider_id", "model_kind"),
    )

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    provider_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("model_providers.id"))
    model_id: Mapped[str] = mapped_column(String(120))
    display_name: Mapped[str] = mapped_column(String(120))
    model_kind: Mapped[str] = mapped_column(String(16))
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_price_cents_per_million_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Phase 2: price for prompt-cache-hit input tokens. null => bill hits at the
    # full input price (current behavior, no change).
    cached_input_price_cents_per_million_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_price_cents_per_million_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    image_price_cents_per_image: Mapped[int | None] = mapped_column(Integer, nullable=True)
    price_updated_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class ModelSlotBinding(Base):
    __tablename__ = "model_slot_bindings"

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    slot_name: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    model_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("provider_models.id"))
    status: Mapped[str] = mapped_column(String(20), default="active")
    last_verified_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_verified_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class ModelCapabilityProbe(Base):
    __tablename__ = "model_capability_probes"
    __table_args__ = (
        Index("idx_model_capability_probes_model_capability", "model_id", "capability"),
        Index("idx_model_capability_probes_verified_at", "verified_at"),
    )

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    model_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("provider_models.id"))
    capability: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(20))
    latency_ms: Mapped[int] = mapped_column(default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_sample: Mapped[str | None] = mapped_column(Text, nullable=True)
    verified_at: Mapped[datetime] = mapped_column(default=utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(nullable=True)
