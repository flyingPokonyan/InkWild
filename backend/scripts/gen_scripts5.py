"""收尾批：A1安回炉 + 9 个名场面小本。绑定紫禁深宫世界。用法: python -m scripts.gen_scripts5 [count]"""
import asyncio
import sys

WORLD = "e9c87a8e-cde7-4229-9c4f-02d764c2a197"
ADMIN = "fc13c915-a3fb-4500-abce-85830e8ae2eb"
_T = "绑定紫禁深宫(甄嬛传)，忠实原著、不魔改，玩家可顺可分歧，剧透无关。请用本世界已有角色，勿新造同类。结局≥4(复刻原著+改写命运)。"

A1A = (_T + "【alt-POV·延禧宫的暗涌(安陵容视角)】玩家扮安陵容，从三姐妹情到黑化全程。推荐视角：安陵容(主)。\n"
       "事件链：1)香料商女出身卑微入宫被轻视；2)苦学歌艺冰嬉争宠；3)在甄嬛沈眉庄的姐妹情与皇后拉拢间摇摆；"
       "4)被皇后收买黑化、以香料害沈眉庄甄嬛；5)与安比槐家族牵连受辱；6)喉疾缠身、众叛亲离孤独终。\n"
       "结局：复刻=黑化倒台凄凉而终；改写=①守住姐妹情不背叛②向上爬保住本心③反戈扳倒皇后④急流勇退。信息锚点：她的自卑与被当枪使。")

S3 = (_T + "【名场面·惊鸿舞】华妃命甄嬛宫宴跳惊鸿舞意图使其出丑，反令甄一舞得宠(神似纯元)。推荐视角：甄嬛(主)/华妃/安陵容。\n"
      "事件链：1)华妃刁难、命甄宫宴献舞；2)甄暗中筹备(借温实初/果郡王笛音相助)；3)宫宴上惊鸿舞惊艳；4)神似纯元触动皇帝；5)甄得盛宠、华妃恼怒生恨。\n"
      "结局：复刻=一舞得宠华妃受挫；改写=①故意藏拙避锋芒②借舞另有所图③失误失宠④反用纯元影像制衡皇帝。")

S4 = (_T + "【名场面·倚梅园除夕】除夕夜甄嬛倚梅园祈福偶遇'清河王'(实为皇帝)初生情愫，余莺儿冒功。推荐视角：甄嬛(主)/余莺儿/安陵容。\n"
      "事件链：1)除夕祈福、剪小像挂梅枝；2)偶遇自称清河王的皇帝、对话生情；3)许愿吹箫；4)余莺儿冒认那夜机缘得宠；5)身份与机缘的悬念。\n"
      "结局：复刻=初得圣意、机缘一度被余莺儿冒占后正名；改写=①当场不让人冒认②避开皇帝守平凡③识破清河王身份④机缘永归他人。")

S5 = (_T + "【名场面·木薯粉】华党用木薯粉害温宜公主、嫁祸甄党。推荐视角：甄嬛(主)/曹琴默/温实初。\n"
      "事件链：1)温宜公主吐奶中毒；2)华党嫁祸甄嬛沈眉庄；3)玩家查粉末来源、温实初验毒；4)揭穿木薯粉与曹琴默华妃；5)曹琴默权衡反水。\n"
      "结局：复刻=查明真相、曹琴默反水自保；改写=①被坐实背锅②提前防范③离间华妃曹琴默④牵出更大阴谋。")

S8 = (_T + "【名场面·甘露寺雪夜】甘露寺时期莫愁(甄嬛)雪夜遇果郡王允礼定情。推荐视角：甄嬛(莫愁)/果郡王允礼/崔槿汐。\n"
      "事件链：1)甘露寺清苦修行；2)雪夜湖畔偶遇允礼；3)诗词唱和暗生情愫；4)互赠信物/箫音传情；5)情与礼的挣扎。\n"
      "结局：复刻=暗定终身、为日后悲剧埋线；改写=①私奔远走②克制不越界③被人撞破④允礼为她筹谋回宫。")

S9 = (_T + "【名场面·迷情香】查安陵容以迷情香/舒痕胶害孕的真相。推荐视角：甄嬛(主)/安陵容/温实初。\n"
      "事件链：1)多名孕妃异常小产；2)线索指向香料；3)查延禧宫安陵容；4)舒痕胶含麝香的证据；5)当面揭穿。\n"
      "结局：复刻=安陵容害人真相败露；改写=①提前查获救下孕妃②反被安嫁祸③逼安反水供出皇后④证据被毁功亏一篑。")

S10 = (_T + "【名场面·猫惊胎】有人以猫惊吓害孕妃小产、栽赃。推荐视角：甄嬛(主)/叶澜依/敬妃。\n"
       "事件链：1)孕妃遇惊小产；2)矛头被栽到某人(如叶澜依的猫)；3)玩家查猫的来源与现场布置；4)揭出幕后皇后党；5)反咬。\n"
       "结局：复刻=查明栽赃、矛头指皇后；改写=①救下胎儿②被坐实③反栽皇后④以退为进留后手。")

S11 = (_T + "【名场面·眉庄之死】沈眉庄难产被害、甄为挚友复仇。推荐视角：甄嬛(主)/温实初/沈眉庄。\n"
       "事件链：1)眉庄怀有身孕(与温实初情深)；2)产期遭遇凶险/难产；3)甄悲愤追查；4)线索指向皇后心腹剪秋；5)复仇与真相。\n"
       "结局：复刻=眉庄逝、甄踏上复仇之路；改写=①救下眉庄母子②保住孩子③提前除掉剪秋④眉庄脱身远遁。信息锚点：剪秋奉皇后命。")

S13 = (_T + "【名场面·死生不复相见】皇后罪行败露、皇帝幽禁皇后的最终对决。推荐视角：甄嬛(主)/皇后宜修/皇帝。\n"
       "事件链：1)纯元旧案等证据齐备；2)当殿对质；3)皇帝震怒；4)'死生不复相见'下旨；5)皇后被废幽禁。\n"
       "结局：复刻=皇后被幽禁、乌拉那拉氏落幕；改写=①皇后绝地反扑②玉石俱焚③留体面全尸④牵连更广清算。")

S14 = (_T + "【名场面·果郡王之死】允礼遭皇帝猜忌、最终死于甄怀中的悲剧。推荐视角：甄嬛(主)/果郡王允礼/皇帝。\n"
       "事件链：1)皇帝疑允礼与甄私情；2)设局试探二人；3)毒酒摆在面前的抉择；4)甄以命相抵的两难；5)允礼之死。\n"
       "结局：复刻=允礼饮毒、死于甄怀、悲剧收场；改写=①甄换酒救允礼②允礼诈死远走③向皇帝坦白求情④二人同归。")

JOBS = [("A1安·延禧宫的暗涌", A1A), ("S3·惊鸿舞", S3), ("S4·倚梅园除夕", S4), ("S5·木薯粉", S5),
        ("S8·甘露雪夜", S8), ("S9·迷情香", S9), ("S10·猫惊胎", S10), ("S11·眉庄之死", S11),
        ("S13·死生不复相见", S13), ("S14·果郡王之死", S14)]


async def main():
    from api.admin import _get_generation_task_service
    from models.draft import ScriptDraft
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    if arg and "," in arg:
        jobs = [JOBS[int(i)] for i in arg.split(",")]
    elif arg:
        jobs = JOBS[:int(arg)]
    else:
        jobs = JOBS
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
        ev = en = dis = 0
        if draft_id:
            async with svc.session_factory() as s:
                d = await s.get(ScriptDraft, draft_id)
                p = (d.payload if d else {}) or {}
            evs = p.get("events_data") or []
            ev = len(evs)
            dis = sum(1 for e in evs if e.get("disabled"))
            en = len(p.get("endings_data") or p.get("endings") or [])
        print(f"[done] {label} status={getattr(t,'status','?')} events={ev} disabled={dis} endings={en} draft={draft_id}", flush=True)
    print("[ALL_DONE]", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
