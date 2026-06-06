"""add model management tables

Revision ID: 6f1c2a4b8d9e
Revises: 5561197da50c
Create Date: 2026-04-17 18:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "6f1c2a4b8d9e"
down_revision: Union[str, Sequence[str], None] = "5561197da50c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if "model_providers" not in table_names:
        op.create_table(
            "model_providers",
            sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
            sa.Column("name", sa.String(length=80), nullable=False),
            sa.Column("provider_type", sa.String(length=32), nullable=False),
            sa.Column("base_url", sa.String(length=500), nullable=True),
            sa.Column("api_key_env_name", sa.String(length=80), nullable=False),
            sa.Column("extra_config", sa.JSON(), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
            sa.Column("last_healthcheck_at", sa.DateTime(), nullable=True),
            sa.Column("last_healthcheck_error", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("name", name="uq_model_providers_name"),
        )
        op.create_index("idx_model_providers_type_status", "model_providers", ["provider_type", "status"], unique=False)

    if "provider_models" not in table_names:
        op.create_table(
            "provider_models",
            sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
            sa.Column("provider_id", sa.Uuid(as_uuid=False), nullable=False),
            sa.Column("model_id", sa.String(length=120), nullable=False),
            sa.Column("display_name", sa.String(length=120), nullable=False),
            sa.Column("model_kind", sa.String(length=16), nullable=False),
            sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["provider_id"], ["model_providers.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("provider_id", "model_id", "model_kind", name="uq_provider_models_identity"),
        )
        op.create_index("idx_provider_models_provider_kind", "provider_models", ["provider_id", "model_kind"], unique=False)

    if "model_slot_bindings" not in table_names:
        op.create_table(
            "model_slot_bindings",
            sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
            sa.Column("slot_name", sa.String(length=50), nullable=False),
            sa.Column("model_id", sa.Uuid(as_uuid=False), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
            sa.Column("last_verified_at", sa.DateTime(), nullable=True),
            sa.Column("last_verified_error", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["model_id"], ["provider_models.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_model_slot_bindings_slot_name", "model_slot_bindings", ["slot_name"], unique=True)

    if "model_capability_probes" not in table_names:
        op.create_table(
            "model_capability_probes",
            sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
            sa.Column("model_id", sa.Uuid(as_uuid=False), nullable=False),
            sa.Column("capability", sa.String(length=32), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("response_sample", sa.Text(), nullable=True),
            sa.Column("verified_at", sa.DateTime(), nullable=False),
            sa.Column("expires_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["model_id"], ["provider_models.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "idx_model_capability_probes_model_capability",
            "model_capability_probes",
            ["model_id", "capability"],
            unique=False,
        )
        op.create_index(
            "idx_model_capability_probes_verified_at",
            "model_capability_probes",
            ["verified_at"],
            unique=False,
        )


def downgrade() -> None:
    op.drop_index("idx_model_capability_probes_verified_at", table_name="model_capability_probes")
    op.drop_index("idx_model_capability_probes_model_capability", table_name="model_capability_probes")
    op.drop_table("model_capability_probes")
    op.drop_index("ix_model_slot_bindings_slot_name", table_name="model_slot_bindings")
    op.drop_table("model_slot_bindings")
    op.drop_index("idx_provider_models_provider_kind", table_name="provider_models")
    op.drop_table("provider_models")
    op.drop_index("idx_model_providers_type_status", table_name="model_providers")
    op.drop_table("model_providers")
