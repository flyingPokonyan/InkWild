"""One-off: rebind image_generation slot to the gpt-image provider.

Bootstrap only creates bindings when none exist — it never overrides an
existing binding (e.g. the legacy xAI/Grok image binding). Run this once
against any environment whose slot still points at Grok.

Usage: cd backend && python scripts/rebind_image_slot_to_gptimage.py
Requires GPTIMAGE_API_KEY (+ base_url / model in config or env).
"""

import asyncio

from sqlalchemy import select

from config import settings
from database import async_session
from models.model_management import ModelProvider, ProviderModel
from services.model_management import (
    IMAGE_MODEL_KIND,
    SYSTEM_GPTIMAGE_PROVIDER_NAME,
    bind_model_slot,
    ensure_default_model_management_state,
)


async def main() -> None:
    if not settings.gptimage_api_key:
        print("FAIL: GPTIMAGE_API_KEY 未配置")
        return

    async with async_session() as db:
        await ensure_default_model_management_state(db)

        provider = (
            await db.execute(
                select(ModelProvider).where(ModelProvider.name == SYSTEM_GPTIMAGE_PROVIDER_NAME)
            )
        ).scalar_one_or_none()
        if not provider:
            print(f"FAIL: provider {SYSTEM_GPTIMAGE_PROVIDER_NAME!r} 未 bootstrap")
            return

        model = (
            await db.execute(
                select(ProviderModel)
                .where(ProviderModel.provider_id == provider.id)
                .where(ProviderModel.model_id == settings.gptimage_image_model)
                .where(ProviderModel.model_kind == IMAGE_MODEL_KIND)
            )
        ).scalar_one_or_none()
        if not model:
            print(f"FAIL: 模型 {settings.gptimage_image_model!r} 未 bootstrap")
            return

        result = await bind_model_slot(db, slot_name="image_generation", model_id=str(model.id))
        print("OK: image_generation 已绑定到", settings.gptimage_image_model)
        print("    binding status:", result.get("binding", {}).get("status"))
        print("    last_verified_error:", result.get("binding", {}).get("last_verified_error"))


if __name__ == "__main__":
    asyncio.run(main())
