"""Look up per-model pricing from the provider_models table."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.model_management import ModelProvider, ProviderModel


async def get_pricing_for(
    db: AsyncSession,
    *,
    provider_name: str | None,
    model_id: str | None,
) -> dict | None:
    """Return pricing dict for the given provider + model, or None if not found.

    The returned dict has keys:
      - input_price_cents_per_million_tokens
      - output_price_cents_per_million_tokens
      - image_price_cents_per_image
      - cached_input_price_cents_per_million_tokens

    Any of these may be None if not configured.
    """
    if not provider_name or not model_id:
        return None

    stmt = (
        select(
            ProviderModel.input_price_cents_per_million_tokens,
            ProviderModel.output_price_cents_per_million_tokens,
            ProviderModel.image_price_cents_per_image,
            ProviderModel.cached_input_price_cents_per_million_tokens,
        )
        .join(ModelProvider, ModelProvider.id == ProviderModel.provider_id)
        .where(
            ModelProvider.name == provider_name,
            ProviderModel.model_id == model_id,
        )
    )
    row = (await db.execute(stmt)).first()
    if row is None:
        return None

    return {
        "input_price_cents_per_million_tokens": row[0],
        "output_price_cents_per_million_tokens": row[1],
        "image_price_cents_per_image": row[2],
        "cached_input_price_cents_per_million_tokens": row[3],
    }
