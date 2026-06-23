"""Character Roster Builder — 两阶段人物生成。

阶段 1: build_character_roster
  planner LLM 一次调用，输出 N 个角色的简略条目（name + role_tag + faction + is_image_target）。
  N 由 LLM 自决，启发式提取 description 中的"X 个角色/NPC"可指定数量。

阶段 2: build_characters_in_batches
  roster 切批，每批独立并发 LLM 调用，产出每个 NPC 完整 schema。
  批后做严格 1:1 dedup 校验：extra/missing/duplicate 全部 warn，不补占位。
"""
import asyncio
import json
import re
from typing import Any

import structlog

from schemas.character_v2 import Character, CharacterPeerRelation, CharacterRosterEntry
from schemas.ip_knowledge_pack import FidelityMode, IPKnowledgePack
from schemas.research_pack import IPCanon, Passage

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Module-level constants for IP constraint bracket markers (Fix 4)
# ---------------------------------------------------------------------------
_CONSTRAINT_HEADER_STRICT = "【强约束】"
_CONSTRAINT_HEADER_LOOSE = "【参考】"
_GROUNDING_HEADER_STRICT = "【原作设定，必须遵守】"
_GROUNDING_HEADER_LOOSE = "【原作设定，参考】"

# ---------------------------------------------------------------------------
# Helper: stream text collection + JSON extraction
# (mirrors research_pack_builder pattern)
# ---------------------------------------------------------------------------


async def _collect_stream_text(
    llm_router: Any,
    *,
    system: str,
    messages: list[dict],
    max_tokens: int,
    reasoning: bool | None = None,
) -> str:
    """通过 stream_with_tools(tools=[]) 收集纯文本输出。

    ``reasoning`` per-call 覆盖路由默认（None=不覆盖）。规划/约束满足类步骤
    （如 roster 花名册）传 True 重新打开 CoT；批量 JSON 生成步骤保持默认（关）。
    只在显式设置时透传，避免 test fakes / 旧 provider 收到未知 kwarg。
    """
    extra: dict = {"reasoning": reasoning} if reasoning is not None else {}
    parts: list[str] = []
    async for event in llm_router.stream_with_tools(
        messages=messages,
        tools=[],
        system=system,
        max_tokens=max_tokens,
        **extra,
    ):
        if event.get("type") == "text_delta":
            parts.append(event.get("text", ""))
    return "".join(parts).strip()


def _extract_json_from_text(text: str) -> dict | None:
    """从 LLM 返回文本中提取 JSON 对象，兼容 Markdown 代码块包裹。"""
    candidates = [text]
    if "```json" in text:
        for part in text.split("```json")[1:]:
            candidates.append(part.split("```", 1)[0].strip())
    if "{" in text and "}" in text:
        candidates.append(text[text.find("{") : text.rfind("}") + 1])

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            continue
    return None


# ---------------------------------------------------------------------------
# Stage 1: build_character_roster
# ---------------------------------------------------------------------------

_ROSTER_SYSTEM = """你是一个互动叙事世界的人物策划助手。
根据给定的世界描述、题材、时代和 IP 典籍，规划完整的人物花名册（roster）。

输出严格 JSON，格式：
{"roster":[{"name":"人物名","role_tag":"角色定位","faction":"派系（可空）","is_image_target":true/false},...]}

规则（按重要性排序）：
- **完整性第一**：宁可多收，不可漏掉核心角色。一个有名有姓、推动剧情的角色被漏掉，
  比多收一个配角严重得多。下方若给出「必含角色」清单，**清单内每一个都必须出现，缺一即不合格**。
- 人物数量：描述中明确指定数量时按指定数量；否则按题材规模——长篇剧集 / 长篇小说取 **20-30 个**，
  中短篇 / 电影取 **12-18 个**，小品世界 **8-12 个**。把主要 + 次要角色尽量收全，别只给最有名的几个。
- name: 符合世界风格的人物名，优先复用已知原作人名
- role_tag: 简短定位，如"主角"/"宿敌"/"心腹"/"市井小贩"/"神秘客"
- faction: 派系归属，无明确派系可留空字符串
- is_image_target（= 可玩角色）：标给"玩家真正会想扮演、有独立鲜明视角、能撑起一条剧情线的主角级角色"。
  这是**精选的一小撮**，不是"所有重要角色"——和"必含角色 / 完整 roster"是两回事，别混。
  ✅ 设 true：主角、男女主；**主要反派（反派大女主 / BOSS / 派系老大 / 当家主母）**——反派视角是宝贵卖点；
     以及性格鲜明、处境独立、玩家有理由想扮演的关键配角（核心盟友、宿敌、王公、谋士、痴情医者等）。
  ❌ 设 false（他们是让世界鲜活的 NPC，**不是可玩角色**）：侍女 / 丫鬟 / 太监 / 随从 / 低位嫔妃（答应·常在）/
     工具人 / 路人 / 孩童 / 一次性出场。即使有戏份、即使在必含清单里，只要不是"玩家会想扮演的主角级"就设 false。
  数量：**按世界规模浮动，宁缺毋滥**——大 IP 约 10-15 个、中小世界 3-8 个；不设硬上限，但绝不要把半数角色都标可玩。
- 只输出 JSON，不含任何解释文字
"""


def _heuristic_count(description: str) -> int | None:
    """从 description 启发式提取"X 个角色/NPC"中的数量，无则返回 None。"""
    pattern = r"(\d+)\s*个\s*(?:角色|NPC|npc|人物|人)"
    match = re.search(pattern, description)
    if match:
        return int(match.group(1))
    return None


def _norm_name(name: str) -> str:
    """规范化人名用于白名单匹配：去空白与中点。"""
    return re.sub(r"[\s·•・]", "", str(name or "")).strip()


def _prune_to_canon(
    entries: list["CharacterRosterEntry"], ip_pack: IPKnowledgePack
) -> list["CharacterRosterEntry"]:
    """严格复刻：裁掉不在原作白名单（全部 ip_pack 角色名）里的角色，保证 0 原创。

    白名单为空（研究完全失败）时不裁——否则会把强约束注入的原作角色也误删成空
    roster。仅按 _norm_name 精确匹配；prompt 已强制 LLM 用原作名，对不齐的原作角色
    会被记进 dropped 日志供 review 时核（而非静默）。
    """
    canon = {_norm_name(c.name) for c in ip_pack.characters if c.name}
    if not canon:
        return entries
    kept = [e for e in entries if _norm_name(e.name) in canon]
    dropped_names = [e.name for e in entries if _norm_name(e.name) not in canon]
    if dropped_names:
        logger.info(
            "roster_strict_pruned_non_canon",
            ip_name=ip_pack.ip_name,
            kept=len(kept),
            dropped=len(dropped_names),
            dropped_names=dropped_names[:20],
        )
    return kept


def _ensure_must_have(
    entries: list["CharacterRosterEntry"], ip_pack: IPKnowledgePack
) -> list["CharacterRosterEntry"]:
    """硬保证 must_have ⊆ roster：LLM 漏掉的 must_have 角色强制补回。

    与 _prune_to_canon（只删白名单外）配成闭环——删多余 + 补必含。补回的角色用
    ip_pack 里的 role_in_story 作 role_tag，is_image_target=True（must_have 是世界主心骨，
    都应可玩）。后续 character-detail 阶段会按 name 补全 persona / traits。

    这是代码级安全网：不依赖 LLM 是否听话。甄嬛传漏掉皇帝/华妃/皇后的直接修复点。
    """
    existing = {_norm_name(e.name) for e in entries}
    injected: list[str] = []
    for c in ip_pack.characters:
        if not c.must_have:
            continue
        if _norm_name(c.name) in existing:
            continue
        entries.append(CharacterRosterEntry(
            name=c.name,
            role_tag=(c.role_in_story or "主要角色"),
            faction="",
            is_image_target=True,
        ))
        existing.add(_norm_name(c.name))
        injected.append(c.name)
    if injected:
        logger.warning(
            "roster_must_have_force_injected",
            ip_name=ip_pack.ip_name,
            injected=injected,
            roster_size=len(entries),
            reason="llm_dropped_must_have_characters",
        )
    return entries


async def build_character_roster(
    description: str,
    genre: str,
    era: str,
    ip_canon: IPCanon,
    locations: list[Any],
    passages: list[Passage],
    llm_router: Any,
    *,
    ip_pack: IPKnowledgePack | None = None,
    fidelity_mode: FidelityMode = "none",
) -> list[CharacterRosterEntry]:
    """Planner LLM 一次调用，产出人物花名册。

    失败（LLM 异常 / JSON 解析失败）时返回空 list，不抛错。

    T8: When ip_pack is provided AND fidelity_mode is strict/loose, inject the pack's
    must-have characters as hard/soft constraints. fidelity_mode == "none" or
    ip_pack is None falls back to legacy ip_canon behavior.
    """
    # 启发式提取数量提示
    heuristic_n = _heuristic_count(description)
    count_hint = f"请生成恰好 {heuristic_n} 个人物。" if heuristic_n else "根据题材规模生成 12-30 个人物。"

    # 整理 IP 典籍提示（legacy ip_canon path; only used when ip_pack 不参与硬约束）
    canon_hint = ""
    if ip_canon is not None and ip_canon.canonical_names:
        canon_hint = f"\n已知 IP 人名（优先使用）：{', '.join(ip_canon.canonical_names[:20])}"

    # 整理地点提示
    location_names: list[str] = []
    for loc in locations:
        if isinstance(loc, str):
            location_names.append(loc)
        elif hasattr(loc, "name"):
            location_names.append(loc.name)
        elif isinstance(loc, dict):
            location_names.append(loc.get("name", ""))
    loc_hint = f"\n世界地点：{', '.join(location_names)}" if location_names else ""

    user_content = (
        f"世界描述：{description}\n"
        f"题材：{genre}　时代：{era}"
        f"{canon_hint}"
        f"{loc_hint}\n\n"
        f"{count_hint}"
    )

    # T8: IP Pack hard/soft constraint injection
    if ip_pack is not None and fidelity_mode in ("strict", "loose"):
        must_have = ip_pack.must_have_character_names()
        optional = [c.name for c in ip_pack.characters if not c.must_have]
        if must_have:
            if fidelity_mode == "strict":
                user_content += (
                    f"\n\n{_CONSTRAINT_HEADER_STRICT}本世界为「严格复刻」，角色只能用原作角色、"
                    f"name 字段用原作名、**禁止新增任何原创 / 路人 / 工具人角色**。\n"
                    f"⚠️ 必含角色（**以下每一个都必须出现在 roster 里，缺一即不合格**；是否可玩"
                    f"按上面 is_image_target 规则各自判断，别因为必含就全标可玩）：{', '.join(must_have)}\n"
                )
                if optional:
                    user_content += (
                        f"其余原作角色（**尽量全部收进来，别只挑有名的**）：{', '.join(optional)}\n"
                    )
                user_content += "所有角色按原作 traits / relation 设定，勿改名、勿杜撰。\n"
            else:  # loose
                user_content += (
                    f"\n\n{_CONSTRAINT_HEADER_LOOSE}原作核心角色：{', '.join(must_have)}\n"
                    f"优先使用原作角色，可扩展。\n"
                )
        elif optional:  # NEW: pack has only secondary characters
            logger.warning(
                "ip_pack_no_must_have_characters",
                ip_name=ip_pack.ip_name,
                secondary_count=len(optional),
            )
            # Don't inject anything — there's no must-have constraint to enforce

    try:
        # roster 是约束满足/规划任务（读 must_have、规划人数、保证主角在场、分配
        # image_target），per-call 打开 CoT —— admin_generation 槽默认 reasoning-off
        # 是为批量 JSON 生成防截断，对这一步反而伤害约束遵守（甄嬛传漏掉皇帝/华妃/皇后
        # 的直接诱因之一）。批量角色详情阶段（下方 build_characters_in_batches）不传，
        # 保持关。
        # max_tokens 给足：开思考时 reasoning_content 会先吃掉预算（实测大 IP 规划
        # 推理可达 ~8k token），8192 会把后面真正的 roster JSON 挤没 → 吐空 → 0 角色。
        # 抬到 16384，让推理 + 输出都装得下。
        text = await _collect_stream_text(
            llm_router,
            system=_ROSTER_SYSTEM,
            messages=[{"role": "user", "content": user_content}],
            max_tokens=16384,
            reasoning=True,
        )
        data = _extract_json_from_text(text)
        if data is None:
            # 兜底：万一网关因别的原因（连接截断等）仍吐空，降级关思考重试一次
            # （admin_generation 槽默认行为，不堆推理），保证坏网关下也能产出 roster。
            logger.warning(
                "roster_json_parse_failed_retrying_no_reasoning",
                text_preview=text[:300],
            )
            text = await _collect_stream_text(
                llm_router,
                system=_ROSTER_SYSTEM,
                messages=[{"role": "user", "content": user_content}],
                max_tokens=16384,
                reasoning=False,
            )
            data = _extract_json_from_text(text)
        if data is None:
            logger.warning("roster_json_parse_failed", text_preview=text[:300])
            return []

        raw_roster = data.get("roster") or []
        if not isinstance(raw_roster, list):
            logger.warning("roster_invalid_format", data=str(data)[:200])
            return []

        entries: list[CharacterRosterEntry] = []
        for item in raw_roster:
            if not isinstance(item, dict) or not item.get("name"):
                continue
            try:
                entries.append(CharacterRosterEntry(
                    name=item["name"],
                    role_tag=item.get("role_tag", ""),
                    faction=item.get("faction", ""),
                    is_image_target=bool(item.get("is_image_target", False)),
                ))
            except Exception as exc:  # noqa: BLE001
                logger.warning("roster_entry_parse_error", item=item, error=str(exc))

        # 严格复刻：硬裁掉原作白名单外的角色，保证 0 原创（loose 不裁，允许扩展）。
        if fidelity_mode == "strict" and ip_pack is not None:
            entries = _prune_to_canon(entries, ip_pack)
        # 删多余之后补必含：LLM 漏掉的 must_have 强制注入（strict + loose 都跑）。
        if fidelity_mode in ("strict", "loose") and ip_pack is not None:
            entries = _ensure_must_have(entries, ip_pack)
        return entries

    except Exception as exc:  # noqa: BLE001
        logger.warning("roster_build_failed", error=str(exc))
        return []


# ---------------------------------------------------------------------------
# Stage 2: build_characters_in_batches
# ---------------------------------------------------------------------------

_BATCH_SYSTEM = """你是一个互动叙事世界的人物详情撰写助手。
根据给定的世界背景和本批人物的简略信息，为每个 NPC 填写完整人物 schema。

输出严格 JSON，格式：
{"characters":[
  {
    "name":"人物名（必须与 roster 完全一致）",
    "personality":"性格描写（2-3句）",
    "voice_style":"说话方式：自称/称谓、句式、口头禅，附1-2句范例台词（30-80字）；各人嗓音要可区分；若是原作角色须贴合其原作台词口吻",
    "description":"角色简介：背景、动机、关键经历（2-3句）",
    "abilities":["擅长事项或技能1","擅长事项或技能2"],
    "starting_inventory":["随身常用物品1","随身常用物品2"],
    "secret":"人物秘密，可空",
    "knowledge":["掌握的信息1","掌握的信息2"],
    "schedule":{"morning":"地点","afternoon":"地点","evening":"地点","night":"地点"},
    "initial_location":"初始位置（必须是地点列表中已有的地点名）",
    "initial_peer_relations":[
      {"target":"另一NPC名","trust":-10到10整数,"kind":"关系类别如盟友/宿敌"}
    ]
  },
  ...
]}

规则：
- 每个 name 必须与 roster 子集中的名字完全一致，不要改名、不要新增不在列表中的人物
- description / abilities / starting_inventory 对**所有角色**都要写（不只是玩家角色）；
  abilities/inventory 各 1-4 条，平凡 NPC 也要给些日常擅长与随身物（如"算账"/"看人脸色"，"算盘"/"半斤碎银"）
- voice_style 对**所有角色**都要写，要能明显区分各人嗓音、避免千人一腔；
  若世界背景表明基于已知作品（IP 复刻），原作角色的 personality 开头点明身份锚（如「《作品名》中的<角色>」）、voice_style 贴合原作口吻
- initial_location 必须是给定地点列表中的名字；地点列表为空时可用空字符串
- initial_peer_relations 的 target 只能是本批或整个 roster 中已有的 NPC 名（不含玩家角色）
- trust 范围 -10（极度敌对）到 10（生死相托）
- 只输出 JSON，不含任何解释文字

NPC 行为边界（写 personality / description / knowledge 时务必遵守）：
- NPC 是**陪玩 / 反应型角色**，不是导师 / 主持人 / 助教。绝对不要给 NPC 写"会主动测试玩家观察力" /
  "主动指出关键线索" / "适时提示玩家应该注意 X" / "引导玩家发现 Y" / "暗示证据" 这类自驱描述
- knowledge 字段写"这个 NPC 客观知道的事实"，不要写成"会在合适时机告诉玩家的提示清单"。
  揭示线索属于玩家的发现工作，NPC 只在被玩家**明确询问**时给出有限度的回应
- 即使是侦探 / 师爷 / 导师类身份，也只是"专业能力强、被问到时能给出专业判断"，不是
  "看玩家半天没发现就主动抛细节"
"""


def _build_batch_prompt(
    batch: list[CharacterRosterEntry],
    description: str,
    ip_canon: IPCanon,
    location_names: list[str],
    *,
    ip_pack: IPKnowledgePack | None = None,
    fidelity_mode: FidelityMode = "none",
) -> str:
    """为单批构建 user prompt。

    T8: When ip_pack is provided AND fidelity_mode is strict/loose, inject per-character
    grounding info (name, role_in_story, relation, traits) for every batch entry whose
    name matches an IP character. fidelity_mode == "none" or no ip_pack: legacy behavior.
    """
    batch_list = "\n".join(
        f"- {e.name}（{e.role_tag}）{f'  派系：{e.faction}' if e.faction else ''}"
        for e in batch
    )
    loc_str = "、".join(location_names) if location_names else "（无地点约束）"

    canon_hint = ""
    if ip_canon is not None and ip_canon.canonical_names:
        canon_hint = f"\nIP 已知人名（参考）：{', '.join(ip_canon.canonical_names[:20])}"

    prompt = (
        f"世界背景：{description}{canon_hint}\n\n"
        f"可用地点：{loc_str}\n\n"
        f"本批需详写的人物（{len(batch)} 人）：\n{batch_list}\n\n"
    )

    # T8: per-character IP grounding (strict/loose only)
    if ip_pack is not None and fidelity_mode in ("strict", "loose"):
        ip_lookup = {c.name.strip(): c for c in ip_pack.characters}
        grounding_blocks: list[str] = []
        for entry in batch:
            ip_match = ip_lookup.get(entry.name.strip())
            if ip_match is None:
                continue
            traits_str = ", ".join(ip_match.traits) if ip_match.traits else "（参照素材）"
            grounding_blocks.append(
                f"- {ip_match.name}（{ip_match.role_in_story}）\n"
                f"  关系：{ip_match.relation_to_protagonist}\n"
                f"  性格特征：{traits_str}"
            )
        if grounding_blocks:
            header = _GROUNDING_HEADER_STRICT if fidelity_mode == "strict" else _GROUNDING_HEADER_LOOSE
            prompt += f"{header}\n" + "\n".join(grounding_blocks) + "\n\n"

    prompt += "请为以上每个人物输出完整 schema。"
    return prompt


async def _process_batch(
    batch: list[CharacterRosterEntry],
    description: str,
    ip_canon: IPCanon,
    location_names: list[str],
    passages: list[Passage],
    llm_router: Any,
    sem: asyncio.Semaphore,
    *,
    ip_pack: IPKnowledgePack | None = None,
    fidelity_mode: FidelityMode = "none",
) -> list[Character]:
    """处理单批，失败时返回空 list（不传播异常，由 gather return_exceptions 捕获）。"""
    async with sem:
        user_content = _build_batch_prompt(
            batch, description, ip_canon, location_names,
            ip_pack=ip_pack, fidelity_mode=fidelity_mode,
        )

        # 附加 passages 摘录（若有），限制字符数防止 context 过长
        if passages:
            snippets = "\n".join(p.text[:200] for p in passages[:5])
            user_content = f"参考资料节选：\n{snippets}\n\n{user_content}"

        # One-shot retry on JSON parse failure. Pre-2026-05-24 a single bad
        # batch silently dropped its entire character set, and downstream
        # events_data still referenced those names — surfacing as the
        # 嘉靖宫变前夜 character_missing / events_data_invalid_npc_name
        # drift. Retrying once with the same prompt rescues most cases
        # (the LLM's second pass tends to produce valid JSON); persistent
        # failures still return []  and the B1 fail-fast gate
        # (_MIN_CHARACTERS) catches the result.
        text = await _collect_stream_text(
            llm_router,
            system=_BATCH_SYSTEM,
            messages=[{"role": "user", "content": user_content}],
            max_tokens=8192,
        )
        data = _extract_json_from_text(text)
        if data is None:
            logger.warning(
                "batch_json_parse_failed_retrying",
                batch_names=[e.name for e in batch],
                text_preview=text[:300],
            )
            retry_text = await _collect_stream_text(
                llm_router,
                system=_BATCH_SYSTEM,
                messages=[
                    {"role": "user", "content": user_content},
                    {
                        "role": "user",
                        "content": (
                            "上次输出无法解析为 JSON。请只输出合法 JSON 对象，"
                            "不要 markdown 包裹、不要思考标签、不要前导说明。"
                        ),
                    },
                ],
                max_tokens=8192,
            )
            data = _extract_json_from_text(retry_text)
            if data is None:
                logger.warning(
                    "batch_json_parse_failed_final",
                    batch_names=[e.name for e in batch],
                    text_preview=retry_text[:300],
                )
                return []

    raw_chars = data.get("characters") or []
    if not isinstance(raw_chars, list):
        logger.warning("batch_invalid_format", batch_names=[e.name for e in batch])
        return []

    # role_tag / faction / is_image_target 由 roster planner 决定，不能让
    # character-detail LLM 推翻（它常常漏掉这几个字段，导致 is_image_target=False
    # → 下游 playable 选 0 个 → images 阶段只画一张 hero、所有 NPC 头像 = placeholder）。
    roster_lookup = {entry.name.strip(): entry for entry in batch}

    result: list[Character] = []
    for item in raw_chars:
        if not isinstance(item, dict) or not item.get("name"):
            continue
        try:
            relations_raw = item.get("initial_peer_relations") or []
            relations: list[CharacterPeerRelation] = []
            for rel in relations_raw:
                if not isinstance(rel, dict) or not rel.get("target"):
                    continue
                try:
                    relations.append(CharacterPeerRelation(
                        target=rel["target"],
                        trust=int(rel.get("trust", 0)),
                        kind=rel.get("kind", rel.get("label", "")),
                    ))
                except Exception as exc:  # noqa: BLE001
                    logger.warning("batch_relation_parse_error", rel=rel, error=str(exc))

            # Inherit roster planner's authoritative tags. If the LLM happened to
            # echo a non-empty value back we still prefer the planner — planner
            # ran first with the global view, the detail LLM only sees one batch.
            roster_entry = roster_lookup.get(str(item["name"]).strip())
            inherited_role_tag = roster_entry.role_tag if roster_entry else item.get("role_tag", "")
            inherited_faction = roster_entry.faction if roster_entry else item.get("faction", "")
            inherited_image_target = (
                roster_entry.is_image_target if roster_entry
                else bool(item.get("is_image_target", False))
            )

            char = Character(
                name=item["name"],
                role_tag=inherited_role_tag,
                faction=inherited_faction,
                is_image_target=inherited_image_target,
                personality=item.get("personality", ""),
                voice_style=item.get("voice_style", ""),
                secret=item.get("secret", ""),
                knowledge=list(item.get("knowledge") or []),
                schedule=dict(item.get("schedule") or {}),
                initial_location=item.get("initial_location", ""),
                initial_peer_relations=relations,
                description=item.get("description", "") or "",
                abilities=list(item.get("abilities") or []),
                starting_inventory=list(item.get("starting_inventory") or []),
            )
            result.append(char)
        except Exception as exc:  # noqa: BLE001
            logger.warning("batch_char_parse_error", name=item.get("name"), error=str(exc))
    return result


async def build_characters_in_batches(
    roster: list[CharacterRosterEntry],
    description: str,
    ip_canon: IPCanon,
    locations: list[Any],
    passages: list[Passage],
    llm_router: Any,
    *,
    batch_size: int = 6,
    concurrency: int = 4,
    ip_pack: IPKnowledgePack | None = None,
    fidelity_mode: FidelityMode = "none",
) -> list[Character]:
    """将 roster 切批并发 LLM 调用，产出完整 Character 列表。

    - 批后严格 1:1 dedup 校验：extra/missing/duplicate 全部 warn，不补占位
    - 单批失败不阻塞其他批
    - 返回按 roster 顺序排列的 list[Character]
    """
    if not roster:
        return []

    # 提取地点名列表
    location_names: list[str] = []
    for loc in locations:
        if isinstance(loc, str):
            location_names.append(loc)
        elif hasattr(loc, "name"):
            location_names.append(loc.name)
        elif isinstance(loc, dict):
            n = loc.get("name", "")
            if n:
                location_names.append(n)

    # 切批
    batches = [roster[i : i + batch_size] for i in range(0, len(roster), batch_size)]
    sem = asyncio.Semaphore(concurrency)

    # 并发调用，return_exceptions=True 保证单批失败不传播
    results = await asyncio.gather(
        *[
            _process_batch(
                batch, description, ip_canon, location_names, passages, llm_router, sem,
                ip_pack=ip_pack, fidelity_mode=fidelity_mode,
            )
            for batch in batches
        ],
        return_exceptions=True,
    )

    # 展平所有批产物
    all_returned: list[Character] = []
    for i, res in enumerate(results):
        if isinstance(res, Exception):
            batch_names = [e.name for e in batches[i]]
            logger.warning("batch_failed", batch_index=i, batch_names=batch_names, error=str(res))
        else:
            all_returned.extend(res)  # type: ignore[arg-type]

    # dedup 校验：roster name 严格 1:1
    roster_names = [r.name for r in roster]
    roster_set = set(roster_names)
    seen: set[str] = set()
    deduped: list[Character] = []

    for c in all_returned:
        if c.name not in roster_set:
            logger.warning("character_extra_dropped", name=c.name)
            continue
        if c.name in seen:
            logger.warning("character_duplicate_dropped", name=c.name)
            continue
        seen.add(c.name)
        deduped.append(c)

    # 缺失警告
    for n in roster_names:
        if n not in seen:
            logger.warning("character_missing", name=n)

    # 按 roster 顺序排列
    return sorted(deduped, key=lambda c: roster_names.index(c.name))
