"""P1 批次甄嬛传剧本（绑定紫禁深宫世界）。忠实章节本 + 双结局。
用法: python -m scripts.gen_scripts2 [count]   # 只跑前 count 个（默认全部），用于先验证再批量
"""
import asyncio
import sys

WORLD = "e9c87a8e-cde7-4229-9c4f-02d764c2a197"
ADMIN = "fc13c915-a3fb-4500-abce-85830e8ae2eb"
_TAIL = "请使用本世界已有 canonical 角色，勿新造同类人物。剧透无关，乐趣在代入与改写命运。"

A3 = ("【忠实复刻·熹妃掌六宫篇（回宫复起弧）】绑定紫禁深宫(甄嬛传)。忠实跟随原著、不魔改。"
      "推荐视角：甄嬛(主)/端妃/安陵容/皇后宜修。" + _TAIL + "\n"
      "事件链：1)甄嬛回宫产龙凤胎、封熹贵妃、平反甄家；2)察觉安陵容用迷情香/舒痕胶害孕的真相；"
      "3)沈眉庄难产被害身亡，甄为其复仇；4)祺贵人构陷私通、滴血验亲被反破；5)查出皇后当年以砒霜害纯元皇后的旧案；"
      "6)皇后'死生不复相见'被幽禁、安陵容等倒台。\n"
      "结局(双轨≥4)：复刻原著=皇后党崩、安党倒、甄掌六宫；改写=①更早集齐证据提前扳倒皇后 ②救下沈眉庄 "
      "③操之过急反被构陷失势 ④与皇后玉石俱焚。\n信息隔离锚点：安陵容香料害人之秘；皇后害纯元旧账；皇帝多疑。")

A2 = ("【忠实复刻·甘露青丝断篇（失宠出家弧）】绑定紫禁深宫(甄嬛传)。忠实原著。"
      "推荐视角：甄嬛(主)/果郡王允礼/崔槿汐。" + _TAIL + "\n"
      "事件链：1)甄父卷入文字狱被陷，甄心灰意冷自请出宫修行；2)甘露寺受尼姑姑子欺凌、槿汐护主；"
      "3)雪中/湖上偶遇果郡王允礼，诗词唱和暗生情愫；4)误传允礼死讯(或惊觉自己只是纯元替身)；"
      "5)为腹中骨肉设计'偶遇'皇帝，以半副仪仗回宫。\n"
      "结局(双轨≥4)：复刻原著=回宫复起、甄家平反；改写=①与允礼私奔远走 ②留在甘露寺不回宫 "
      "③回宫之计被识破打入冷宫 ④保住与允礼的孩子身世不被疑。\n信息隔离锚点：允礼对甄之情；纯元替身真相；甄家冤案内情。")

S6 = ("【忠实复刻·名场面短本·纯元旧衣】绑定紫禁深宫(甄嬛传)。自包含短本，忠实原著。"
      "推荐视角：甄嬛(主)/皇后宜修(设局者)/敬妃(知情旁观)。" + _TAIL + "\n"
      "事件链：1)皇后假意赏赐一件旧衣；2)甄嬛不知那是纯元皇后故衣，穿之出席；"
      "3)皇帝见之震怒，视为亵渎挚爱/把甄当替身；4)甄当场失宠、禁足；5)事后线索指向皇后蓄意设局。\n"
      "结局(双轨≥4)：复刻原著=甄失宠、心灰萌生去意；改写=①识破来历拒穿、避开陷阱 ②事后查实皇后设局当众反将 "
      "③借皇帝愧疚反获恩宠 ④彻底寒心提前布局复仇。\n信息隔离锚点：旧衣是纯元故衣；皇后设局之秘；皇帝视甄为替身。")

S12 = ("【忠实复刻·名场面短本·砒霜旧案(纯元死因)】绑定紫禁深宫(甄嬛传)。自包含调查短本，忠实原著。"
       "推荐视角：甄嬛(主)/端妃(知部分内情)/温实初(医证)。" + _TAIL + "\n"
       "事件链：1)偶得旧线索(太医院旧档/一只旧药箱)；2)循线追查纯元皇后当年'难产而亡'的疑点；"
       "3)证据逐步指向皇后当年下砒霜；4)集齐人证物证；5)择机当殿揭发。\n"
       "结局(双轨≥4)：复刻原著=皇后罪行败露、被幽禁；改写=①证据不足反被皇后倒打构陷 "
       "②皇后狗急跳墙先下手 ③证据确凿扳倒更彻底(赐死) ④留一手以旧案长期挟制皇后。\n信息隔离锚点：皇后害纯元之秘；端妃旁观所知；温实初能验毒。")

S1 = ("【忠实复刻·名场面短本·一丈红(入门)】绑定紫禁深宫(甄嬛传)。自包含入门短本，忠实原著，教玩家认识华妃与后宫规矩。"
      "推荐视角：甄嬛(新人)/华妃年世兰(施威者)/沈眉庄。" + _TAIL + "\n"
      "事件链：1)新人夏冬春恃宠嚣张、顶撞华妃；2)华妃震怒、赐'一丈红'杖责立威；"
      "3)玩家可选择干预(求情/旁观/激化/暗助)；4)华党借此立威，玩家或结怨或自保或示好。\n"
      "结局(双轨≥4)：复刻原著=夏冬春被杖责、华妃立威；改写=①出手救下夏冬春结一善缘 "
      "②激怒华妃殃及自身 ③借机向华妃示好换取暂时安全 ④冷眼旁观、暗中收买人心。\n信息隔离锚点：华妃跋扈仗年家之势；新人间的拉拢与提防。")

# reorder: 3 个事件偏薄/失败的先做（redo with CoT off），S6/S12 已好放后面
JOBS = [("A3·熹妃掌六宫", A3), ("A2·甘露青丝断", A2), ("S1·一丈红", S1), ("S6·纯元旧衣", S6), ("S12·砒霜旧案", S12)]


async def main():
    from api.admin import _get_generation_task_service
    from models.draft import ScriptDraft
    n = int(sys.argv[1]) if len(sys.argv) > 1 else len(JOBS)
    jobs = JOBS[:n]
    svc = _get_generation_task_service()
    started = []
    for label, outline in jobs:
        res = await svc.start_script_generation(world_id=WORLD, outline=outline, user_id=ADMIN)
        draft_id, task_id = res if isinstance(res, (list, tuple)) else (None, res)
        print(f"[start] {label} task={task_id} draft={draft_id}", flush=True)
        started.append((label, task_id, draft_id))
    await asyncio.gather(*[svc._run_script_generation(t) for _, t, _ in started], return_exceptions=True)
    for label, task_id, draft_id in started:
        t = await svc.get_task(task_id)
        ev = en = 0
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
