import asyncio
async def main():
    from api.admin import _build_generation_world_creator_agent
    from services.character_roster_builder import build_character_roster
    from schemas.research_pack import IPCanon
    agent = _build_generation_world_creator_agent()
    if asyncio.iscoroutine(agent): agent = await agent
    ipc = IPCanon(canonical_names=["甄嬛","皇后宜修","华妃年世兰","沈眉庄","安陵容","端妃","敬妃","果郡王允礼","温实初","皇帝","太后","曹琴默","祺贵人","叶澜依"])
    roster = await build_character_roster(
        description="电视剧《后宫·甄嬛传》清雍正后宫，忠实复刻，群像宫斗",
        genre="宫斗", era="清朝雍正", ip_canon=ipc, locations=[], passages=[], llm_router=agent.llm,
    )
    items = roster if isinstance(roster, list) else getattr(roster, "roster", [])
    def it(r):
        return getattr(r,"is_image_target", None) if not isinstance(r,dict) else r.get("is_image_target")
    def nm(r):
        return getattr(r,"name", None) if not isinstance(r,dict) else r.get("name")
    def rt(r):
        return getattr(r,"role_tag","") if not isinstance(r,dict) else r.get("role_tag","")
    tgt = [r for r in items if it(r)]
    print(f"[RESULT] total={len(items)} playable={len(tgt)}", flush=True)
    print("[playable]", ", ".join(f"{nm(r)}({rt(r)})" for r in tgt))
asyncio.run(main())
