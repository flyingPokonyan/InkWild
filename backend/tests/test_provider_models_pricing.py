import pytest
from sqlalchemy import select
from models.model_management import ProviderModel, ModelProvider


@pytest.mark.asyncio
async def test_provider_model_accepts_pricing_fields(db):
    provider = ModelProvider(
        name="test-provider",
        provider_type="openai_compatible",
        api_key_env_name="TEST_KEY",
    )
    db.add(provider)
    await db.flush()

    model = ProviderModel(
        provider_id=provider.id,
        model_id="gpt-test",
        display_name="GPT Test",
        model_kind="text",
        input_price_cents_per_million_tokens=150,
        output_price_cents_per_million_tokens=600,
    )
    db.add(model)
    await db.commit()

    row = (await db.execute(select(ProviderModel).where(ProviderModel.model_id == "gpt-test"))).scalar_one()
    assert row.input_price_cents_per_million_tokens == 150
    assert row.output_price_cents_per_million_tokens == 600
    assert row.image_price_cents_per_image is None
