"""World-generation quality checker — 生成产物的"尺子"。

两层，与生成上下文解耦，任何 world payload（result_payload / draft payload）都能喂进来：

- ``run_deterministic_checks``：纯代码、零模型成本、高精度。抓 gender 缺失、百科腔
  bio、must-have 缺失、可玩不足、base_setting 过薄、事件禁用率过高等**能确定性判定**
  的缺陷。既做生成内联闸，也做离线回归护栏（pytest / 批量扫描）。
- ``judge_content_quality``：一次 LLM 调用，抓字符串看不见的语义问题——同一剧情节拍被
  换措辞重复、AI 味、正典/时代矛盾、事件是否覆盖整条故事线。是"天花板"那一层的判官。

两层都返回统一的 ``QualityFlag`` 列表，severity 分 blocking / warning。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import structlog

from services.research_pack_builder import (
    _collect_stream_text,
    _extract_json_from_text,
)

logger = structlog.get_logger()


@dataclass
class QualityFlag:
    code: str
    severity: str  # "blocking" | "warning"
    detail: str
    entities: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "code": self.code,
            "severity": self.severity,
            "detail": self.detail,
            "entities": self.entities,
        }


# 元指涉开头：破坏沉浸的百科腔（"《X》中的…"/"本作中的…"/"原作里的…"）
_META_REF = re.compile(r"^\s*[《【]|中的(?:角色|人物|主角|女主|男主|反派)|本作|原著里的|原作里的|该角色")


def _chars(payload: dict) -> list[dict]:
    return [c for c in (payload.get("world_characters") or []) if isinstance(c, dict)]


def _events(payload: dict) -> list[dict]:
    return [e for e in (payload.get("events_data") or []) if isinstance(e, dict)]


# ---------------------------------------------------------------------------
# 第一层：确定性检查（零成本）
# ---------------------------------------------------------------------------


def run_deterministic_checks(
    payload: dict,
    *,
    must_have: list[str] | None = None,
    playable_min: int = 3,
    base_setting_min: int = 400,
) -> list[QualityFlag]:
    flags: list[QualityFlag] = []
    chars = _chars(payload)
    names = {str(c.get("name") or "").strip() for c in chars if c.get("name")}

    # 1. gender 缺失
    no_gender = [str(c.get("name") or "") for c in chars if not str(c.get("gender") or "").strip()]
    if no_gender:
        flags.append(QualityFlag(
            "gender_missing", "warning",
            f"{len(no_gender)}/{len(chars)} 个角色 gender 为空",
            no_gender[:20],
        ))

    # 2. 百科腔 bio（元指涉开头）
    meta = [
        str(c.get("name") or "")
        for c in chars
        if _META_REF.search(str(c.get("personality") or "")[:16])
        or _META_REF.search(str(c.get("description") or "")[:16])
    ]
    if meta:
        flags.append(QualityFlag(
            "meta_referential_bio", "warning",
            f"{len(meta)}/{len(chars)} 个角色 personality/description 是元指涉百科腔（如「《X》中的…」）",
            meta[:20],
        ))

    # 3. must-have 缺失（blocking）
    missing = [n for n in (must_have or []) if n not in names]
    if missing:
        flags.append(QualityFlag(
            "must_have_missing", "blocking",
            f"缺少必含角色：{', '.join(missing)}",
            missing,
        ))

    # 4. 可玩不足（blocking）
    playable = {str(p.get("name") or "").strip() for p in (payload.get("playable") or []) if isinstance(p, dict) and p.get("name")}
    if len(playable) < playable_min:
        flags.append(QualityFlag(
            "playable_below_min", "blocking",
            f"可玩角色 {len(playable)} < 下限 {playable_min}",
        ))

    # 5. base_setting 过薄
    base_len = len(str(payload.get("base_setting") or ""))
    if base_len < base_setting_min:
        flags.append(QualityFlag(
            "base_setting_thin", "warning",
            f"base_setting 仅 {base_len} 字（下限 {base_setting_min}）",
        ))

    # 6. 事件禁用率过高（生成质量信号，非玩家可见但说明模型产出坏）
    events = _events(payload)
    disabled = [e for e in events if e.get("disabled")]
    if events and len(disabled) / len(events) > 0.3:
        flags.append(QualityFlag(
            "high_disabled_event_ratio", "warning",
            f"{len(disabled)}/{len(events)} 个事件被禁用（触发条件/角色引用不合法）",
        ))

    return flags


# ---------------------------------------------------------------------------
# 第二层：语义 judge（一次 LLM 调用）
# ---------------------------------------------------------------------------

_JUDGE_SYSTEM = """你是互动叙事世界的质量审查官。只挑硬伤，不夸奖、不打分排名。
针对给定世界，检查以下问题并**只**输出命中的：

1. event_beat_duplication：多条运行时事件其实是同一个剧情节拍（同一场流产/死亡/出家/
   倒台/身份揭露…），即便换了措辞/视角/地点也算重复。
2. timeline_coverage_gap：事件挤在故事前半段，后半段的关键节拍（如结局走向、势力清算、
   主角命运）在事件里完全没有。
3. ai_smell：角色/设定读起来是套模板、千人一腔、空洞抒情、翻译腔或元指涉百科腔。
4. canon_fidelity：与该 IP 的公认设定/时代/人物关系矛盾（仅在明显冲突时报）。

严格 JSON 输出：
{"flags":[{"code":"上面四类之一","severity":"blocking|warning","detail":"一句话+具体点名哪些条目","entities":["相关 id 或角色名"]}]}
没有问题就输出 {"flags":[]}。不含 markdown。"""


def _judge_projection(payload: dict) -> str:
    """把 payload 压成 judge 需要的最小上下文（事件 summary + 角色 bio 摘要）。"""
    chars = _chars(payload)
    events = _events(payload)
    lines = [f"世界：{payload.get('name')}", f"背景：{str(payload.get('base_setting') or '')[:400]}", "", "运行时事件（按顺序）："]
    for e in events:
        lines.append(f"  [{e.get('id')}] {'(disabled)' if e.get('disabled') else ''}{e.get('summary')}")
    lines.append("")
    lines.append("角色（名｜性格前 40 字）：")
    for c in chars[:36]:
        lines.append(f"  {c.get('name')}｜{str(c.get('personality') or '')[:40]}")
    return "\n".join(lines)


async def judge_content_quality(payload: dict, llm_router: Any) -> list[QualityFlag]:
    """一次 LLM 调用，返回语义质量红旗。LLM 异常/解析失败 → 空列表（不阻断）。"""
    try:
        text = await _collect_stream_text(
            llm_router,
            system=_JUDGE_SYSTEM,
            messages=[{"role": "user", "content": _judge_projection(payload)}],
            max_tokens=2048,
        )
        data = _extract_json_from_text(text) or {}
        out: list[QualityFlag] = []
        for item in data.get("flags") or []:
            if not isinstance(item, dict) or not item.get("code"):
                continue
            out.append(QualityFlag(
                code=str(item.get("code")),
                severity="blocking" if item.get("severity") == "blocking" else "warning",
                detail=str(item.get("detail") or ""),
                entities=[str(x) for x in (item.get("entities") or []) if x],
            ))
        return out
    except Exception as exc:  # noqa: BLE001
        logger.warning("content_quality_judge_failed", error=str(exc))
        return []
