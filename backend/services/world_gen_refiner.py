"""AI 精修引擎 —— 拿已生成世界 payload + 质检意见，做定向内容重写。

产品化自 refine 原型（见 world-creator plan）。设计取舍来自原型实测：

- **检测层用生成时算好的 ``quality_warnings``**，不在精修时实时重跑 judge——judge 有明显
  run-to-run 方差（同一 payload 一次判 3 条硬伤、一次判全清），拿它决定"要不要显示精修
  入口"不可靠。精修以调用方给定的 ``targets`` 为准。
- **每类修订带重试**：原型里 LLM 返回会截断/解析失败（一次小传修订全败、一次全成），
  所以拿不到目标数量就重试。
- **修后复检一次**（确定性 + 一次 judge）附在结果里——单次定向修订不单调，可能修 A 引入
  B（原型里重排事件时序时把因果搞颠倒），复检让调用方/用户看到修完到底什么状态。

纯函数式：输入 payload、输出新 payload + 结构化改动 + 复检结果。读写 draft、推 SSE、
存撤销快照都由任务层负责。
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

import structlog

from services.research_pack_builder import _collect_stream_text, _extract_json_from_text
from services.world_gen_quality_check import (
    QualityFlag,
    judge_content_quality,
    run_deterministic_checks,
)

logger = structlog.get_logger()

# warning code → 修订通道
_EVENT_CODES = {"event_beat_duplication", "timeline_coverage_gap", "canon_fidelity"}
_BIO_CODES = {"ai_smell", "canon_fidelity"}

# 语义类质检 code（judge 产出）。刷新 quality_warnings 时给这些加回 judge_ 前缀，
# 与生成阶段的落库格式一致；确定性检查（gender_missing 等）不加前缀。
REFINABLE_JUDGE_CODES = {"event_beat_duplication", "timeline_coverage_gap", "canon_fidelity", "ai_smell"}

ProgressCb = Callable[[str, str], Awaitable[None]]


@dataclass
class RefineChange:
    kind: str  # "events" | "characters"
    entity: str  # event id / 角色名
    field: str  # "summary" | "personality" | "voice_style"
    before: str
    after: str

    def as_dict(self) -> dict:
        return {"kind": self.kind, "entity": self.entity, "field": self.field,
                "before": self.before, "after": self.after}


@dataclass
class RefineResult:
    changed: bool
    payload: dict
    changes: list[RefineChange] = field(default_factory=list)
    rechecked: list[QualityFlag] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "changed": self.changed,
            "changes": [c.as_dict() for c in self.changes],
            "rechecked": [f.as_dict() for f in self.rechecked],
        }


_EVENT_FIX_SYSTEM = """你是互动叙事世界的剧情线医生。给你一个世界的运行时事件序列（每条 id + 一句
summary）、一份"标准时间线锚"和"质检意见"。只修语义与顺序，产出修订后的**同一批 id** 的事件
序列，必须复用全部 id、一个不少：
1. 严格按故事时间先后排列，绝不把前期节拍排在后期之后；
2. 质检指出后半段关键节拍缺失时，把重复/错位的事件槽位**改写**成那些缺失的后期节拍；
3. 修正与该作品公认设定/时代/人物关系冲突之处；
4. 每条 summary 用具体专名与因果，不写空泛套话、不含任何英文。
严格 JSON：{"events":[{"id":"evt_001","summary":"..."}]}，按最终时序排列。只输出 JSON。"""

_BIO_FIX_SYSTEM = """你是人物小传编辑。给你一批角色的 personality 与 voice_style 及质检意见。逐个
重写：①去掉套话（外柔内刚/城府极深/重情重义/秀美绝俗 等空泛形容），换成该角色独有、贴原著的
具体性格动机；②删除任何英文单词；③voice_style 给口吻描述 + 一句范例台词。
严格 JSON：{"characters":[{"name":"...","personality":"...","voice_style":"..."}]}。只输出 JSON。"""


async def _call_json(
    llm: Any, system: str, user: str, key: str, want: int, max_tokens: int, tries: int = 3
) -> list:
    """带重试的严格 JSON 调用：返回 list 达到 want 才算成功，否则取历次最优。"""
    best: list = []
    for _ in range(tries):
        try:
            text = await _collect_stream_text(
                llm, system=system, messages=[{"role": "user", "content": user}], max_tokens=max_tokens
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("refine_llm_call_failed", error=str(exc))
            continue
        data = _extract_json_from_text(text) or {}
        lst = data.get(key) or []
        if len(lst) > len(best):
            best = lst
        if len(lst) >= want:
            return lst
    return best


def _matched_details(payload: dict, targets: set[str]) -> str:
    """从 quality_warnings 里取命中 targets 的意见文本，拼成 directive。"""
    warns = payload.get("quality_warnings") or []
    parts = []
    for w in warns:
        if not isinstance(w, dict):
            continue  # quality_warnings 混有 moderation_flag 之类的纯字符串标记，跳过
        code = str(w.get("code") or "").removeprefix("judge_")
        if code in targets:
            msg = str(w.get("message") or w.get("detail") or "")
            if msg:
                parts.append(msg)
    return "；".join(parts)[:800]


async def _refine_events(payload: dict, directive: str, llm: Any) -> list[RefineChange]:
    events = [e for e in (payload.get("events_data") or []) if isinstance(e, dict)]
    if not events:
        return []
    shared = payload.get("shared_events") or []
    anchor = "\n".join(
        f"- {e.get('title') or (e.get('summary') or '')[:30]}" for e in shared[:20] if isinstance(e, dict)
    )
    user = json.dumps(
        {
            "世界": payload.get("name"),
            "现有事件": [{"id": e.get("id"), "summary": e.get("summary")} for e in events],
            "标准时间线锚": anchor,
            "质检意见": directive,
        },
        ensure_ascii=False,
    )
    ev_list = await _call_json(llm, _EVENT_FIX_SYSTEM, user, "events", want=len(events), max_tokens=4096)
    id2new = {x.get("id"): x.get("summary") for x in ev_list if isinstance(x, dict) and x.get("id")}
    by_id = {e.get("id"): e for e in events}
    order = [x.get("id") for x in ev_list if isinstance(x, dict) and x.get("id") in by_id]

    changes: list[RefineChange] = []
    new_events: list[dict] = []
    for eid in order:
        old = by_id[eid]
        new = dict(old)
        new_summary = id2new.get(eid)
        if new_summary and new_summary != old.get("summary"):
            changes.append(RefineChange("events", eid, "summary", old.get("summary") or "", new_summary))
            new["summary"] = new_summary
        new_events.append(new)
    for e in events:  # 补齐 LLM 漏掉的 id，保序骨架不丢
        if e.get("id") not in {ne.get("id") for ne in new_events}:
            new_events.append(dict(e))
    payload["events_data"] = new_events
    return changes


async def _refine_bios(payload: dict, directive: str, llm: Any) -> list[RefineChange]:
    chars = [c for c in (payload.get("world_characters") or []) if isinstance(c, dict)]
    if not chars:
        return []
    user = json.dumps(
        {
            "角色": [
                {"name": c.get("name"), "personality": c.get("personality"), "voice_style": c.get("voice_style")}
                for c in chars
            ],
            "质检意见": directive,
        },
        ensure_ascii=False,
    )
    bio_list = await _call_json(llm, _BIO_FIX_SYSTEM, user, "characters", want=len(chars), max_tokens=8192)
    name2 = {x.get("name"): x for x in bio_list if isinstance(x, dict) and x.get("name")}

    changes: list[RefineChange] = []
    for c in chars:
        nb = name2.get(c.get("name"))
        if not nb:
            continue
        for fld in ("personality", "voice_style"):
            new_val = nb.get(fld)
            if new_val and new_val != (c.get(fld) or ""):
                changes.append(RefineChange("characters", c.get("name"), fld, c.get(fld) or "", new_val))
                c[fld] = new_val
    payload["world_characters"] = chars
    return changes


async def refine_world_payload(
    payload: dict,
    *,
    targets: list[str],
    llm_router: Any,
    progress: ProgressCb | None = None,
) -> RefineResult:
    """对 world payload 做定向精修。返回新 payload（原地修改的拷贝）+ 改动 + 复检结果。

    ``targets`` 为要修的 warning code 列表（如 ["timeline_coverage_gap","ai_smell"]）；空则从
    payload 的 quality_warnings 推断全部可修项。
    """
    payload = json.loads(json.dumps(payload))  # 深拷贝，不动入参
    target_set = set(targets)
    if not target_set:
        for w in payload.get("quality_warnings") or []:
            if isinstance(w, dict):  # 跳过 moderation_flag 之类的纯字符串标记
                target_set.add(str(w.get("code") or "").removeprefix("judge_"))

    async def _emit(code: str, msg: str) -> None:
        if progress:
            await progress(code, msg)

    changes: list[RefineChange] = []

    # 事件重排改 events_data、小传改 world_characters，互不依赖 —— 并行跑，砍掉一次串行 LLM 往返。
    # directive 依赖精修前的 quality_warnings，必须在 gather 前算好（两个协程会各自改 payload 的不同 key）。
    do_events = bool(target_set & _EVENT_CODES)
    do_bios = bool(target_set & _BIO_CODES & {"ai_smell"})

    if do_events and do_bios:
        await _emit("refining", "正在并行重排事件时序、重写角色小传…")
    elif do_events:
        await _emit("events_refining", "正在重排事件时序、补齐缺失节拍…")
    elif do_bios:
        await _emit("bios_refining", "正在重写角色小传、去套路化…")

    jobs: list[Awaitable[list[RefineChange]]] = []
    if do_events:
        ev_directive = _matched_details(payload, target_set & _EVENT_CODES) or "理顺事件时序、补齐后半段缺失节拍、修正与原著冲突处"
        jobs.append(_refine_events(payload, ev_directive, llm_router))
    if do_bios:
        bio_directive = _matched_details(payload, {"ai_smell"}) or "去掉模板化套话、删除英文、写具体贴原著的性格"
        jobs.append(_refine_bios(payload, bio_directive, llm_router))

    if jobs:
        for part in await asyncio.gather(*jobs):
            changes += part

    # 修后复检一次：确定性 + 一次 judge（judge 失败降级为空，不阻塞）
    await _emit("rechecking", "正在复检修订结果…")
    rechecked: list[QualityFlag] = []
    try:
        rechecked += run_deterministic_checks(
            payload,
            must_have=[c.get("name", "") for c in (payload.get("world_characters") or [])][:8],
            playable_min=3,
        )
        rechecked += await judge_content_quality(payload, llm_router)
    except Exception as exc:  # noqa: BLE001
        logger.warning("refine_recheck_failed", error=str(exc))

    # 用复检结果刷新 quality_warnings，否则前端质检条会一直显示已修好的旧告警。
    # 内容审核标记（moderation_flag 之类的纯字符串）精修不碰，原样保留；
    # 语义 + 确定性告警整体替换为本次复检后的真实状态。
    if changes:
        kept: list[Any] = [w for w in (payload.get("quality_warnings") or []) if isinstance(w, str)]
        for f in rechecked:
            kept.append({
                "code": f"judge_{f.code}" if f.code in REFINABLE_JUDGE_CODES else f.code,
                "severity": f.severity,
                "message": f.detail,
                "meta": {"message": f.detail},
            })
        payload["quality_warnings"] = kept

    return RefineResult(changed=bool(changes), payload=payload, changes=changes, rechecked=rechecked)
