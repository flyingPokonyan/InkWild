"""Headless 5-genre world + 1 entry-script batch (末日/穿书/重生/民国女频/梦华录).

Run inside backend container, SEQUENTIAL pacing to respect STO burst limit:
  python -m scripts.gen_genres world_a mori
  python -m scripts.gen_genres world_b mori
  python -m scripts.gen_genres pub_world mori
  python -m scripts.gen_genres script mori
  python -m scripts.gen_genres pub_script mori
  python -m scripts.gen_genres auto mori           # a->b->pub->script->pub for one key, with sleeps
State per key: /tmp/gengenre_<key>.json
"""
import asyncio
import json
import sys

ADMIN = "fc13c915-a3fb-4500-abce-85830e8ae2eb"  # Pokonyan, is_admin
PACE = 12  # seconds between heavy phases (STO burst-limit guard)

WORLDS: dict[str, dict] = {
    "mori": {  # 末日
        "fidelity": "none",
        "desc": (
            "末日废土·封闭避难所题材（原创）。三十年前一场名为‘灰雾’的灾变吞没地表，"
            "嗅味捕猎的感染者在雾中游荡，幸存者龟缩于一座旧军事工事改造的地下避难所‘方舟-7’。"
            "避难所分三层：上层是闸门、岗哨与通风机房；中层是公共食堂、配给站与议事厅；"
            "下层是水培农场、蓄水池与医疗舱。物资按工票配给，夜间通风循环时灰雾有渗入风险。"
            "内部派系：维持秩序、信奉‘秩序即氧气’的议事会；垄断黑市、囤积物资的仓管帮；"
            "主张离开避难所去寻找传说中地表绿洲的远征派；以及隐姓埋名、来历不明的外来者。"
            "近来避难所接连有人‘失踪’或‘暴毙’，表面归咎于灰雾渗入，实则暗流汹涌——"
            "有人在清除知情者、有人在做配给黑账、有人握着灰雾真正来源的秘密。"
            "气质=末世生存 + 封闭社群社会推理：物资倒计时、夜间灰雾循环、尸潮逼近闸门、"
            "内部清洗多重压力叠加。请塑造一组各揣冲突秘密的幸存者群像（议事会议长、"
            "仓管帮头目、远征派领袖、医疗舱医师、年轻岗哨、外来者等），人物有作息、有生活肌理，"
            "舞台有边界、可被时钟驱动。可玩视角应覆盖执法者/拾荒侦察/医师/外来者等不对称身份。"
        ),
    },
    "chuanshu": {  # 穿越·穿书
        "fidelity": "none",
        "desc": (
            "穿越·穿书题材（原创）。玩家是现代读者，一觉醒来穿进一本古早狗血宫斗小说《孽海重楼》，"
            "成了书里‘注定三个月后被赐毒酒赐死’的恶毒女配——架空昭宁王朝的四公主府嫡出郡主。"
            "玩家隐约记得原著大致剧情走向（女主白月光上位、男主太子深情、女配嫉妒作死被赐死），"
            "但书里没写到的角落全是未知。舞台：昭宁王朝的公主府、皇宫宴苑与京城坊市。"
            "群像各有秘密：被全书偏爱的‘女主’（人设清纯实则心机）、深情人设的太子（另有所图）、"
            "女配身边唯一真心的贴身侍女（藏着自己的身世）、疑似同样穿书进来的另一个人（也知剧情、是对手）、"
            "被原著写成反派其实另有隐情的角色。核心可藏张力：原著‘剧情’是否真会发生、能否被改写？"
            "是否还有别的穿书者？这个世界的‘作者规则’是什么？女配前身被写成恶毒——真有其罪还是被构陷？"
            "压力源=原著‘三个月后赐死’的死亡倒计时，剧情关键节点步步逼近，改一处可能崩全盘。"
            "气质=戏剧反讽 + 改命求生：玩家手握‘剧透’优势却处处是未知陷阱。可玩视角覆盖穿书女配/"
            "知情侍女/另一个穿书者/原著女主等不对称身份。请塑造可被自然语言行动逐步撬动的群像与谜面。"
        ),
    },
    "chongsheng": {  # 重生
        "fidelity": "none",
        "desc": (
            "重生复仇题材（原创）。大胤王朝，镇国将军府嫡女沈昭，前世被庶妹与负心未婚夫联手构陷、"
            "扣上通敌罪名致满门抄斩，自己受尽折磨而死。一朝魂归，重生回到一切尚未发生的及笄之年，"
            "带着前世全部记忆。舞台：将军府内的嫡庶宅院、京城权贵交际圈、朝堂边缘。"
            "群像各揣秘密：装柔弱的庶妹（前世的刽子手）、掌家的继母（构陷主谋，藏着沈昭生母真正的死因）、"
            "前世背叛她的负心未婚夫、前世害过她但这世尚可争取的人、唯一察觉她‘变了’的忠仆。"
            "核心张力（对 NPC 隐藏、玩家知一半）：前世满门抄斩的幕后主使到底是谁？生母真正死因？"
            "而玩家‘知道未来’这件事本身既是最大底牌、也是最大破绽——一旦被识破‘重生’便招来妖异之祸。"
            "压力源=前世的覆灭时间线步步逼近（若不改，原定的构陷将在数月后重演），玩家必须赶在悲剧重演前翻盘，"
            "同时小心隐藏重生的秘密。气质=戏剧反讽 + 复仇逆袭 + 古代嫡庶宅斗。"
            "可玩视角覆盖重生嫡女/忠仆/庶妹（反视角）/可争取的盟友等不对称身份。注意：本世界是‘她自己的前世·"
            "复仇·古代将门’，与穿书的‘外来灵魂·求生’味道要清晰拉开。请塑造作息分明、可被自然语言撬动的群像。"
        ),
    },
    "minguo": {  # 民国女频
        "fidelity": "none",
        "desc": (
            "民国都市·名媛公馆题材（原创·女性向）。1930 年代上海十里洋场，法租界里的江南丝绸世家‘沈氏’公馆。"
            "留洋归来的沈家大小姐在家族联姻、商战与时局谍影之间周旋求存。舞台：沈公馆（深宅内宅）、"
            "百乐门舞厅、外滩洋行写字间、老城厢钱庄。旗袍、留声机、霓虹与暗流。"
            "群像各揣秘密：精明掌家的当家太太（藏着沈家真正的财政危机）、争产的二房姨太太（暗通外人）、"
            "周旋各方的大小姐（主角）、与沈家议亲的世交银行少爷（真实身份成谜——地下党？商敌？）、"
            "知道沈家发家旧账的老管家、消息灵通人人都想拉拢的交际花闺蜜。"
            "核心可藏真相：沈氏即将倾覆的真正原因（商战阴谋？政治站队？一桩牵连沈家的旧命案/旧血债？）、"
            "议亲对象的真实身份。压力源=家族财政危机倒计时 + 联姻期限 + 战云将至逼迫站队 + 商敌步步紧逼。"
            "气质=民国情感 + 商战谍影 + 女性周旋，与古代宅斗/宫廷拉开。可玩视角覆盖大小姐/二姨太/议亲对象/"
            "交际花闺蜜等不对称身份。请塑造有生活肌理、可被自然语言逐步撬动的群像与悬念。"
        ),
    },
    "menghualu": {  # IP 女频·梦华录
        "fidelity": "loose",
        "desc": (
            "改编自剧集《梦华录》（脱胎自关汉卿杂剧《赵盼儿风月救风尘》）。北宋东京，钱塘茶坊女老板赵盼儿，"
            "携善厨的孙三娘、擅琵琶的宋引章两姐妹闯荡东京，盘下‘半遮面’茶坊、立志做成东京最大酒楼，"
            "途中与皇城司指挥顾千帆因缘际会，在商战、断案与情感之间立足。舞台：东京半遮面茶坊/永安楼、"
            "樊楼、皇城司、钱塘旧地。忠实复刻核心人物：赵盼儿、顾千帆、孙三娘、宋引章、负心人欧阳旭、"
            "权相萧钦言、纨绔池衙内、市井帮闲何四等，气质=宋代市井女性互助 + 商战 + 探案 + 言情。"
            "群像各揣秘密：机敏要强的赵盼儿、查朝堂大案又藏着身世的顾千帆、藏着家庭旧伤的孙三娘、"
            "识人不清成软肋的宋引章、攀附权贵的欧阳旭、幕后布局的萧钦言。可长出的接缝：同行构陷半遮面的商战案、"
            "顾千帆追查的朝堂大案、欧阳旭的算计。请用本世界已有角色，勿新造同类。可玩视角覆盖赵盼儿/孙三娘/"
            "顾千帆等。玩家可顺可分歧，剧透无关。"
        ),
    },
}

# label, outline — 1 entry script per world (入门本：自包含、单子舞台、中等赌注、低前置知识)
SCRIPTS: dict[str, tuple[str, str]] = {
    "mori": ("入门·闸门夜", (
        "【入门本·闸门夜·谁动了通风阀】方舟-7 的一个寻常夜里，下层通风阀被人悄悄调向，"
        "灰雾即将顺着风道渗入水培农场层；与此同时，一名当晚值守、似乎察觉到异样的年轻岗哨离奇死在机房。"
        "玩家须在天亮前查清：是谁动的阀、为什么、那名岗哨之死是意外还是灭口。推荐视角：年轻岗哨的同伴/"
        "医疗舱医师/外来者。\n"
        "事件链：1)夜间警报——农场层湿度与灰雾读数异常；2)机房发现岗哨尸体、现场被人动过；3)走访议事会、"
        "仓管帮、远征派各方说辞互相矛盾；4)配给黑账与通风维修记录浮出交集；5)在灰雾真正渗入前锁定动阀之人、"
        "当众对质。\n结局(≥4)：复刻=揪出内鬼、及时封阀保住农场；改写=①只能牺牲封阀、放弃一部分舱室"
        "②真凶将祸水嫁给外来者③查明是议事会为‘清除不稳定因素’默许④牵出灰雾来源的更大秘密。"
        "信息锚点：那名岗哨死前想告诉谁、通风维修记录上被涂掉的名字。"
    )),
    "chuanshu": ("入门·毒酒三月", (
        "【入门本·开局·毒酒三月倒计时】玩家睁眼即是《孽海重楼》里被写死的恶毒女配，"
        "正身处入府后的第一场宫宴——而这场宴会，正是原著中‘女配陷害女主、反被当众揭穿、自此失势走向赐死’的"
        "开局剧情节点。玩家手握‘剧透’记忆，是按原著避开这步死棋、还是反向布局？推荐视角：穿书女配(主)/"
        "知情侍女/另一个穿书者。\n事件链：1)宴前侍女通风报信、玩家辨认‘剧情’将至；2)原著中‘嫁祸女主’的局"
        "已被人布下，玩家可拆可避可将计就计；3)席间察觉另一个‘也知道剧情’的人在暗中搅动；4)女主/太子的真实"
        "态度与原著描述出现偏差；5)在‘原著该发生的羞辱’临界点做出选择、改写或坐实命运第一步。\n"
        "结局(≥4)：复刻=避开死棋、初步站稳、死亡倒计时松动；改写=①弄巧成拙提前坐实‘恶毒’人设②识破并联手/"
        "扳倒另一个穿书者③揭穿太子或女主的伪装④改动太大引发‘剧情反噬’招来新危机。"
        "信息锚点：你与那个穿书者的关系、原著里这场宴会真正的转折点。"
    )),
    "chongsheng": ("入门·重生第一日", (
        "【入门本·重生第一日·先发制人】沈昭重生回到前世噩梦开始的那个春日——前世，正是这天庶妹设下的第一步"
        "构陷让她着了道、自此步步走向满门抄斩。这一世她带着记忆睁眼，庶妹的第一招（一桩‘失仪/失窃’的栽赃）"
        "即将落下。玩家凭前世记忆抢先一步：是当场揭穿、隐忍布局，还是反将一军？推荐视角：重生嫡女(主)/忠仆/"
        "庶妹(反视角)。\n事件链：1)重生睁眼、玩家凭记忆辨认今日将发生的构陷；2)庶妹按‘前世剧本’布下第一局；"
        "3)玩家先发应对，同时小心不暴露‘我知道未来’；4)继母出面‘主持公道’实则偏帮，旧日恩怨初现；"
        "5)在构陷落定前翻盘或隐忍蓄势。\n结局(≥4)：复刻=先发制人扳回一局、扭转前世开局；改写=①隐忍蛰伏"
        "放长线钓大鱼②用力过猛暴露重生之异招致猜忌③反将一军让庶妹自食恶果④牵动继母与生母旧案提前浮现。"
        "信息锚点：前世这天她错信了谁、生母死因的第一缕线索。"
    )),
    "minguo": ("入门·订婚宴", (
        "【入门本·订婚宴·租界一夜】沈家在法租界公馆为大小姐操办订婚宴，冠盖云集。然而这一夜，"
        "沈家暗藏的财政黑账、议亲对象讳莫如深的真实身份、二房姨太太精心布下的暗算，同时在宴席上浮出水面。"
        "大小姐须在一夜之间周旋各方，既保住自己、也保住摇摇欲坠的家族体面。推荐视角：沈家大小姐(主)/二姨太/"
        "议亲银行少爷。\n事件链：1)宴前——账房异动与一封匿名信同时送到；2)宴上各方寒暄之下暗流交锋；"
        "3)议亲对象的身份疑点被人有意无意挑破；4)二房借宴生事、财政黑幕险些当众爆开；5)大小姐在席散前做出"
        "决定性周旋。\n结局(≥4)：复刻=借势化解、保住婚约与家族体面；改写=①当机退婚、自立门户②被二房与商敌"
        "联手算计③议亲对象身份揭破改变全局④顺线揪出拖垮沈家的真正黑手。信息锚点：那封匿名信出自谁手、"
        "议亲少爷深夜见的那个人。"
        "\n【硬性要求】事件链须展开为至少 5 个独立、有效（非 disabled）的 event，触发条件简单可达、勿过度嵌套。"
    )),
    "menghualu": ("入门·半遮面开张", (
        "【入门本·半遮面·开张风波】赵盼儿携孙三娘、宋引章在东京盘下‘半遮面’茶坊，初来乍到、招牌未稳，"
        "开张不久便遭同行构陷——一桩‘以次充好/贵客在店中‘中招’’的栽赃闹到门前，眼看要砸了三姐妹的生计。"
        "赵盼儿须查清是谁做的局、护住招牌与姐妹清白。推荐视角：赵盼儿(主)/孙三娘/顾千帆。\n"
        "事件链：1)开张遇冷与流言四起；2)贵客‘出事’、人证物证齐齐指向半遮面；3)赵盼儿明察暗访、识破栽赃破绽；"
        "4)同行/背后之人的算计逐层浮现，或牵动顾千帆的关注；5)当众理清是非、反将构陷者一军。\n"
        "结局(≥4)：复刻=查清构陷、半遮面转危为安、声名鹊起；改写=①损失惨重被迫另起炉灶②借顾千帆之力收场"
        "但欠下人情③构陷者反咬、三姐妹险些获罪④牵出更大的商战黑幕/背后权贵。信息锚点：那位‘出事’贵客究竟受谁指使、"
        "栽赃的破绽藏在哪一道茶/菜里。"
    )),
}

WORLD_PREAMBLE: dict[str, str] = {
    "mori": "绑定本末日避难所世界，忠实末世生存+封闭社群社会推理气质，玩家可顺可分歧、剧透无关。请用本世界已有角色，勿新造同类。结局≥4。",
    "chuanshu": "绑定本穿书世界，忠实‘穿进小说当注定要死的炮灰女配、知剧情改命求生’的戏剧反讽气质，玩家可顺可分歧、剧透无关。请用本世界已有角色，勿新造同类。结局≥4。",
    "chongsheng": "绑定本重生复仇世界，忠实‘嫡女重生、带前世记忆复仇逆袭、古代嫡庶宅斗’气质，玩家可顺可分歧、剧透无关。请用本世界已有角色，勿新造同类。结局≥4。",
    "minguo": "绑定本民国名媛世界，忠实‘1930年代上海·商战谍影·女性周旋’气质，玩家可顺可分歧、剧透无关。请用本世界已有角色，勿新造同类。结局≥4。",
    "menghualu": "绑定梦华录世界，忠实宋代市井+女性互助+商战探案气质，玩家可顺可分歧、剧透无关。请用本世界已有角色，勿新造同类。结局≥4。",
}


def _sp(key: str) -> str:
    return f"/tmp/gengenre_{key}.json"


def _load(key: str) -> dict:
    try:
        with open(_sp(key)) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def _save(key: str, d: dict) -> None:
    with open(_sp(key), "w") as f:
        json.dump(d, f, ensure_ascii=False)


async def world_a(key: str) -> None:
    from api.admin import _get_generation_task_service
    from services.generation_task_service import PHASE_A
    spec = WORLDS[key]
    svc = _get_generation_task_service()
    print(f"[world_a:{key}] IP recognition gate...", flush=True)
    draft_id, task_a = await svc.start_world_generation(description=spec["desc"], user_id=ADMIN, phase=PHASE_A)
    await svc._run_world_generation(task_a)
    t = await svc.get_task(task_a)
    rec = (t.intermediate_state or {}).get("ip_recognition") or {}
    st = _load(key)
    st.update({"draft_id": draft_id, "rec": rec, "fidelity": spec["fidelity"]})
    _save(key, st)
    print(f"[world_a:{key}] status={getattr(t,'status','?')} draft={draft_id} kind={rec.get('kind')}", flush=True)


async def world_b(key: str) -> None:
    from api.admin import _get_generation_task_service
    from models.draft import WorldDraft
    spec = WORLDS[key]
    st = _load(key)
    svc = _get_generation_task_service()
    print(f"[world_b:{key}] {spec['fidelity']} generation on {st['draft_id']} ...", flush=True)
    task_b = await svc.start_world_phase_b_task(
        draft_id=st["draft_id"], description=spec["desc"], user_id=ADMIN,
        ip_recognition=st.get("rec") or None, fidelity_mode=spec["fidelity"],
    )
    await svc._run_world_generation(task_b)
    tb = await svc.get_task(task_b)
    async with svc.session_factory() as s:
        d = await s.get(WorldDraft, st["draft_id"])
        payload = (d.payload if d else {}) or {}
    chars = payload.get("world_characters") or payload.get("characters") or []
    playable = [c for c in chars if c.get("playable")]
    print(f"[world_b:{key}] status={getattr(tb,'status','?')} total_chars={len(chars)} playable={len(playable)}", flush=True)
    print(f"[world_b:{key}] playable={json.dumps([c.get('name') for c in playable], ensure_ascii=False)}", flush=True)


async def pub_world(key: str) -> None:
    from api.admin import _get_generation_task_service
    from services.publish_service import publish_world_draft
    st = _load(key)
    svc = _get_generation_task_service()
    async with svc.session_factory() as s:
        world = await publish_world_draft(s, draft_id=st["draft_id"], actor_user_id=ADMIN, audit_enabled=False)
        st["world_id"] = world.id
    _save(key, st)
    print(f"[pub_world:{key}] world_id={st['world_id']} name={getattr(world,'name','?')}", flush=True)


async def gen_script(key: str) -> None:
    from api.admin import _get_generation_task_service
    from models.draft import ScriptDraft
    st = _load(key)
    label, outline = SCRIPTS[key]
    preamble = WORLD_PREAMBLE[key]
    svc = _get_generation_task_service()
    draft_id, task_id = await svc.start_script_generation(
        world_id=st["world_id"], outline=preamble + "\n" + outline, user_id=ADMIN)
    print(f"[script:{key}] start {label} task={task_id} draft={draft_id}", flush=True)
    await svc._run_script_generation(task_id)
    t = await svc.get_task(task_id)
    async with svc.session_factory() as s:
        d = await s.get(ScriptDraft, draft_id)
        p = (d.payload if d else {}) or {}
    evs = p.get("events_data") or []
    en = len(p.get("endings_data") or p.get("endings") or [])
    st["script_draft"] = draft_id
    _save(key, st)
    print(f"[script:{key}] {label} status={getattr(t,'status','?')} events={len(evs)} endings={en} draft={draft_id}", flush=True)


async def pub_script(key: str) -> None:
    from api.admin import _get_generation_task_service
    from services.publish_service import publish_script_draft
    from models.draft import ScriptDraft
    from sqlalchemy.orm.attributes import flag_modified
    st = _load(key)
    did = st["script_draft"]
    svc = _get_generation_task_service()
    async with svc.session_factory() as s:
        d = await s.get(ScriptDraft, did)
        if d:
            p = dict(d.payload)
            evs = p.get("events_data") or []
            kept = [e for e in evs if not e.get("disabled")]
            if len(kept) != len(evs):
                p["events_data"] = kept
                d.payload = p
                flag_modified(d, "payload")
                await s.commit()
    async with svc.session_factory() as s:
        sc = await publish_script_draft(s, draft_id=did, actor_user_id=ADMIN, audit_enabled=False)
    print(f"[pub_script:{key}] -> {getattr(sc,'status','?')} | {getattr(sc,'name','?')}", flush=True)


async def auto(key: str) -> None:
    await world_a(key); await asyncio.sleep(PACE)
    await world_b(key); await asyncio.sleep(PACE)
    await pub_world(key); await asyncio.sleep(PACE)
    await gen_script(key); await asyncio.sleep(PACE)
    await pub_script(key)
    print(f"[AUTO_DONE:{key}] {json.dumps(_load(key), ensure_ascii=False)}", flush=True)


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    fn = {"world_a": world_a, "world_b": world_b, "pub_world": pub_world,
          "script": gen_script, "pub_script": pub_script, "auto": auto}.get(cmd)
    if not fn:
        print(__doc__); sys.exit(1)
    asyncio.run(fn(sys.argv[2]))


if __name__ == "__main__":
    main()
