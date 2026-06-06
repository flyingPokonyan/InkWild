"""Headless IP world + scripts generation (batch: 狄公案 / 东方快车 / 莲花楼).

Run inside backend container, e.g.:
  python -m scripts.gen_ip world_a digong       # phase_a: IP recognition gate
  python -m scripts.gen_ip world_b digong       # phase_b: full generation (long)
  python -m scripts.gen_ip pub_world digong      # publish world draft -> prints world_id
  python -m scripts.gen_ip scripts digong        # gen all script outlines for the world
  python -m scripts.gen_ip scripts digong 0,2    # gen only outline indices 0 and 2
  python -m scripts.gen_ip pub_scripts <draft_id> [<draft_id> ...]

State per key persists in /tmp/genip_<key>.json (draft_id, recognition, world_id, script drafts).
"""
import asyncio
import json
import sys

ADMIN = "fc13c915-a3fb-4500-abce-85830e8ae2eb"  # Pokonyan, is_admin


# ---------------------------------------------------------------------------
# World definitions
# ---------------------------------------------------------------------------
WORLDS: dict[str, dict] = {
    "digong": {
        "fidelity": "loose",
        "desc": (
            "高罗佩《大唐狄公案》改编。唐高宗时期，名相狄仁杰任地方州县父母官，刚正不阿、断狱如神，"
            "被西方读者誉为'中国的福尔摩斯'。忠实复刻核心人物：狄仁杰（狄公，主审官）、亲随老都头洪亮、"
            "勇健校尉乔泰与马荣、师爷陶甘。舞台：州县衙门大堂与后衙、市集街巷、客栈、寺庙道观、城门关隘。"
            "气质=唐代公案推理，重实地勘探、取证与逻辑推演，单元探案、一案一群嫌疑人。"
            "无固定派系，每个案件自带各自的知情人与利害冲突方。"
        ),
    },
    "orient": {
        "fidelity": "strict",
        "desc": (
            "阿加莎·克里斯蒂《东方快车谋杀案》。1930年代隆冬，辛普朗号东方快车从伊斯坦布尔西行，"
            "因暴风雪滞留在南斯拉夫荒原雪地，与世隔绝。比利时大侦探赫尔克里·波洛恰好同车。深夜，"
            "头等车厢的美国富商雷切特在反锁包厢内被连刺十二刀身亡——他的真实身份是多年前阿姆斯特朗"
            "绑架撕票案中逃脱法网的主犯卡塞蒂。同车十二名乘客身份各异（俄国德拉戈米罗夫公爵夫人、"
            "匈牙利安德烈尼伯爵夫妇、美国太太哈伯德、英国阿巴思诺特上校、女家庭教师玛丽·德贝纳姆、"
            "德国女仆、意大利商人、列车员皮埃尔·米歇尔、波洛旧友布克先生等），实则全部与阿姆斯特朗"
            "一家有隐秘渊源。忠实复刻原著人物、封闭雪夜车厢的有限舞台、'十二人各刺一刀'的集体复仇隐藏"
            "真相，以及波洛最终给出的'两个结论'。"
        ),
    },
    "qing": {
        "fidelity": "loose",
        "desc": (
            "猫腻小说《庆余年》/同名剧改编。架空古代庆国，少年范闲身世成谜——生母叶轻眉留下惊世遗泽，"
            "范闲自南方澹州奉命入京都，卷入监察院、皇室与各方势力的权谋漩涡。忠实复刻核心人物：范闲、"
            "陈萍萍（监察院院长，城府极深）、庆帝、范建（户部尚书）、林婉儿、神秘高手五竹、言冰云、"
            "王启年、二皇子、太子、长公主李云睿、北齐圣女海棠朵朵、肖恩、费介、范思辙等。地点：监察院、"
            "皇宫大殿、范府、抱月楼、京都街市、澹州、北齐。派系：监察院 / 皇室 / 太子党 / 二皇子党 / "
            "长公主势力。气质=朝堂权谋 + 查案谍战 + 身世悬案，群像各揣秘密、信息高度不对称；"
            "贯穿暗线是范闲生母叶轻眉当年之死的真相。"
        ),
    },
    "lianhua": {
        "fidelity": "loose",
        "desc": (
            "藤萍小说《吉祥纹莲花楼》/剧《莲花楼》改编。十年前，四顾门少门主、天下第一的李相夷与"
            "金鸳盟盟主笛飞声东海决战，双双重伤失踪；十年后，李相夷化名游医李莲花，带着会移动的小楼"
            "'莲花楼'隐居江湖，身中碧茶之毒、命不久矣，平日装作不通医术的庸医。他与热血率真的捕快世家"
            "公子方多病、隐忍深沉的笛飞声三人因缘际会，屡破江湖奇案。忠实复刻核心人物（李莲花/李相夷、"
            "方多病、笛飞声、单孤刀、乔婉娩、肖紫衿、角丽谯、石水等）、江湖门派（四顾门、金鸳盟、百川院）、"
            "会移动的莲花楼。气质=武侠探案：单元江湖奇案在前台，李莲花的隐藏身份与十年前东海决战的旧日"
            "恩怨作贯穿暗线。"
        ),
    },
}


# ---------------------------------------------------------------------------
# Script outlines (per world key). Each: (label, outline).
# Outline density mirrors scripts/gen_scripts5.py: 事件链 + 结局 + 推荐视角 + 信息锚点.
# {WORLD} placeholder will be replaced with a per-world binding preamble at gen time.
# ---------------------------------------------------------------------------
SCRIPTS: dict[str, list[tuple[str, str]]] = {
    "digong": [
        ("入门·铜钟案", (
            "【入门本·蓬莱铜钟案】狄公初到蓬莱县上任，接手两桩悬案：城外古寺普慈寺一座大铜钟下压着一具尸体，"
            "以及多年前轰动一时的林氏布商灭门旧案。推荐视角：狄仁杰(主)/洪亮/案中嫌疑人。\n"
            "事件链：1)狄公赴任、查阅积案卷宗；2)普慈寺铜钟下惊现命案、僧众闪烁其词；3)勘验现场、走访市集人证；"
            "4)旧案苦主与新案现场出现交集线索；5)识破真凶布局、当堂取证对质。\n"
            "结局(≥4)：复刻=狄公明察、铜钟与灭门两案真凶伏法；改写=①关键证物被毁须另辟蹊径②真凶反咬狄公"
            "构陷③苦主私自复仇先一步动手④牵出更高官员包庇。信息锚点：寺院香火钱去向与铜钟为何半年未响。"
        )),
        ("进阶·湖滨案", (
            "【进阶本·汉源湖滨案】狄公调任汉源县，城西湖上花船名妓在众目睽睽的诗会夜里离奇身亡，"
            "在座皆是地方士绅名流，人人都有不可告人的秘密。复用洪亮、乔泰，扩展到士绅宅邸与湖船双舞台。"
            "推荐视角：狄仁杰(主)/乔泰/与死者有牵连的士绅。\n"
            "事件链：1)湖船诗会、名妓席间猝死；2)在座士绅各执一词、互相遮掩；3)狄公分查宅邸与湖船双线；"
            "4)名妓暗藏的账本/书信浮出水面、牵连多人；5)锁定下毒时机与真凶动机当堂对质。\n"
            "结局(≥4)：复刻=查明士绅杀人灭口、真相大白；改写=①被栽赃的清白者险些顶罪②真凶买通仵作伪造死因"
            "③名妓其实诈死另有隐情④牵出走私漕运窝案。信息锚点：名妓临死前要见的那个人。"
        )),
        ("收官·黄金案", (
            "【收官本·蓬莱黄金案】狄公追查前任蓬莱县令暴毙之谜——表面病故，实则牵出朝鲜走私黄金与杀官灭口的"
            "通天大案，赌注最高、群像全员、各方势力交织。复用全部亲随，舞台扩至城门关隘与海港。"
            "推荐视角：狄仁杰(主)/马荣/走私网络中人。\n"
            "事件链：1)前令'病故'疑点重重、狄公暗访；2)海港走私黄金线索浮现；3)亲随分头查城门、关隘、海船；"
            "4)灭口连环发生、狄公自身陷入险境；5)收网对质、揭出幕后主使。\n"
            "结局(≥4)：复刻=狄公破走私杀官大案、主使落网；改写=①主使是上官、狄公面临官场抉择②走私网络鱼死网破"
            "③关键证人被灭口功亏一篑④狄公将计就计反间收网。信息锚点：前任县令死前寄出的那封密信。"
        )),
    ],
    "orient": [
        ("主本·雪夜列车", (
            "【主本·雪夜东方快车（波洛视角）】东方快车暴雪滞留荒原，深夜头等车厢富商雷切特被反锁包厢内连刺十二刀。"
            "波洛在封闭车厢内逐一审问十二名乘客，每个人都有不在场证明、却处处是破绽。推荐视角：赫尔克里·波洛(主)/"
            "布克先生/列车员皮埃尔。\n"
            "事件链：1)清晨发现命案、列车与世隔绝无人能下车；2)勘验包厢——十二刀深浅不一、停摆的怀表、烧焦的纸片；"
            "3)逐一审问乘客、谎言与口音破绽；4)死者真实身份=阿姆斯特朗案逃犯卡塞蒂浮出，乘客与受害家庭的隐秘渊源"
            "一一显形；5)波洛识破'十二人各刺一刀'的集体复仇、面对两个结论的抉择。\n"
            "结局(≥4)：复刻=波洛提出'两个结论'、出于人性选择隐瞒真相放走十二人；改写=①公事公办、将真相交予警方"
            "②被某乘客铤而走险灭口的危机③促成十二人自首与赎罪和解④发现混入的第十三人翻转全案。"
            "信息锚点：怀表停在的时刻是伪造的、烧焦纸片上的'阿姆斯特朗'。"
        )),
        ("alt·复仇者", (
            "【alt-POV·十二分之一（乘客视角）】玩家扮演十二名复仇者之一，在波洛逐一审问下，既要替屈死的阿姆斯特朗"
            "一家完成这场集体复仇，又要隐藏自己的真实身份、与同伴们守住默契、误导这位太精明的侦探。"
            "推荐视角：复仇乘客之一(主)/同谋者/波洛(对手)。\n"
            "事件链：1)行动当夜各就各位、按计划行刺；2)清晨案发、波洛登场审问；3)玩家应对盘问、维持伪装与口供一致；"
            "4)同伴中有人露馅、计划出现裂缝；5)在波洛揭破真相的临界点做出选择。\n"
            "结局(≥4)：复刻=众人默契守住秘密、波洛成全放行；改写=①玩家露馅连累全体②玩家良心动摇主动坦白"
            "③内部猜忌反目计划崩盘④说服波洛达成'两个结论'的默契。信息锚点：你与阿姆斯特朗一家的那层关系。"
        )),
    ],
    "qing": [
        ("入门·京都风波", (
            "【入门本·京都风波】范闲奉命自澹州初入京都，途中遭牛栏街程巨树伏杀，五竹出手相救；范闲初识监察院"
            "与京中各方势力。推荐视角：范闲(主)/王启年/言冰云。\n"
            "事件链：1)范闲入京、暗藏叶轻眉留下的钥匙之谜；2)牛栏街遭程巨树刺杀、五竹拼死护主；3)追查刺杀"
            "幕后(太子/二皇子/长公主皆有嫌疑)；4)监察院言冰云、王启年的试探与结盟；5)当众揭出主使、范闲在"
            "京都立稳脚跟。\n"
            "结局(≥4)：复刻=查明刺杀主使、范闲立足京都；改写=①提前识破刺杀全身而退②被栽赃为刺客反遭通缉"
            "③策反刺客反咬主使④锋芒太露招致更大杀机。信息锚点：刺客令牌的来路、五竹为何拼死护他。"
        )),
        ("进阶·抱月楼黑幕", (
            "【进阶本·抱月楼黑幕】京都销金窟抱月楼背后藏着人口买卖与黑账，线索直指二皇子的钱袋。复用王启年、"
            "言冰云，扩展到朝堂党争。推荐视角：范闲(主)/二皇子/抱月楼管事。\n"
            "事件链：1)抱月楼命案/女子失踪牵出黑幕；2)范闲暗查账本与人口线索；3)矛头指向二皇子的财路；"
            "4)二皇子的拉拢与威胁、范闲进退两难；5)证据呈堂、查抄抱月楼、重创对手。\n"
            "结局(≥4)：复刻=查抄抱月楼、断二皇子财路；改写=①账本被毁功亏一篑②被二皇子反将构陷③与二皇子"
            "虚与委蛇放长线④顺藤牵出更高的内库黑影。信息锚点：抱月楼真正的东家、内库的影子。"
        )),
        ("收官·叶轻眉之死", (
            "【收官本·叶轻眉之死的真相】贯穿暗线总爆发：范闲追查生母叶轻眉当年之死的真相，逐层揭开陈萍萍、"
            "庆帝、长公主多年的隐秘与算计。最高赌注、群像全员、结局分支最多。推荐视角：范闲(主)/陈萍萍/庆帝/"
            "长公主。\n"
            "事件链：1)叶轻眉的遗物与旧案线索浮现；2)范闲追查当年京都那一夜到底发生了什么；3)陈萍萍隐忍多年"
            "的复仇布局逐层揭开；4)庆帝的真实角色与长公主的牵连显形；5)真相大白后范闲在亲情、权力与复仇间"
            "的终极抉择。\n"
            "结局(≥4)：复刻=真相揭破、范闲与庆帝走向决裂；改写=①隐忍蛰伏以待来日②与陈萍萍共谋清算"
            "③放下复仇守住眼前人④玉石俱焚同归于尽。信息锚点：叶轻眉留下的那句遗志、神庙的秘密。"
        )),
    ],
    "lianhua": [
        ("入门·云隐山庄", (
            "【入门本·云隐山庄疑案】方多病初遇'庸医'李莲花。云隐山庄一桩离奇命案，李莲花装作不通医术却屡屡点破关键，"
            "方多病又气又疑。莲花楼作为流动据点登场。推荐视角：方多病(主)/李莲花/山庄案中人。\n"
            "事件链：1)方多病为查案夜投云隐山庄、命案发生；2)李莲花以游医身份出现、看似糊涂却暗中验尸取证；"
            "3)方多病揭穿其医术作假、却破不了案的反差；4)庄中各房嫌疑、流言与旧怨；5)李莲花点破诡计、真凶现形。\n"
            "结局(≥4)：复刻=真凶伏法、方多病对李莲花刮目相看结伴同行；改写=①方多病独力破案抢功②真凶是同情者"
            "网开一面③李莲花病发暴露武功底子引人怀疑④庄主以死护住更大秘密。信息锚点：李莲花为何懂验尸却装不懂医。"
        )),
        ("进阶·易容奇案", (
            "【进阶本·角丽谯易容案】一桩'死人复活'/身份调包的易容奇案，牵出金鸳盟旧部角丽谯。笛飞声以神秘高手身份"
            "介入。复用李莲花、方多病，扩展到江湖门派恩怨。推荐视角：李莲花(主)/方多病/笛飞声。\n"
            "事件链：1)已死之人再现人间、目击者各执一词；2)李莲花识破易容/人皮面具的破绽；3)金鸳盟旧部的影子浮现；"
            "4)笛飞声出手、与李莲花暗中较劲又隐隐配合；5)揭穿调包局、引出十年前旧案的一角。\n"
            "结局(≥4)：复刻=易容真相大白、暗线指向东海旧怨；改写=①被易容者反将一军②方多病识破李莲花身份疑点"
            "③笛飞声暴露立场④角丽谯倒戈供出金鸳盟。信息锚点：易容者要顶替的那个身份、与四顾门的关系。"
        )),
        ("收官·东海决战", (
            "【收官本·东海决战真相】贯穿暗线总爆发：单孤刀的背叛、李相夷的真实身份、十年前东海一战的真相。"
            "李莲花碧茶之毒将尽，必须在大限前了断旧案。赌注最高、群像全员、结局分支最多。"
            "推荐视角：李莲花/李相夷(主)/笛飞声/单孤刀。\n"
            "事件链：1)旧部与信物牵出十年前决战疑点；2)单孤刀当年背叛的真相逐层揭开；3)李莲花身份在众人前濒临揭穿；"
            "4)与笛飞声从死敌到并肩、直面单孤刀；5)东海决战真相大白、李莲花面对生死与去留的终局抉择。\n"
            "结局(≥4)：复刻=真相昭雪、李莲花放下一切、泛舟远去赴死；改写=①寻得解毒生机、重入江湖②与笛飞声"
            "了断恩怨各自归隐③单孤刀幡然悔悟同归于尽④隐姓埋名守着莲花楼终老。信息锚点：东海决战那夜真正发生了什么。"
        )),
    ],
}

WORLD_PREAMBLE = {
    "digong": "绑定大唐狄公案世界，忠实唐代公案气质、注重勘探取证与逻辑推理，玩家可顺可分歧，剧透无关。请用本世界已有角色，勿新造同类。结局≥4。",
    "orient": "绑定东方快车谋杀案世界，忠实阿加莎原著人物与封闭车厢设定，玩家可顺可分歧，剧透无关。请用本世界已有角色，勿新造同类。结局≥4。",
    "lianhua": "绑定莲花楼世界，忠实武侠探案气质、李莲花隐藏身份暗线，玩家可顺可分歧，剧透无关。请用本世界已有角色，勿新造同类。结局≥4。",
    "qing": "绑定庆余年世界，忠实朝堂权谋+查案+身世悬案气质、信息高度不对称，玩家可顺可分歧，剧透无关。请用本世界已有角色，勿新造同类。结局≥4。",
}


def _state_path(key: str) -> str:
    return f"/tmp/genip_{key}.json"


def _load(key: str) -> dict:
    try:
        with open(_state_path(key)) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def _save(key: str, d: dict) -> None:
    with open(_state_path(key), "w") as f:
        json.dump(d, f, ensure_ascii=False)


async def world_a(key: str) -> None:
    from api.admin import _get_generation_task_service
    from services.generation_task_service import PHASE_A

    spec = WORLDS[key]
    svc = _get_generation_task_service()
    print(f"[world_a:{key}] starting IP recognition...", flush=True)
    draft_id, task_a = await svc.start_world_generation(
        description=spec["desc"], user_id=ADMIN, phase=PHASE_A
    )
    await svc._run_world_generation(task_a)
    t = await svc.get_task(task_a)
    print(f"[world_a:{key}] task status={getattr(t,'status','?')}", flush=True)
    rec = (t.intermediate_state or {}).get("ip_recognition") or {}
    print(f"[world_a:{key}] draft_id={draft_id}", flush=True)
    print(f"[world_a:{key}] recognition={json.dumps(rec, ensure_ascii=False)}", flush=True)
    st = _load(key)
    st.update({"draft_id": draft_id, "task_a": task_a, "rec": rec, "fidelity": spec["fidelity"]})
    _save(key, st)
    kind = rec.get("kind")
    if spec["fidelity"] == "strict" and kind != "known_ip":
        print(f"[GATE-WARN] fidelity=strict but kind={kind}; consider loose", flush=True)
    else:
        print(f"[GATE-OK] kind={kind} fidelity={spec['fidelity']}; safe for world_b", flush=True)


async def world_b(key: str) -> None:
    from api.admin import _get_generation_task_service
    from models.draft import WorldDraft

    spec = WORLDS[key]
    st = _load(key)
    svc = _get_generation_task_service()
    print(f"[world_b:{key}] {spec['fidelity']} generation on draft {st['draft_id']} ...", flush=True)
    task_b = await svc.start_world_phase_b_task(
        draft_id=st["draft_id"],
        description=spec["desc"],
        user_id=ADMIN,
        ip_recognition=st.get("rec") or None,
        fidelity_mode=spec["fidelity"],
    )
    st["task_b"] = task_b
    _save(key, st)
    print(f"[world_b:{key}] task_b={task_b} running...", flush=True)
    await svc._run_world_generation(task_b)
    tb = await svc.get_task(task_b)
    print(f"[world_b:{key}] final status={getattr(tb,'status','?')}", flush=True)
    async with svc.session_factory() as s:
        d = await s.get(WorldDraft, st["draft_id"])
        payload = (d.payload if d else {}) or {}
    chars = payload.get("world_characters") or payload.get("characters") or []
    playable = [c for c in chars if c.get("playable")]
    print(f"[world_b:{key}] total_chars={len(chars)} playable={len(playable)}", flush=True)
    print(f"[world_b:{key}] playable={json.dumps([c.get('name') for c in playable], ensure_ascii=False)}", flush=True)


async def pub_world(key: str) -> None:
    from api.admin import _get_generation_task_service
    from services.publish_service import publish_world_draft

    st = _load(key)
    svc = _get_generation_task_service()
    async with svc.session_factory() as s:
        world = await publish_world_draft(s, draft_id=st["draft_id"], actor_user_id=ADMIN, audit_enabled=False)
        world_id = world.id
        name = world.name
    st["world_id"] = world_id
    _save(key, st)
    print(f"[pub_world:{key}] world_id={world_id} name={name} status={getattr(world,'status','?')}", flush=True)


async def gen_scripts(key: str, indices: list[int] | None) -> None:
    from api.admin import _get_generation_task_service
    from models.draft import ScriptDraft

    st = _load(key)
    world_id = st["world_id"]
    preamble = WORLD_PREAMBLE[key]
    jobs = SCRIPTS[key]
    if indices:
        jobs = [jobs[i] for i in indices]
    svc = _get_generation_task_service()
    started = []
    for label, outline in jobs:
        draft_id, task_id = await svc.start_script_generation(
            world_id=world_id, outline=preamble + "\n" + outline, user_id=ADMIN
        )
        print(f"[start] {label} task={task_id} draft={draft_id}", flush=True)
        started.append((label, task_id, draft_id))
    await asyncio.gather(*[svc._run_script_generation(t) for _, t, _ in started], return_exceptions=True)
    st.setdefault("script_drafts", {})
    for label, task_id, draft_id in started:
        t = await svc.get_task(task_id)
        ev = en = dis = 0
        async with svc.session_factory() as s:
            d = await s.get(ScriptDraft, draft_id)
            p = (d.payload if d else {}) or {}
        evs = p.get("events_data") or []
        ev = len(evs)
        dis = sum(1 for e in evs if e.get("disabled"))
        en = len(p.get("endings_data") or p.get("endings") or [])
        st["script_drafts"][label] = draft_id
        print(f"[done] {label} status={getattr(t,'status','?')} events={ev} disabled={dis} endings={en} draft={draft_id}", flush=True)
    _save(key, st)
    print(f"[SCRIPTS_DONE:{key}] drafts={json.dumps(st['script_drafts'], ensure_ascii=False)}", flush=True)


async def pub_scripts(draft_ids: list[str]) -> None:
    """Publish script drafts. Strips disabled events first — generation sometimes
    emits disabled events with malformed condition trees that fail publish validation
    (disabled events never run, so dropping them is safe)."""
    from api.admin import _get_generation_task_service
    from services.publish_service import publish_script_draft
    from models.draft import ScriptDraft
    from sqlalchemy.orm.attributes import flag_modified

    svc = _get_generation_task_service()
    for did in draft_ids:
        try:
            async with svc.session_factory() as s:
                d = await s.get(ScriptDraft, did)
                if d:
                    p = dict(d.payload)
                    evs = p.get("events_data") or []
                    kept = [e for e in evs if not e.get("disabled")]
                    if len(kept) != len(evs):
                        print(f"[strip] {did[:8]}: {len(evs)}->{len(kept)} events", flush=True)
                        p["events_data"] = kept
                        d.payload = p
                        flag_modified(d, "payload")
                        await s.commit()
            async with svc.session_factory() as s:
                sc = await publish_script_draft(s, draft_id=did, actor_user_id=ADMIN, audit_enabled=False)
            print(f"[pub] {did[:8]} -> {getattr(sc,'status','?')} | {getattr(sc,'name','?')}", flush=True)
        except Exception as e:
            print(f"[ERR] {did[:8]}: {type(e).__name__}: {str(e)[:160]}", flush=True)
    print("[PUB_SCRIPTS_DONE]", flush=True)


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "world_a":
        asyncio.run(world_a(sys.argv[2]))
    elif cmd == "world_b":
        asyncio.run(world_b(sys.argv[2]))
    elif cmd == "pub_world":
        asyncio.run(pub_world(sys.argv[2]))
    elif cmd == "scripts":
        key = sys.argv[2]
        idx = [int(i) for i in sys.argv[3].split(",")] if len(sys.argv) > 3 else None
        asyncio.run(gen_scripts(key, idx))
    elif cmd == "pub_scripts":
        asyncio.run(pub_scripts(sys.argv[2:]))
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
