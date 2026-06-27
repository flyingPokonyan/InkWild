"""Re-render hero+cover for all PUBLISHED worlds with the new 插画 cover_brief.
Two-phase: serial brief derivation, then concurrent image gen (sem-limited).
Backs up old URLs to /tmp/regen_backup.json first (rollback). Run in the
LOCAL container after Clash is off (gateway must be reachable)."""
import asyncio, json
from pathlib import Path
from sqlalchemy import select
from database import async_session
from models.world import World
from models.ip_knowledge_pack import IPKnowledgePack
from services.cover_brief_helper import derive_world_cover_brief
from services.cover_brief import build_world_hero_prompt, build_world_cover_prompt
from services.model_management import resolve_slot_router, resolve_slot_image_generator
from services.image_storage import get_image_storage, make_image_key, IMAGE_PLACEHOLDER_URL
from services.world_creator_agent_v2 import _generate_image_with_fallback
from services.ip_recognizer import IPRecognition

SEM = asyncio.Semaphore(12)

async def gen(image_gen, tiers, aspect, category, name, log_key):
    async with SEM:
        url, _ = await _generate_image_with_fallback(
            image_gen, tiers, aspect_ratio=aspect, storage=get_image_storage(),
            storage_key=make_image_key(category, name or "image"), log_key=log_key)
        return url if (url and url != IMAGE_PLACEHOLDER_URL) else None

async def main():
    async with async_session() as db:
        router = await resolve_slot_router(db, "admin_generation")
        image_gen = await resolve_slot_image_generator(db, "image_generation")
        if image_gen is None:
            print("no image generator bound"); return
        worlds = (await db.execute(select(World).where(World.status == "published"))).scalars().all()
        ONLY = {"哈利·波特", "东方快车谋杀案", "大唐狄公案"}  # blocked-cover retry
        if ONLY:
            worlds = [w for w in worlds if w.name in ONLY]
        print(f"{len(worlds)} worlds", flush=True)

        # backup
        backup = [{"id": str(w.id), "name": w.name, "hero": w.hero_image, "cover": w.cover_image} for w in worlds]
        Path("/tmp/regen_backup.json").write_text(json.dumps(backup, ensure_ascii=False, indent=2))
        print("backed up old URLs -> /tmp/regen_backup.json", flush=True)

        # phase 1: derive briefs (serial; light LLM calls)
        plans = []
        for w in worlds:
            wd = {"name": w.name or "", "genre": getattr(w, "genre", "") or "",
                  "era": getattr(w, "era", "") or "", "description": w.description or ""}
            pack = (await db.execute(select(IPKnowledgePack).where(IPKnowledgePack.world_id == str(w.id)))).scalars().first()
            recog = None
            if pack and (pack.ip_name or "").strip():
                recog = IPRecognition(kind="known_ip", confidence=1.0, ip_name=pack.ip_name.strip())
            try:
                brief, _ = await derive_world_cover_brief(world_data=wd, characters=[], recognition=recog, ip_pack=None, llm=router)
            except Exception as e:
                print(f"DERIVE-FAIL {w.name}: {type(e).__name__}: {e}", flush=True); continue
            is_ip = bool(brief.ip_name and brief.ip_name.strip())
            plans.append((w, brief, is_ip))
            print(f"  {w.name:12} 画法={brief.art_style or 'fb':6} 焦点={brief.cover_focus[:46]}", flush=True)

        # phase 2: concurrent image gen
        async def do(w, brief, is_ip):
            hero_t = [build_world_hero_prompt(brief)] + ([build_world_hero_prompt(brief, ip_fallback=True)] if is_ip else [])
            cover_t = [build_world_cover_prompt(brief)] + ([build_world_cover_prompt(brief, ip_fallback=True)] if is_ip else [])
            h, c = await asyncio.gather(
                gen(image_gen, hero_t, "21:9", "worlds/hero", w.name, f"hero:{w.name}"),
                gen(image_gen, cover_t, "3:2", "worlds/cover", w.name, f"cover:{w.name}"))
            return w, h, c
        results = await asyncio.gather(*[do(w, b, ip) for w, b, ip in plans])

        # write DB (serial)
        for w, h, c in results:
            ch = []
            if h: w.hero_image = h; ch.append("hero")
            if c: w.cover_image = c; ch.append("cover")
            print(f"{'OK ' if ch else 'FAIL'} {w.name}  {ch}", flush=True)
        await db.commit()
    print("done", flush=True)

asyncio.run(main())
