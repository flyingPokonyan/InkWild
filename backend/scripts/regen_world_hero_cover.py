"""Regenerate hero (21:9) + server-cropped cover (3:2) for the two existing
prod worlds whose hero images need to pick up the V3 unified template
(2026-05-19): IP anchor lifted to subject, key art format flexibility,
LLM-derived mood cue.

Targets: 凡尘仙途, 嘉靖风云录.

Per-world steps:
  1. build_world_hero_prompt(brief)   ← V3 unified template
  2. gen 21:9 via gpt-image-2 (with retry/backoff on 429)
  3. crop_to_aspect_ratio(bytes, 3, 2)  → cover 3:2
  4. upload hero + cover to OSS
  5. UPDATE worlds SET hero_image = ..., cover_image = ...

Note: in production cover_brief_helper LLM-derives mood per world from the
full world data. Here we hard-code mood for these two known worlds (admin
can re-trigger generation through the workshop UI to get the LLM-derived
mood for future regens).

Cost: ~$0.5, ~3 min wall clock (with 90s inter-world sleep).
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from sqlalchemy import update  # noqa: E402

from config import settings  # noqa: E402
from database import async_session  # noqa: E402
from llm.openai_compatible import OpenAICompatibleImageProvider  # noqa: E402
from models.world import World  # noqa: E402
from services.cover_brief import CoverBrief, build_world_hero_prompt  # noqa: E402
from services.image_cropper import crop_to_aspect_ratio, materialize_image_bytes  # noqa: E402
from services.image_storage import (  # noqa: E402
    get_image_storage,
    make_image_key,
    save_generated_image_result,
)


WORLD_BRIEFS: list[tuple[str, CoverBrief]] = [
    (
        "6a842bda-3e3f-4e6c-a24b-c1f034d0c30e",
        CoverBrief(
            world_name="凡尘仙途",
            world_name_english="Mortal Path to Immortality",
            genre_tag="仙侠",
            mood="毛笔书法、朱印、云雾、墨色、仙气",
            ip_name="诛仙",
        ),
    ),
    (
        "684ea301-4169-442f-9322-395df0bc68af",
        CoverBrief(
            world_name="嘉靖风云录",
            world_name_english="Jiajing Chronicles",
            genre_tag="古装权谋",
            mood="毛笔书法、朱印、龙袍、烛火、深红",
            ip_name="大明王朝 1566",
        ),
    ),
]


async def gen_with_retry(provider, prompt: str, aspect: str, max_attempts: int = 4):
    for attempt in range(1, max_attempts + 1):
        print(f"  attempt {attempt}/{max_attempts} ({aspect})", flush=True)
        try:
            return await provider.generate_image(prompt, aspect_ratio=aspect, resolution="1k")
        except Exception as exc:
            msg = str(exc)
            transient = "429" in msg or "Too many requests" in msg or "502" in msg
            print(f"  error: {type(exc).__name__}: {msg[:140]}", flush=True)
            if transient and attempt < max_attempts:
                backoff = 60 * attempt
                print(f"  sleeping {backoff}s before retry", flush=True)
                await asyncio.sleep(backoff)
                continue
            raise


async def regen_one(provider, image_storage, db, world_id: str, brief: CoverBrief) -> None:
    print(f"\n=== {brief.world_name} ({world_id}) ===", flush=True)
    prompt = build_world_hero_prompt(brief)
    print(f"prompt ({len(prompt)} chars):\n{prompt}", flush=True)

    # 1. Generate hero
    print("\nGENERATE hero 21:9", flush=True)
    result = await gen_with_retry(provider, prompt, "21:9")

    # 2. Materialize bytes (handles base64 OR url)
    hero_bytes = await materialize_image_bytes(result)
    print(f"hero bytes: {len(hero_bytes)} bytes", flush=True)

    # 3. Upload hero
    hero_key = make_image_key("worlds/hero", brief.world_name)
    hero_url = await save_generated_image_result(image_storage, result, hero_key)
    print(f"hero uploaded: {hero_url}", flush=True)

    # 4. Crop hero → cover 3:2
    cover_bytes = crop_to_aspect_ratio(hero_bytes, target_w=3, target_h=2)
    print(f"cover bytes: {len(cover_bytes)} bytes", flush=True)

    # 5. Upload cover
    cover_key = make_image_key("worlds/cover", brief.world_name, ext="jpg")
    cover_url = await image_storage.save(cover_bytes, cover_key)
    print(f"cover uploaded: {cover_url}", flush=True)

    # 6. Update DB
    await db.execute(
        update(World)
        .where(World.id == world_id)
        .values(hero_image=hero_url, cover_image=cover_url)
    )
    await db.commit()
    print(f"DB updated for {brief.world_name}", flush=True)


async def main() -> None:
    provider = OpenAICompatibleImageProvider(
        api_key=settings.gptimage_api_key,
        base_url=settings.gptimage_base_url,
        model=settings.gptimage_image_model,
    )
    image_storage = get_image_storage()

    async with async_session() as db:
        for idx, (world_id, brief) in enumerate(WORLD_BRIEFS):
            if idx > 0:
                print(f"\n--- inter-world sleep 90s ---", flush=True)
                await asyncio.sleep(90)
            try:
                await regen_one(provider, image_storage, db, world_id, brief)
            except Exception as exc:
                print(f"FATAL for {brief.world_name}: {type(exc).__name__}: {exc}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
