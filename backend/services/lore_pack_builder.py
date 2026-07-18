"""LorePack builder — lore 维度规划 + 批量内容生成。

两个公共函数：
- build_lore_dimensions: planner LLM 一次调用，输出 2-6 个 lore 维度清单
- build_lore_pack: 常态一次生成全部维度正文，缺项时只补缺失 key

LLMRouter API 说明：
  只暴露 stream_with_tools(messages, tools, system, max_tokens)。
  本文件复用 services.research_pack_builder 里的两个 helper：
  _collect_stream_text / _extract_json_from_text。
"""
import asyncio
from datetime import datetime, timezone
from typing import Any

import structlog

from schemas.ip_knowledge_pack import FidelityMode, IPKnowledgePack
from schemas.lore_pack import (
    LoreContentBlock,
    LoreDimension,
    LoreDimensionContent,
    LorePack,
)
from schemas.research_pack import IPCanon, Passage
from schemas.world_generation import WorldScalePlan
from services.research_pack_builder import (
    _collect_stream_text,
    _extract_json_from_text,
)

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Prompt 模板（内联，不改 generation_prompt_builder.py）
# ---------------------------------------------------------------------------

_DIMENSIONS_SYSTEM = """你是一个世界构建专家，负责规划世界观的关键 lore 维度。

给你一段世界描述，以及可选的题材、时代、IP 信息，请识别出对该世界最有意义的 lore 维度清单。

每个维度包含：
- key: 机器可读的英文标识符，如 "tech_levels"、"faction_politics"
- name: 人类可读的中文名称，如 "技术等级"、"派系政治"
- why_relevant: 一句话说明为什么这个维度对该世界有意义

要求：
- **当用户提供了具体的 IP 名（例如《XX》/影视剧/小说/动漫/游戏）或已识别出 IP 上下文时，你必须输出至少 3 个维度**（典型如：势力派系 / 历史背景 / 地理风貌 / 修炼或科技体系 / 标志性器物 等），不允许空输出
- 仅在用户描述完全是纯抽象、纯日常、或纯原创轻量场景且无 IP 上下文时，才可考虑输出 ≤ 2 个维度
- 维度上限 6 个，避免冗余
- 严格 JSON 输出，不包含解释文字
- 格式：{"dimensions": [{"key": "...", "name": "...", "why_relevant": "..."}]}"""

_DIMENSION_CONTENT_SYSTEM = """你是一个世界构建专家，负责为特定的 lore 维度生成详细内容。

给你一个 lore 维度的信息以及世界描述，请生成该维度的详细内容块。

每个内容块包含：
- heading: 小标题
- body: 详细描述（2-5 句话）

要求：
- 输出 2-4 个内容块
- 内容要具体、有世界感，适合作为世界设定参考
- 严格 JSON 输出，不包含解释文字
- 格式：{"content_blocks": [{"heading": "...", "body": "..."}]}"""

_DIMENSION_BATCH_SYSTEM = """你是一个世界构建专家。一次为给定的全部 lore 维度生成内容。

要求：
- 每个输入 key 恰好返回一项，不得改名或遗漏
- 每个维度输出 2-4 个 content_blocks，每块含 heading 和 2-5 句话的 body
- 各维度职责分明，不重复抄写同一段设定
- 严格 JSON，不含 markdown
- 格式：{"dimensions":[{"key":"输入 key","content_blocks":[{"heading":"...","body":"..."}]}]}"""


# ---------------------------------------------------------------------------
# build_lore_dimensions
# ---------------------------------------------------------------------------


async def build_lore_dimensions(
    description: str,
    genre: str,
    era: str,
    ip_canon: IPCanon,
    llm_router: Any,
    *,
    ip_pack: IPKnowledgePack | None = None,
    fidelity_mode: FidelityMode = "none",
    scale_plan: WorldScalePlan | None = None,
) -> list[LoreDimension]:
    """Planner LLM 一次调用，识别出 2-6 个 lore 维度。

    失败（LLM 异常 / JSON 解析失败）→ 返回空 list，不抛错。

    T8/Phase 2: 当 ip_pack 可用且 fidelity_mode 为 strict/loose 时，把已识别的 IP
    名、原作摘要、核心角色 / 派系 / 地点等注入到 user prompt，让 planner 知道
    "这是一个复刻 IP 世界，必须给出 ≥3 个 lore 维度"。无 ip_pack 时回落到 legacy
    ip_canon 行为。
    """
    title_hints = ", ".join(ip_canon.title_guesses) if ip_canon.title_guesses else "（无已知 IP）"
    canon_names = ", ".join(ip_canon.canonical_names) if ip_canon.canonical_names else "（无）"

    user_message = (
        f"世界描述：{description}\n"
        f"题材：{genre or '未指定'}\n"
        f"时代：{era or '未指定'}\n"
        f"可能的 IP / 作品：{title_hints}\n"
        f"标志性人名：{canon_names}\n"
    )

    # Phase 2: inject IP pack context so planner has a concrete anchor
    if ip_pack is not None and fidelity_mode in ("strict", "loose"):
        summary_excerpt = (ip_pack.summary or "").strip()[:500]
        char_names = [c.name for c in ip_pack.canon_characters()[:8] if getattr(c, "name", "")]
        place_names = [p.name for p in ip_pack.places[:8] if getattr(p, "name", "")]
        faction_names = [f.name for f in ip_pack.factions[:8] if getattr(f, "name", "")]
        object_names = [o.name for o in ip_pack.iconic_objects[:8] if getattr(o, "name", "")]
        event_names = [e.name for e in ip_pack.key_events[:8] if getattr(e, "name", "")]

        ip_block = (
            f"\n=== 已识别 IP 上下文（fidelity={fidelity_mode}）===\n"
            f"IP 名：{ip_pack.ip_name}（{ip_pack.ip_type}）\n"
        )
        if summary_excerpt:
            ip_block += f"原作摘要：{summary_excerpt}\n"
        if char_names:
            ip_block += f"核心角色：{', '.join(char_names)}\n"
        if place_names:
            ip_block += f"标志性地点：{', '.join(place_names)}\n"
        if faction_names:
            ip_block += f"派系势力：{', '.join(faction_names)}\n"
        if object_names:
            ip_block += f"标志性器物：{', '.join(object_names)}\n"
        if event_names:
            ip_block += f"关键事件：{', '.join(event_names)}\n"
        ip_block += (
            "提示：以上属于真实存在的 IP 世界，**必须输出至少 3 个 lore 维度**，"
            "覆盖角色背后的势力 / 历史 / 地理 / 修炼或科技体系 / 标志性器物 等设定。\n"
        )
        user_message += ip_block

    if scale_plan is not None:
        target_band = {
            "compact": "2-3",
            "standard": "3-4",
            "epic": "4-5",
        }[scale_plan.scale_class.value]
        user_message += (
            f"\nWorldSpec 规模为 {scale_plan.scale_class.value}，"
            f"请规划 {target_band} 个真正必要的维度。"
        )

    user_message += "\n请输出适合该世界的 lore 维度清单（JSON 格式）。"

    try:
        text = await _collect_stream_text(
            llm_router,
            system=_DIMENSIONS_SYSTEM,
            messages=[{"role": "user", "content": user_message}],
            max_tokens=1024,
        )
        data = _extract_json_from_text(text)
        if data is None:
            logger.warning("lore_dimensions_json_parse_failed", text_preview=text[:200])
            return []

        raw_dims = data.get("dimensions")
        if not isinstance(raw_dims, list):
            logger.warning("lore_dimensions_unexpected_format", data=data)
            return []

        result: list[LoreDimension] = []
        for item in raw_dims:
            if not isinstance(item, dict):
                continue
            try:
                result.append(
                    LoreDimension(
                        key=item.get("key", ""),
                        name=item.get("name", ""),
                        why_relevant=item.get("why_relevant", ""),
                    )
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("lore_dimension_item_invalid", error=str(exc), item=item)

        return result

    except Exception as exc:  # noqa: BLE001
        logger.warning("lore_dimensions_failed", error=str(exc))
        return []


# ---------------------------------------------------------------------------
# build_lore_pack
# ---------------------------------------------------------------------------


def _match_passages_for_dimension(
    dimension: LoreDimension,
    passages: list[Passage],
    max_passages: int = 8,
) -> list[Passage]:
    """从 passages 中过滤与该维度 key 关键词匹配的段落（最多 max_passages 条）。

    简单字符串子串匹配：dimension.key 的各部分词汇出现在 passage.text 中。
    找不到时返回空列表。
    """
    keywords = [kw.lower() for kw in dimension.key.split("_") if len(kw) > 2]
    if not keywords:
        return []

    matched: list[Passage] = []
    for p in passages:
        text_lower = p.text.lower()
        if any(kw in text_lower for kw in keywords):
            matched.append(p)
            if len(matched) >= max_passages:
                break
    return matched


async def _build_single_dimension_content(
    dimension: LoreDimension,
    description: str,
    ip_canon: IPCanon,
    passages: list[Passage],
    llm_router: Any,
    semaphore: asyncio.Semaphore,
) -> LoreDimensionContent:
    """单个维度的内容生成，受 Semaphore 控制并发。

    LLM 异常 / JSON 解析失败 → content_blocks 为空，记 warning，不抛错。
    """
    matched = _match_passages_for_dimension(dimension, passages)
    passages_text = ""
    if matched:
        passages_text = "\n\n参考资料：\n" + "\n---\n".join(p.text for p in matched)

    title_hints = ", ".join(ip_canon.title_guesses) if ip_canon.title_guesses else ""
    ip_hint = f"\n已知 IP / 作品：{title_hints}" if title_hints else ""

    user_message = (
        f"维度 key：{dimension.key}\n"
        f"维度名称：{dimension.name}\n"
        f"相关理由：{dimension.why_relevant}\n\n"
        f"世界描述：{description}{ip_hint}{passages_text}\n\n"
        "请为该维度生成详细内容块（JSON 格式）。"
    )

    async with semaphore:
        try:
            text = await _collect_stream_text(
                llm_router,
                system=_DIMENSION_CONTENT_SYSTEM,
                messages=[{"role": "user", "content": user_message}],
                max_tokens=2048,
            )
            data = _extract_json_from_text(text)
            if data is None:
                logger.warning(
                    "lore_dimension_content_json_failed",
                    dimension_key=dimension.key,
                    text_preview=text[:200],
                )
                return LoreDimensionContent(key=dimension.key, name=dimension.name)

            raw_blocks = data.get("content_blocks")
            if not isinstance(raw_blocks, list):
                logger.warning(
                    "lore_dimension_content_unexpected_format",
                    dimension_key=dimension.key,
                    data=data,
                )
                return LoreDimensionContent(key=dimension.key, name=dimension.name)

            content_blocks: list[LoreContentBlock] = []
            for block in raw_blocks:
                if not isinstance(block, dict):
                    continue
                try:
                    content_blocks.append(
                        LoreContentBlock(
                            heading=block.get("heading", ""),
                            body=block.get("body", ""),
                        )
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "lore_content_block_invalid",
                        dimension_key=dimension.key,
                        error=str(exc),
                    )

            return LoreDimensionContent(
                key=dimension.key,
                name=dimension.name,
                content_blocks=content_blocks,
            )

        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "lore_dimension_content_failed",
                dimension_key=dimension.key,
                error=str(exc),
            )
            return LoreDimensionContent(key=dimension.key, name=dimension.name)


async def build_lore_pack(
    dimensions: list[LoreDimension],
    description: str,
    ip_canon: IPCanon,
    passages: list[Passage],
    llm_router: Any,
    *,
    concurrency: int = 4,
) -> LorePack:
    """Generate all lore dimensions in one normal-path call.

    A missing-only retry is allowed once, so one malformed dimension does not
    force four independent normal calls or discard the healthy dimensions.
    ``concurrency`` remains in the signature for caller compatibility.
    """
    if not dimensions:
        return LorePack(
            dimensions=[],
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

    del concurrency
    by_key = {dim.key: dim for dim in dimensions}
    content_by_key: dict[str, LoreDimensionContent] = {}

    async def generate(targets: list[LoreDimension], *, retry: bool) -> None:
        evidence = "\n\n".join(
            passage.text for passage in passages[:12] if passage.text
        )
        prompt = (
            f"世界描述：{description}\n"
            f"IP/作品：{', '.join(ip_canon.title_guesses[:2]) or '无'}\n"
            f"维度清单：{[dim.model_dump() for dim in targets]}\n"
            f"参考资料：{evidence[:10000] or '无'}\n"
            + ("上次有维度缺失；本次只补这些 key。\n" if retry else "")
            + "请输出严格 JSON。"
        )
        try:
            text = await _collect_stream_text(
                llm_router,
                system=_DIMENSION_BATCH_SYSTEM,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=8192,
            )
            data = _extract_json_from_text(text) or {}
            items = data.get("dimensions") or []
            if not isinstance(items, list):
                return
            for item in items:
                if not isinstance(item, dict):
                    continue
                key = str(item.get("key") or "")
                dim = by_key.get(key)
                if dim is None:
                    continue
                blocks: list[LoreContentBlock] = []
                for raw in item.get("content_blocks") or []:
                    if not isinstance(raw, dict):
                        continue
                    try:
                        blocks.append(
                            LoreContentBlock(
                                heading=raw.get("heading", ""),
                                body=raw.get("body", ""),
                            )
                        )
                    except Exception as exc:  # noqa: BLE001
                        logger.warning(
                            "lore_content_block_invalid",
                            dimension_key=key,
                            error=str(exc),
                        )
                if blocks:
                    content_by_key[key] = LoreDimensionContent(
                        key=key,
                        name=dim.name,
                        content_blocks=blocks,
                    )
        except Exception as exc:  # noqa: BLE001
            logger.warning("lore_dimension_batch_failed", retry=retry, error=str(exc))

    await generate(dimensions, retry=False)
    missing = [dim for dim in dimensions if dim.key not in content_by_key]
    if missing:
        await generate(missing, retry=True)

    dimension_contents = [
        content_by_key.get(dim.key, LoreDimensionContent(key=dim.key, name=dim.name))
        for dim in dimensions
    ]

    return LorePack(
        dimensions=dimension_contents,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
