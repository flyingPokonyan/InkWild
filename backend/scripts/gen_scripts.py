"""Concurrent 甄嬛传 script generation bound to the published 紫禁深宫 world.

Faithful chapter-scripts: follow canon, divergent endings, dramatic irony.
Run inside backend container: python -m scripts.gen_scripts
"""
import asyncio
import json

WORLD = "e9c87a8e-cde7-4229-9c4f-02d764c2a197"  # 紫禁深宫 (甄嬛传), published
ADMIN = "fc13c915-a3fb-4500-abce-85830e8ae2eb"

A1 = (
    "【忠实复刻·华妃争锋篇】绑定《紫禁深宫》(甄嬛传)世界。忠实跟随原著剧情、不魔改；玩家选一个角色活进剧情，"
    "可顺原著也可做不同动作产生分歧结局；剧透无关，乐趣在代入与改写命运。\n"
    "推荐可扮演视角：甄嬛(主)/沈眉庄/安陵容/华妃年世兰。请使用本世界已有的 canonical 角色，勿新造同类人物。\n"
    "忠实事件链(按时间线触发)：1)选秀入宫初居碎玉轩；2)倚梅园除夕偶遇'清河王'(实为皇帝)得圣意；"
    "3)惊鸿舞得盛宠(似纯元)；4)华妃一丈红杖责夏冬春立威；5)华党木薯粉/温宜公主中毒嫁祸甄党，甄党反击；"
    "6)沈眉庄被诬'假孕'(皇后华妃合谋)；7)年羹尧获罪、华妃失势，欢宜香=麝香致不孕真相浮出；"
    "8)皇后设局'纯元旧衣'致甄失宠(高潮转折)。\n"
    "结局(双轨,至少4个)：复刻原著=华党倒、甄因纯元旧衣心灰决意出家甘露寺；"
    "改写命运=①识破纯元旧衣陷阱未失宠留宫斗皇后 ②提前坐实欢宜香更早扳倒华妃保圣宠 ③保下沈眉庄免诬 ④翻车被联合构陷打入冷宫。\n"
    "信息隔离锚点：华妃不知欢宜香是麝香；皇后藏害纯元旧账；皇帝视甄为纯元替身。"
)

S2 = (
    "【忠实复刻·名场面短本·滴血验亲】绑定《紫禁深宫》(甄嬛传)世界。自包含短本，忠实原著，玩家可顺可分歧，剧透无关。\n"
    "背景：回宫后祺贵人联合皇后当殿告发甄嬛与温实初私通、六阿哥非龙裔，要求滴血验亲。\n"
    "推荐可扮演视角：甄嬛(主,被告信息受困)/温实初(太医能验能牺牲)。请使用本世界已有 canonical 角色。\n"
    "忠实事件链：1)祺贵人当殿发难告私通；2)第一次滴血验亲血相融(有人在水里加了白矾/盐)→危局；"
    "3)玩家查那盆水、找证人(温实初/宫人/采蜜小太监)；4)揭穿水被动手脚→反转；"
    "5)温实初自证(自宫明志)或揪出加料者；6)反咬出祺贵人背后的皇后。\n"
    "结局(双轨,至少4个)：复刻原著=拆穿做手脚、祺贵人倒台、温实初自宫、甄反将皇后一军；"
    "改写命运=①提前查出水中猫腻不靠温实初牺牲即脱险 ②保住温实初 ③未拆穿被坐实私通赐死(失败) ④顺势翻出皇后害纯元旧案当场扳倒皇后。\n"
    "信息隔离锚点：谁在水里动手脚(皇后党指使)；温实初对甄之情。"
)

JOBS = [("A1·紫禁初风云", A1), ("S2·滴血验亲", S2)]


async def main():
    from api.admin import _get_generation_task_service
    from models.draft import ScriptDraft

    svc = _get_generation_task_service()
    started = []
    for label, outline in JOBS:
        res = await svc.start_script_generation(world_id=WORLD, outline=outline, user_id=ADMIN)
        draft_id, task_id = res if isinstance(res, (list, tuple)) else (None, res)
        print(f"[start] {label} task={task_id} draft={draft_id}", flush=True)
        started.append((label, task_id, draft_id))

    # run all concurrently in this process (await to completion)
    await asyncio.gather(
        *[svc._run_script_generation(tid) for _, tid, _ in started],
        return_exceptions=True,
    )

    for label, task_id, draft_id in started:
        t = await svc.get_task(task_id)
        ev = 0
        en = 0
        nm = ""
        if draft_id:
            async with svc.session_factory() as s:
                d = await s.get(ScriptDraft, draft_id)
                p = (d.payload if d else {}) or {}
            ev = len(p.get("events_data") or [])
            en = len(p.get("endings_data") or p.get("endings") or [])
            nm = p.get("name") or p.get("title") or ""
        print(f"[done] {label} status={getattr(t,'status','?')} name={nm} events={ev} endings={en} draft={draft_id}", flush=True)

    print("[ALL_DONE]", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
