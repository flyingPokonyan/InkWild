"""重生成后宫·甄嬛传世界的全部图片（关 mock + 新 gpt-image 端点）：
世界 hero(21:9) + cover(3:2) + 9 可玩角色头像(2:3) + 21 剧本封面(3:2)，写回 DB。"""
import asyncio
from config import settings
settings.mock_images = False  # 关 mock，用真实端点

WORLD = "e9c87a8e-cde7-4229-9c4f-02d764c2a197"


async def main():
    from api.admin import _build_generation_world_creator_agent, _get_generation_task_service
    from services.cover_brief_helper import derive_world_cover_brief
    from services.cover_brief import (
        build_world_hero_prompt, build_world_cover_prompt,
        build_character_portrait_prompt, build_script_cover_prompt,
    )
    from services.world_creator_agent_v2 import _generate_image_with_fallback
    from services.image_storage import get_image_storage, make_image_key
    from services.ip_recognizer import IPRecognition
    from models.world import World, WorldCharacter
    from models.script import Script
    from sqlalchemy import select

    agent = _build_generation_world_creator_agent()
    if asyncio.iscoroutine(agent):
        agent = await agent
    ig, storage, llm = agent.image_gen, get_image_storage(), agent.llm
    sf = _get_generation_task_service().session_factory
    rec = IPRecognition(kind="known_ip", ip_name="后宫·甄嬛传", ip_type="tv",
                        one_liner="", confidence=1.0, source_hints=[])
    sem = asyncio.Semaphore(4)

    async def gen(prompt, ar, cat, name, label):
        async with sem:
            url, _ = await _generate_image_with_fallback(
                ig, [prompt], aspect_ratio=ar, storage=storage,
                storage_key=make_image_key(cat, name), log_key=label)
            ok = url and "placeholder" not in (url or "")
            print(f"[img] {label} -> {'OK' if ok else 'FAIL'} {url[:55] if url else ''}", flush=True)
            return url if ok else None

    async with sf() as s:
        w = await s.get(World, WORLD)
        world_data = {"name": w.name, "genre": w.genre, "era": w.era, "base_setting": w.base_setting}
        pchars = (await s.execute(select(WorldCharacter).where(
            WorldCharacter.world_id == WORLD, WorldCharacter.playable == True))).scalars().all()
        pnames = [(c.name, c.personality or "") for c in pchars]
        scripts = (await s.execute(select(Script).where(
            Script.world_id == WORLD, Script.status == "published"))).scalars().all()
        sc_meta = [(str(sc.id), sc.name, sc.description or "") for sc in scripts]

    char_inputs = [{"name": n, "role_tag": "", "personality": p, "gender": "", "is_image_target": True}
                   for (n, p) in pnames]
    print(f"[brief] deriving cover_brief for {len(char_inputs)} chars + {len(sc_meta)} scripts...", flush=True)
    cover_brief, char_briefs = await derive_world_cover_brief(
        world_data=world_data, characters=char_inputs, recognition=rec, ip_pack=None, llm=llm)

    # 世界 hero + cover
    hero = await gen(build_world_hero_prompt(cover_brief), "21:9", "worlds/hero", w.name, "world_hero")
    cover = await gen(build_world_cover_prompt(cover_brief), "3:2", "worlds/cover", w.name, "world_cover")

    async def gen_av(n):
        cb = char_briefs.get(n)
        if not cb:
            print(f"[img] avatar:{n} -> no brief"); return n, None
        return n, await gen(build_character_portrait_prompt(cover_brief, cb), "2:3", "characters", n, f"avatar:{n}")

    async def gen_sc(sid, name, desc):
        p = build_script_cover_prompt(cover_brief, script_title=name, script_title_english="", script_essence=desc[:200])
        return sid, await gen(p, "3:2", "scripts/cover", name, f"script:{name}")

    av = await asyncio.gather(*[gen_av(n) for (n, _) in pnames])
    sc = await asyncio.gather(*[gen_sc(*m) for m in sc_meta])

    async with sf() as s:
        w = await s.get(World, WORLD)
        if hero: w.hero_image = hero
        if cover: w.cover_image = cover
        for n, url in av:
            if url:
                c = (await s.execute(select(WorldCharacter).where(
                    WorldCharacter.world_id == WORLD, WorldCharacter.name == n))).scalars().first()
                if c: c.avatar = url
        for sid, url in sc:
            if url:
                obj = await s.get(Script, sid)
                if obj: obj.cover_image = url
        await s.commit()

    print(f"[DONE] hero={'ok' if hero else 'X'} cover={'ok' if cover else 'X'} "
          f"avatars={sum(1 for _,u in av if u)}/{len(av)} script_covers={sum(1 for _,u in sc if u)}/{len(sc)}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
