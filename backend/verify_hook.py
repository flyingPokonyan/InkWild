"""Verify LLM-generated 主题钩子: accuracy, IP retention, sparse-essence fallback."""
import asyncio
from sqlalchemy import select
from database import async_session
from models.world import World
from services.cover_brief_helper import derive_world_cover_brief
from services.model_management import resolve_slot_router

NAMES = ["哈利·波特", "后宫·甄嬛传", "庆余年", "灰雾迷城", "记忆典当行"]


async def derive(router, name, wd):
    brief, _ = await derive_world_cover_brief(
        world_data=wd, characters=[], recognition=None, ip_pack=None, llm=router)
    print(f"[{name}]  画法={brief.art_style}")
    print(f"   钩子: {brief.cover_focus or '(空→退回纯发挥)'}")


async def main():
    async with async_session() as db:
        router = await resolve_slot_router(db, "admin_generation")
        for nm in NAMES:
            w = (await db.execute(select(World).where(World.name == nm))).scalars().first()
            if not w:
                print(f"[{nm}] NOT FOUND"); continue
            await derive(router, nm, {"name": w.name, "genre": getattr(w, "genre", ""),
                                       "era": getattr(w, "era", ""), "description": w.description or ""})
        # 极简描述：测 LLM 理解不足时的钩子
        print("--- 极简 essence（测理解不足）---")
        await derive(router, "无名之地", {"name": "无名之地", "genre": "", "era": "", "description": "一个神秘的地方。"})

asyncio.run(main())
