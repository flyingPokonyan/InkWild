# IP Fidelity Engine — Phase 2.0 + 2.1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Phase 2.0 修 lore_pack/shared_events/relations_pack 真空 bug；Phase 2.1 引入 Grok web_search + 百度百科直抓作 IP Pack 主源，把逐玉的 must_have 角色从 2 个升到 8+，places 从 0 升到 5+。

**Architecture:** Phase 2.0 是诊断+修 bug，三个 builder 各自独立。Phase 2.1 在 IP Research pipeline 现有 wikipedia + tavily_site 之外新增 Grok 主搜索（一次 LLM call 拿结构化清单 + 4 citations）+ 百度百科直抓（角色页 RAG passages），流程从 2 步升级为 4 步（搜索 → 解析候选 → 多源深抓 → 抽取自检）。

**Tech Stack:** Python 3.12 / FastAPI / async / Pydantic v2 / structlog / xAI SDK (已通过 backend.llm.grok 集成) / httpx / BeautifulSoup4

**Spec:** [`docs/superpowers/specs/2026-05-14-ip-fidelity-phase2-design.md`](../specs/2026-05-14-ip-fidelity-phase2-design.md)

**Out of Phase 2.0+2.1 scope** (留给后续子 phase)：
- 防线 1/2/3/4（structured output / two-step / 分层 prompt / 双轨 critic）→ Phase 2.2/2.5
- Schema 扩展（Location 2→8 字段、NPC 5→9 字段）→ Phase 2.3
- lore_pack 接 IP Pack（IP-aware lore）→ Phase 2.4
- SSE 子事件 + 前端展示 → Phase 2.6
- 5 IP 验收套件 → Phase 2.7

---

## File Structure

### 新增

| 文件 | 责任 |
|---|---|
| `backend/services/ip_pack_extractors/grok_search.py` | 包 GrokProvider.web_search，输出 list[Passage] + extract candidate character names |
| `backend/services/ip_pack_extractors/baidu_baike.py` | 抓百度百科剧主页 + 角色页 |
| `backend/tests/test_grok_search_extractor.py` | mock Grok provider 测试 |
| `backend/tests/test_baidu_baike_extractor.py` | 真实 httpx fixture 测试 |

### 修改

| 文件 | 变更 |
|---|---|
| `backend/services/lore_pack_builder.py` | 诊断 + 修 dimensions=[] 落地 bug |
| `backend/services/shared_events_builder.py` | 诊断 + 修持久化（事件 0 个问题） |
| `backend/services/relations_pack_builder.py` | 诊断 + 修持久化（null 问题） |
| `backend/services/world_creator_agent_v2.py` | `_run_lore_pack` / `_run_shared_events` / `_run_relations_pack` 落 intermediate_state 检查 |
| `backend/schemas/ip_knowledge_pack.py` | 加 `IPCharacter.voice_style`、`IPCharacter.story_arc`、`IPPlace.faction_owner`、`IPKnowledgePack.timeline` 四个 optional 字段 |
| `backend/services/ip_research_pipeline.py` | 4 步流程升级：Grok 主搜索 → 解析候选 → 多源深抓 → 抽取自检 4 维度 |

---

# Phase 2.0：修 lore_pack / shared_events / relations_pack 真空 bug

## Task 1：诊断并修 lore_pack.dimensions=[] 落地 bug

**症状**：generation_task_events 表能看到 `lore_pack stage` 跑了 4-5 个 subtask_completed (dim:power_structure / cultivation_system / historical_background / geography 等)，但 `intermediate_state.lore_pack.dimensions = []`。

**Files:**
- Read: `backend/services/lore_pack_builder.py` (函数 `build_lore_pack` 在 L249，`build_lore_dimensions` 在 L71，`_build_single_dimension_content` 在 L162)
- Read: `backend/services/world_creator_agent_v2.py` (`_run_lore_pack` 方法，前面已被 Phase 1 task 改过；找 `self._last_lore_pack` 设值的地方)
- Read: `backend/schemas/lore_pack.py` (LorePack / Dimension schemas)
- Modify: 找到 bug 的那个文件

- [ ] **Step 1: 用最近一个 succeeded 逐玉草稿做调试样本，跑 build_lore_pack 看返回值**

```bash
docker exec talealive-backend-noreload python -c "
import asyncio, json
from sqlalchemy import select

async def main():
    from database import async_session
    from models.generation_task import GenerationTask

    async with async_session() as db:
        # 拉最近一个 succeeded phase_b task
        result = await db.execute(
            select(GenerationTask)
            .where(GenerationTask.status == 'succeeded')
            .where(GenerationTask.request_payload['phase'].astext == 'phase_b')
            .order_by(GenerationTask.created_at.desc())
            .limit(1)
        )
        task = result.scalar_one_or_none()
        if not task:
            print('NO PHASE_B TASK')
            return
        print(f'Task: {task.id}')
        print(f'intermediate_state keys: {list((task.intermediate_state or {}).keys())}')
        lp = (task.intermediate_state or {}).get('lore_pack')
        print(f'lore_pack: {json.dumps(lp, ensure_ascii=False, indent=2)[:500] if lp else \"NONE\"}')

asyncio.run(main())
"
```
Expected: 确认 lore_pack.dimensions 真的是 []，然后看 generation_task_events 表里 lore_pack stage 的 subtask_completed 数量。

- [ ] **Step 2: 跟踪 build_lore_pack 在 lore_pack_builder.py:249 的内部行为**

Read `services/lore_pack_builder.py:249` (`build_lore_pack`)，找出 dimensions 是如何从 `build_lore_dimensions` (L71) + `_build_single_dimension_content` (L162) 的结果累积到最终返回值的。

特别注意：
- 每个 sub-task 失败时是否被静默 skip（return None / [] / 抛异常）
- `concurrency` 参数（lore_pack 用了 asyncio.gather）是否用了 `return_exceptions=True`，异常 dimension 是否被过滤掉但其他正常 dimension 也丢了
- 返回值如何 wrap 成 `LorePack(dimensions=[...])`

Possible root causes (一个个排查):
- A) `_build_single_dimension_content` 返回 `Dimension(content_blocks=[])` 时被 `build_lore_pack` 视为"失败" → 整个 dimension 丢
- B) `build_lore_pack` 的 dimensions list 累积时用 `if r.content_blocks:` 这种条件过滤掉空 blocks 的整条 dimension
- C) `world_creator_agent_v2._run_lore_pack` 的 `self._record_intermediate("lore_pack", pack.model_dump())` 写入时 `pack.model_dump()` 出错或被覆盖
- D) `_record_intermediate` 实现层 bug

- [ ] **Step 3: 加诊断日志临时定位**

在 `services/lore_pack_builder.py` `build_lore_pack` 开头和末尾各加一行 structlog warning（**临时调试，定位后删除**）：

```python
logger.warning("lore_pack_build_start", dimension_count_input=len(dimensions))
# ... 现有代码 ...
logger.warning("lore_pack_build_end", final_dimension_count=len(pack.dimensions),
               content_blocks_per_dim=[len(d.content_blocks) for d in pack.dimensions])
```

同理 `services/world_creator_agent_v2.py:_run_lore_pack` 的 `await self._record_intermediate(...)` 调用前后加诊断：

```python
logger.warning("lore_pack_about_to_persist", dim_count=len(pack.dimensions),
               serialized_size=len(json.dumps(pack.model_dump())))
```

重启 backend 让它生效（noreload container 需要手动 `docker restart talealive-backend-noreload`），或者直接在 container 内重载（取决于现状）。

- [ ] **Step 4: 触发一次生成观察 log 找根因**

走 admin UI 重新创建一个 draft "影视剧 逐玉" → strict（或用 curl 调 continue-generation 复用已有 phase_a task）。跑完看 backend log：

```bash
docker logs --since 5m talealive-backend-noreload 2>&1 | grep -E "(lore_pack|dimension)"
```

定位根因。

- [ ] **Step 5: 修 bug**

根据 Step 4 的发现做最小定向修复。Common fix 候选：

**如果根因是 A/B（builder 内部过滤了空 dimension）**：把 `if r.content_blocks:` 条件去掉，保留所有 dimension。warning 标记空 dimension 即可。

```python
# 改前 (推测):
if r and r.content_blocks:
    final_dimensions.append(r)

# 改后:
if r is None:
    logger.warning("lore_pack_dim_returned_none", key=plan.key)
    continue
if not r.content_blocks:
    logger.warning("lore_pack_dim_empty_blocks", key=plan.key)
# 仍然加入，让上层看到
final_dimensions.append(r)
```

**如果根因是 C（`pack.model_dump` 数据丢）**：检查 Pydantic v2 model_dump 配置（mode="python" vs "json"）。可能 nested Dimension model 序列化丢了内容。

**如果根因是 D（`_record_intermediate` 被覆盖）**：grep `_record_intermediate("lore_pack"` 看是否被后续调用覆盖（比如多次调用，后调用传空）。

- [ ] **Step 6: 删除 Step 3 加的临时诊断日志**

- [ ] **Step 7: 跑现有 unit tests 确认没破坏**

```bash
docker exec talealive-backend-noreload python -m pytest tests/test_lore_pack_builder.py tests/test_world_creator_v2_pipeline.py -v 2>&1 | tail -20
```
Expected: 全 pass。

- [ ] **Step 8: 重跑逐玉生成验证 lore_pack 不再为空**

通过 admin UI 或 curl 创建新 draft → strict → 跑完后查：

```bash
docker exec talealive-db-1 psql -U postgres -d talealive -c "
SELECT
  jsonb_array_length((intermediate_state::text)::jsonb -> 'lore_pack' -> 'dimensions') AS dim_count
FROM generation_tasks
WHERE request_payload->>'phase' = 'phase_b' AND status = 'succeeded'
ORDER BY created_at DESC LIMIT 1;"
```
Expected: dim_count ≥ 4

---

## Task 2：修 shared_events 持久化（实测 0 个事件）

**症状**：generation_task_events 表显示 shared_events stage 跑了 ~20 个 pulse 事件 + completed (duration_ms 120527)，但 `intermediate_state.shared_events = 0 个`。

**Files:**
- Read: `backend/services/shared_events_builder.py:181` (`build_shared_events`)
- Read: `backend/services/world_creator_agent_v2.py:_run_shared_events`
- Read: `backend/schemas/shared_events.py` (SharedEvent schema)

- [ ] **Step 1: 用 Task 1 重跑后的最新 task 看 shared_events 字段**

```bash
docker exec talealive-db-1 psql -U postgres -d talealive -c "
SELECT
  jsonb_typeof((intermediate_state::text)::jsonb -> 'shared_events') AS type,
  CASE jsonb_typeof((intermediate_state::text)::jsonb -> 'shared_events')
    WHEN 'array' THEN jsonb_array_length((intermediate_state::text)::jsonb -> 'shared_events')::text
    ELSE 'not an array'
  END AS detail
FROM generation_tasks
WHERE request_payload->>'phase' = 'phase_b' AND status = 'succeeded'
ORDER BY created_at DESC LIMIT 1;"
```

- [ ] **Step 2: 读 shared_events_builder 找原因**

Read `services/shared_events_builder.py:181-end` (`build_shared_events` 函数)。看：
- `_parse_events_from_data` (L117) 是否过滤太严
- `_dedup_by_title` (L168) 是否把所有 events dedup 掉
- LLM 输出格式问题（spec 第 5 节提到"LLM 输出格式不对没解析到"）

读 prompt 部分 (`_build_extract_prompt` L61, `_build_supplement_prompt` L91)，验证 schema 是否清晰。

- [ ] **Step 3: 加诊断日志，重跑一次抓 raw LLM 输出**

在 `build_shared_events` 拿到 LLM 文本但 parse 前后加：

```python
logger.warning("shared_events_raw_llm_text", text_preview=text[:800])
events = _parse_events_from_data(text)
logger.warning("shared_events_parsed", count=len(events))
deduped = _dedup_by_title(events)
logger.warning("shared_events_after_dedup", count=len(deduped))
```

重跑 → 看 log。

- [ ] **Step 4: 根据日志结果定向修**

可能 fix：
- 如果 `parsed > 0` 但 `dedup_by_title` 全 dedup → fix dedup 逻辑（可能用错了 key）
- 如果 `parsed == 0` 但 raw text 看着有事件 → fix `_parse_events_from_data`（JSON 提取或字段映射）
- 如果 raw text 是空或乱码 → fix prompt 或 max_tokens

- [ ] **Step 5: 跑 unit tests + 重跑逐玉验证**

```bash
docker exec talealive-backend-noreload python -m pytest tests/test_shared_events_builder.py -v 2>&1 | tail -10
```

再触发一次生成，查 `jsonb_array_length(... -> 'shared_events') >= 3`。

- [ ] **Step 6: 删调试日志**

---

## Task 3：修 relations_pack 持久化（实测 null）

**症状**：`intermediate_state.relations_pack = null`。

**Files:**
- Read: `backend/services/relations_pack_builder.py:21` (`build_relations_pack`)
- Read: `backend/services/world_creator_agent_v2.py:_run_relations_pack`

- [ ] **Step 1: 读 _run_relations_pack 看是否真的调用了 _record_intermediate**

Read `world_creator_agent_v2.py` 找 `_run_relations_pack`。注意 build_relations_pack 是 **同步函数（def 不是 async def）**，可能调用方式不对。

- [ ] **Step 2: 查 build_relations_pack 在 v2 agent 里的调用点**

```bash
grep -n "build_relations_pack\|relations_pack" backend/services/world_creator_agent_v2.py | head
```

应该有 `await self._record_intermediate("relations_pack", pack.model_dump())` 一类调用。如果没有 → 加上。如果有但传了 None 或空 dict → 检查 build_relations_pack 返回值。

- [ ] **Step 3: 修 + 验证**

修完跑一次生成查 relations_pack 不为 null：

```bash
docker exec talealive-db-1 psql -U postgres -d talealive -c "
SELECT (intermediate_state::text)::jsonb -> 'relations_pack' -> 'edges' AS edges
FROM generation_tasks
WHERE request_payload->>'phase' = 'phase_b' AND status = 'succeeded'
ORDER BY created_at DESC LIMIT 1;"
```
Expected: edges 至少有 ≥ 5 条。

---

## Task 4：Phase 2.0 验证 — 跑一次完整逐玉看三项都不空

**Files:** 无代码改动，纯验证 + 文档

- [ ] **Step 1: 创建 draft + 跑完整生成**

通过 admin UI 创建 draft 输入 "影视剧 逐玉" → strict → 等完成（约 90s）。

- [ ] **Step 2: 一次性查询三项指标**

```bash
docker exec talealive-db-1 psql -U postgres -d talealive -c "
SELECT
  jsonb_array_length((intermediate_state::text)::jsonb -> 'lore_pack' -> 'dimensions') AS lore_dims,
  jsonb_array_length(COALESCE((intermediate_state::text)::jsonb -> 'shared_events', '[]'::jsonb)) AS shared_count,
  COALESCE(jsonb_array_length((intermediate_state::text)::jsonb -> 'relations_pack' -> 'edges'), 0) AS rel_edges
FROM generation_tasks
WHERE request_payload->>'phase' = 'phase_b' AND status = 'succeeded'
ORDER BY created_at DESC LIMIT 1;"
```
Expected: lore_dims ≥ 4, shared_count ≥ 3, rel_edges ≥ 5

- [ ] **Step 3: 把这个数据写入 Phase 2 baseline 里**

Append 到 `docs/_archive/ip-fidelity-phase1-zhuyu-baseline.md`：

```markdown

## Phase 2.0 完成（2026-05-14）

修了 lore_pack / shared_events / relations_pack 三处持久化 bug：

| 指标 | Phase 1 | Phase 2.0 |
|---|---|---|
| lore_pack.dimensions | 0 | <填实测> |
| shared_events | 0 | <填实测> |
| relations_pack.edges | null | <填实测> |
```

---

# Phase 2.1：IP 知识层升级（Grok 主搜索 + 百度直抓）

## Task 5：Grok search extractor

**Files:**
- Create: `backend/services/ip_pack_extractors/grok_search.py`
- Create: `backend/tests/test_grok_search_extractor.py`

- [ ] **Step 1: 实现 grok_search.py**

```python
"""Grok web_search → list[Passage]。

把 Grok 一次性搜索结果作为 IP Research 的主要 passages 源。
Grok 输出的 text 已经是结构化中文清单（含演员表 + 关系 + 角色定位），
作为高质量上下文喂给下游 LLM 抽取。
"""
import re
import uuid
from typing import Any

import structlog

from schemas.research_pack import Passage

logger = structlog.get_logger()


def _build_query(ip_name: str, ip_type: str) -> str:
    """根据 ip_type 拼搜索关键词。"""
    base = f"《{ip_name}》"
    if ip_type in ("tv", "movie"):
        return f"电视剧/电影{base} 主要角色 演员表 角色介绍 人物关系 剧情"
    if ip_type == "novel":
        return f"小说{base} 主要人物 角色介绍 人物关系 剧情简介"
    if ip_type == "anime":
        return f"动漫{base} 主要角色 声优 人物关系 剧情"
    if ip_type == "game":
        return f"游戏{base} 主要角色 剧情 角色介绍"
    return f"{base} 主要角色 介绍 关系"


def _extract_candidate_names(grok_text: str) -> list[str]:
    """从 Grok summary 文本里抽出候选角色名（用于下游百度补抓）。

    简单 heuristic：找形如「饰 X」「饰演 X」「Y 饰 X」的人物名，
    以及粗暴的「X（演员名 X 饰）」格式。返回去重后的中文名。
    """
    names: list[str] = []
    # 匹配「饰 角色名」/「饰演 角色名」 (后跟中文/部分英文)
    for m in re.finditer(r"饰演?\s*\*?\*?\s*([一-鿿·]{2,12})", grok_text):
        names.append(m.group(1).strip("·"))
    # 去重保序
    seen: set[str] = set()
    unique: list[str] = []
    for n in names:
        if n not in seen:
            seen.add(n)
            unique.append(n)
    return unique[:20]


async def fetch_via_grok_search(
    ip_name: str,
    ip_type: str,
    grok_provider: Any | None,
    *,
    max_chars: int = 4000,
) -> tuple[list[Passage], list[str]]:
    """主入口：跑一次 Grok web_search，返回 (passages, candidate_names)。

    grok_provider 为 None 或 web_search 不可用 → 返回 ([], [])。
    """
    if grok_provider is None:
        return [], []
    query = _build_query(ip_name, ip_type)
    try:
        result = await grok_provider.web_search(query, max_tokens=2048)
    except Exception as exc:  # noqa: BLE001
        logger.warning("grok_search_failed", ip_name=ip_name, error=str(exc))
        return [], []

    text = (result.text or "").strip()
    if not text:
        return [], []

    citations = list(result.citations or [])
    tags = [f"query:{query}"] + [f"citation:{c.get('url','')}" for c in citations]

    passages = [Passage(
        id=f"p_grok_{uuid.uuid4().hex[:8]}",
        text=text[:max_chars],
        tags=tags,
        source="grok_search",
    )]
    candidates = _extract_candidate_names(text)
    return passages, candidates
```

**注意**：`Passage.source` 是 Literal，需要加 `"grok_search"`。打开 `backend/schemas/research_pack.py` 把 `PassageSource` literal 加上 `"grok_search"` 值（同 Phase 1 加 wikipedia/tavily_site 的模式）。

- [ ] **Step 2: 测试 (mock grok_provider)**

```python
# backend/tests/test_grok_search_extractor.py
"""Tests for Grok web_search extractor."""
import pytest
from unittest.mock import AsyncMock

from services.ip_pack_extractors.grok_search import (
    fetch_via_grok_search, _extract_candidate_names, _build_query,
)


def test_extract_candidate_names_from_grok_format():
    text = "张凌赫 饰 谢征（武安侯）\n田曦薇 饰 樊长玉（屠户女）\n任豪 饰 李怀安"
    names = _extract_candidate_names(text)
    assert "谢征" in names
    assert "樊长玉" in names
    assert "李怀安" in names


def test_extract_candidate_names_dedup():
    text = "饰 樊长玉 ... 樊长玉一身泼辣 ... 饰 樊长玉"
    names = _extract_candidate_names(text)
    assert names.count("樊长玉") == 1


def test_build_query_tv():
    q = _build_query("逐玉", "tv")
    assert "电视剧" in q
    assert "《逐玉》" in q
    assert "演员" in q


@pytest.mark.asyncio
async def test_fetch_returns_passage_and_candidates():
    fake_grok = AsyncMock()
    fake_result = AsyncMock()
    fake_result.text = "张凌赫 饰 谢征\n田曦薇 饰 樊长玉"
    fake_result.citations = [{"url": "https://example.com/x", "title": "1"}]
    fake_grok.web_search.return_value = fake_result

    passages, candidates = await fetch_via_grok_search("逐玉", "tv", fake_grok)
    assert len(passages) == 1
    assert passages[0].source == "grok_search"
    assert "谢征" in passages[0].text
    assert "谢征" in candidates
    assert "樊长玉" in candidates


@pytest.mark.asyncio
async def test_fetch_handles_none_provider():
    passages, candidates = await fetch_via_grok_search("X", "tv", None)
    assert passages == []
    assert candidates == []


@pytest.mark.asyncio
async def test_fetch_handles_exception():
    fake_grok = AsyncMock()
    fake_grok.web_search.side_effect = Exception("api down")
    passages, candidates = await fetch_via_grok_search("X", "tv", fake_grok)
    assert passages == []
    assert candidates == []
```

- [ ] **Step 3: 跑测试**

```bash
docker exec talealive-backend-noreload python -m pytest tests/test_grok_search_extractor.py -v
```
Expected: 6 passed

- [ ] **Step 4: 实测 Grok 跑一次逐玉（确认配置可用）**

```bash
docker exec talealive-backend-noreload python -c "
import asyncio
from llm.grok import GrokProvider
from services.ip_pack_extractors.grok_search import fetch_via_grok_search
async def main():
    p = GrokProvider()
    passages, candidates = await fetch_via_grok_search('逐玉', 'tv', p)
    print(f'passages: {len(passages)} | text_size: {len(passages[0].text) if passages else 0}')
    print(f'candidates: {candidates[:10]}')
asyncio.run(main())
" 2>&1 | tail -10
```
Expected: passages: 1 | text_size: ~2000-4000 | candidates: ['谢征', '樊长玉', '李怀安', ...] (至少 5 个原作角色名)

---

## Task 6：百度百科 extractor

**Files:**
- Create: `backend/services/ip_pack_extractors/baidu_baike.py`
- Create: `backend/tests/test_baidu_baike_extractor.py`

- [ ] **Step 1: 实现 baidu_baike.py**

```python
"""百度百科直抓 → list[Passage]。

两个入口：
- fetch_baike_show: 抓剧/作品主页（演员表 + 角色介绍区段最丰富）
- fetch_baike_character: 抓单角色页（per-character 详细资料）

依赖 httpx + beautifulsoup4 (Phase 1 已经装过)。
"""
import asyncio
import re
import uuid
from urllib.parse import quote

import httpx
import structlog

from schemas.research_pack import Passage

logger = structlog.get_logger()

BAIKE_BASE = "https://baike.baidu.com/item/"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0"


async def _fetch_html(url: str, timeout: float = 8.0) -> str | None:
    try:
        async with httpx.AsyncClient(timeout=timeout, headers={"User-Agent": USER_AGENT}) as c:
            r = await c.get(url, follow_redirects=True)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.text
    except Exception as exc:  # noqa: BLE001
        logger.warning("baike_fetch_failed", url=url, error=str(exc))
        return None


def _html_to_text(html: str, max_chars: int) -> str:
    """简单 HTML→text，跟 wikipedia.py 同思路：去 script/style 但保留 infobox 表格内容。"""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        logger.warning("beautifulsoup_not_installed")
        return ""

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    # 百度百科的主内容容器：先试常见 selector，再退到 body
    main = soup.select_one("div.lemma-summary") or soup.select_one("div.J-lemma-content") or soup.body
    text = main.get_text(separator="\n", strip=True) if main else ""
    return re.sub(r"\n{3,}", "\n\n", text)[:max_chars]


async def fetch_baike_show(
    ip_name: str,
    *,
    max_chars: int = 4000,
) -> list[Passage]:
    """抓 /item/<ip_name> 剧主页，切 2 段返回。"""
    url = BAIKE_BASE + quote(ip_name)
    html = await _fetch_html(url)
    if not html:
        return []
    text = _html_to_text(html, max_chars * 2)
    if not text.strip():
        return []
    passages: list[Passage] = []
    chunk_size = max_chars
    for offset in range(0, min(len(text), chunk_size * 2), chunk_size):
        chunk = text[offset: offset + chunk_size]
        if chunk.strip():
            passages.append(Passage(
                id=f"p_baike_show_{uuid.uuid4().hex[:8]}",
                text=chunk,
                tags=[f"source:{url}", f"query:{ip_name}", "kind:show_page"],
                source="baidu_baike",
            ))
    return passages


async def fetch_baike_character(
    name: str,
    *,
    max_chars: int = 3000,
) -> Passage | None:
    """抓 /item/<name>（百度自动消歧），返回 1 个 Passage 或 None。"""
    url = BAIKE_BASE + quote(name)
    html = await _fetch_html(url)
    if not html:
        return None
    text = _html_to_text(html, max_chars)
    if not text.strip():
        return None
    return Passage(
        id=f"p_baike_char_{uuid.uuid4().hex[:8]}",
        text=text[:max_chars],
        tags=[f"source:{url}", f"query:{name}", "kind:character_page"],
        source="baidu_baike",
    )


async def fetch_baike_characters_batch(
    names: list[str],
    *,
    max_chars: int = 3000,
    concurrency: int = 4,
    sleep_between: float = 0.3,
) -> list[Passage]:
    """批量抓多个角色页，并发受限 + 限速防反爬。返回成功的 passages list。"""
    sem = asyncio.Semaphore(concurrency)

    async def one(name: str) -> Passage | None:
        async with sem:
            p = await fetch_baike_character(name, max_chars=max_chars)
            await asyncio.sleep(sleep_between)
            return p

    results = await asyncio.gather(*(one(n) for n in names), return_exceptions=False)
    return [r for r in results if r is not None]
```

把 `baidu_baike` 加到 `PassageSource` Literal 里（同 Step 5 修改 schemas/research_pack.py）。

- [ ] **Step 2: 测试 (mock httpx)**

```python
# backend/tests/test_baidu_baike_extractor.py
"""Tests for Baidu Baike extractor."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from services.ip_pack_extractors.baidu_baike import (
    fetch_baike_show, fetch_baike_character, fetch_baike_characters_batch,
)


@pytest.mark.asyncio
async def test_show_404_returns_empty():
    fake_resp = MagicMock(status_code=404, raise_for_status=MagicMock())
    fake_client = MagicMock()
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=None)
    fake_client.get = AsyncMock(return_value=fake_resp)
    with patch("httpx.AsyncClient", return_value=fake_client):
        result = await fetch_baike_show("不存在的IP")
        assert result == []


@pytest.mark.asyncio
async def test_show_parses_html():
    html = "<html><body><div class='lemma-summary'>《逐玉》主要讲述...樊长玉与谢征。</div></body></html>"
    fake_resp = MagicMock(status_code=200, raise_for_status=MagicMock(), text=html)
    fake_client = MagicMock()
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=None)
    fake_client.get = AsyncMock(return_value=fake_resp)
    with patch("httpx.AsyncClient", return_value=fake_client):
        result = await fetch_baike_show("逐玉", max_chars=100)
        assert len(result) >= 1
        assert "樊长玉" in result[0].text or "谢征" in result[0].text
        assert result[0].source == "baidu_baike"


@pytest.mark.asyncio
async def test_character_returns_single_passage():
    html = "<html><body><div class='J-lemma-content'>樊长玉是电视剧《逐玉》中由田曦薇饰演的角色。</div></body></html>"
    fake_resp = MagicMock(status_code=200, raise_for_status=MagicMock(), text=html)
    fake_client = MagicMock()
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=None)
    fake_client.get = AsyncMock(return_value=fake_resp)
    with patch("httpx.AsyncClient", return_value=fake_client):
        result = await fetch_baike_character("樊长玉")
        assert result is not None
        assert "樊长玉" in result.text
        assert "kind:character_page" in result.tags


@pytest.mark.asyncio
async def test_character_404_returns_none():
    fake_resp = MagicMock(status_code=404, raise_for_status=MagicMock())
    fake_client = MagicMock()
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=None)
    fake_client.get = AsyncMock(return_value=fake_resp)
    with patch("httpx.AsyncClient", return_value=fake_client):
        result = await fetch_baike_character("不存在角色")
        assert result is None


@pytest.mark.asyncio
async def test_batch_filters_nones():
    html_ok = "<html><body><div class='J-lemma-content'>樊长玉相关内容</div></body></html>"

    async def fake_get_factory():
        responses = iter([
            MagicMock(status_code=200, raise_for_status=MagicMock(), text=html_ok),
            MagicMock(status_code=404, raise_for_status=MagicMock()),
            MagicMock(status_code=200, raise_for_status=MagicMock(), text=html_ok),
        ])
        async def get(*args, **kwargs):
            return next(responses)
        return get

    fake_client = MagicMock()
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=None)
    fake_client.get = AsyncMock(side_effect=[
        MagicMock(status_code=200, raise_for_status=MagicMock(), text=html_ok),
        MagicMock(status_code=404, raise_for_status=MagicMock()),
        MagicMock(status_code=200, raise_for_status=MagicMock(), text=html_ok),
    ])
    with patch("httpx.AsyncClient", return_value=fake_client):
        results = await fetch_baike_characters_batch(["A", "B", "C"], sleep_between=0)
        assert len(results) == 2  # 中间那个 404 被过滤
```

- [ ] **Step 3: 跑测试**

```bash
docker exec talealive-backend-noreload python -m pytest tests/test_baidu_baike_extractor.py -v
```
Expected: 5 passed

- [ ] **Step 4: 实测真实百度抓取（验证现实可用性）**

```bash
docker exec talealive-backend-noreload python -c "
import asyncio
from services.ip_pack_extractors.baidu_baike import fetch_baike_show, fetch_baike_characters_batch
async def main():
    show = await fetch_baike_show('逐玉')
    print(f'show passages: {len(show)} | total chars: {sum(len(p.text) for p in show)}')
    chars = await fetch_baike_characters_batch(['樊长玉', '谢征', '李怀安', '贺敬元'], concurrency=2)
    print(f'character passages: {len(chars)}')
    for p in chars:
        for tag in p.tags:
            if tag.startswith('query:'):
                print(f'  {tag[6:]}: {len(p.text)} chars')
asyncio.run(main())
" 2>&1 | tail -15
```
Expected: show passages ≥ 1, 总 chars ~4000+；character passages ≥ 3 (some name 可能消歧失败)

---

## Task 7：IPKnowledgePack schema 扩展

**Files:**
- Modify: `backend/schemas/ip_knowledge_pack.py`
- Modify: `backend/tests/test_ip_knowledge_pack_schema.py` (验证向后兼容)

- [ ] **Step 1: 加 4 个 optional 字段**

```python
# backend/schemas/ip_knowledge_pack.py 改动

# 1) IPCharacter 新增两个 optional 字段（在现有字段后追加，保持向后兼容）
class IPCharacter(BaseModel):
    name: str
    role_in_story: str
    relation_to_protagonist: str
    traits: list[str] = Field(default_factory=list)
    must_have: bool
    source_passage_ids: list[str] = Field(default_factory=list)
    # 新增
    voice_style: str | None = None      # 一句典型台词或语气描述（如"温润书生口吻，喜用文言"）
    story_arc: str | None = None         # 在原作的成长/角色弧线（30-80 字）


# 2) IPPlace 新增 faction_owner
class IPPlace(BaseModel):
    name: str
    description: str = ""
    must_have: bool = False
    source_passage_ids: list[str] = Field(default_factory=list)
    faction_owner: str | None = None     # 该地点属于哪个势力（与 factions[].name 对应）


# 3) IPKnowledgePack 新增 timeline
class IPTimelineEntry(BaseModel):
    when: str       # 相对时间锚，如 "17 年前" / "序幕" / "中段" / "结局"
    event: str      # 事件简述（30-60 字）
    source_passage_ids: list[str] = Field(default_factory=list)


class IPKnowledgePack(BaseModel):
    ip_name: str
    ip_type: IPType
    fidelity_mode: FidelityMode
    summary: str
    characters: list[IPCharacter]
    places: list[IPPlace]
    factions: list[IPFaction]
    iconic_objects: list[IPObject]
    key_events: list[IPEvent]
    tone_lingo: list[str]
    passages: list[Passage]
    # 新增
    timeline: list[IPTimelineEntry] = Field(default_factory=list)

    def must_have_character_names(self) -> list[str]:
        return [c.name for c in self.characters if c.must_have]

    def must_have_place_names(self) -> list[str]:
        return [p.name for p in self.places if p.must_have]
```

- [ ] **Step 2: 加测试验证扩展 + 向后兼容**

在 `backend/tests/test_ip_knowledge_pack_schema.py` 追加：

```python
def test_ip_character_new_optional_fields():
    from schemas.ip_knowledge_pack import IPCharacter
    # 不传 voice_style/story_arc 仍可构造（向后兼容）
    c = IPCharacter(name="X", role_in_story="女主", relation_to_protagonist="本人",
                    traits=[], must_have=True, source_passage_ids=[])
    assert c.voice_style is None
    assert c.story_arc is None

    # 传完整字段
    c2 = IPCharacter(name="樊长玉", role_in_story="女主", relation_to_protagonist="本人",
                     traits=["泼辣"], must_have=True, source_passage_ids=[],
                     voice_style="泼辣市井口吻，常用'我说'开头",
                     story_arc="屠户女 → 簪花将军")
    assert c2.voice_style == "泼辣市井口吻，常用'我说'开头"


def test_ip_place_faction_owner():
    from schemas.ip_knowledge_pack import IPPlace
    p = IPPlace(name="武安侯府", must_have=True, faction_owner="谢氏一族")
    assert p.faction_owner == "谢氏一族"


def test_timeline_entry_and_pack():
    from schemas.ip_knowledge_pack import IPTimelineEntry, IPKnowledgePack
    pack = IPKnowledgePack(
        ip_name="X", ip_type="tv", fidelity_mode="strict", summary="",
        characters=[], places=[], factions=[], iconic_objects=[],
        key_events=[], tone_lingo=[], passages=[],
        timeline=[IPTimelineEntry(when="17 年前", event="谢氏满门遭屠")],
    )
    assert pack.timeline[0].when == "17 年前"
    assert pack.timeline[0].event == "谢氏满门遭屠"


def test_pack_backward_compat_without_timeline():
    """旧调用方不传 timeline 仍可构造。"""
    from schemas.ip_knowledge_pack import IPKnowledgePack
    pack = IPKnowledgePack(
        ip_name="X", ip_type="tv", fidelity_mode="none", summary="",
        characters=[], places=[], factions=[], iconic_objects=[],
        key_events=[], tone_lingo=[], passages=[],
    )
    assert pack.timeline == []
```

- [ ] **Step 3: 跑测试**

```bash
docker exec talealive-backend-noreload python -m pytest tests/test_ip_knowledge_pack_schema.py -v
```
Expected: 既有 5 tests + 4 new tests = 9 passed

---

## Task 8：IP Research Pipeline 升级（4 步流程）

**Files:**
- Modify: `backend/services/ip_research_pipeline.py`
- Modify: `backend/tests/test_ip_research_pipeline.py`

**目标**：从 Phase 1 的 2 步流程（wiki+tavily 并发 → LLM 抽取 → 1 轮自检）升级为 4 步流程：
1. Step 1: Grok web_search 主搜索 → 拿 grok_summary + candidate_names
2. Step 2: 多源并发深抓 → grok + 百度剧主页 + 百度角色页（top N） + wiki + tavily fallback
3. Step 3: RAG 抽取 IPKnowledgePack（context = grok_summary 优先 + 百度细节）
4. Step 4: 完整性自检 4 维度（characters/places/factions/key_events），≤ 2 轮补抓

- [ ] **Step 1: 修改 `_gather_passages` 升级为多源并发 + 引入 grok/baidu**

打开 `services/ip_research_pipeline.py`，把 `_gather_passages` 改成接受 `grok_provider`：

```python
# 文件开头新增 imports
from services.ip_pack_extractors.grok_search import fetch_via_grok_search
from services.ip_pack_extractors.baidu_baike import (
    fetch_baike_show, fetch_baike_characters_batch,
)

MAX_BAIDU_CHARACTERS = 8  # 单局最多抓多少角色页


async def _gather_passages_v2(
    rec: IPRecognition,
    tavily: Any,
    grok_provider: Any | None,
) -> tuple[list[Passage], list[str]]:
    """4 步多源抓取。

    返回 (passages, candidate_names)。
    candidate_names 来自 Grok summary 的解析，用于下游"应该哪些角色 must_have"提示。
    """
    ip_name = rec.ip_name or ""
    ip_type = rec.ip_type or "other"
    if not ip_name:
        return [], []

    # Step 1: Grok 主搜索（拿候选名）
    grok_passages, candidates = await fetch_via_grok_search(ip_name, ip_type, grok_provider)

    # Step 2: 多源并发抓取
    # - 百度剧主页（始终抓）
    # - 百度角色页（top N candidates，若 Grok 给了）
    # - wiki + tavily 作 fallback
    baike_show_coro = fetch_baike_show(ip_name, max_chars=MAX_PASSAGE_CHARS)

    top_candidates = candidates[:MAX_BAIDU_CHARACTERS] if candidates else []
    baike_chars_coro = (
        fetch_baike_characters_batch(top_candidates, max_chars=MAX_PASSAGE_CHARS, concurrency=4)
        if top_candidates else
        _empty_list_coro()
    )

    wiki_coro = fetch_wikipedia(ip_name, max_chars=MAX_PASSAGE_CHARS)
    site_coro = fetch_via_tavily_site(ip_name, ip_type, tavily, max_chars=MAX_PASSAGE_CHARS)

    results = await asyncio.gather(
        baike_show_coro, baike_chars_coro, wiki_coro, site_coro,
        return_exceptions=True,
    )
    baike_show, baike_chars, wiki, site = (
        r if not isinstance(r, BaseException) else []
        for r in results
    )

    all_passages: list[Passage] = []
    all_passages.extend(grok_passages)
    all_passages.extend(list(baike_show))
    all_passages.extend(list(baike_chars))
    all_passages.extend(list(wiki))
    all_passages.extend(list(site))
    return all_passages[:MAX_PASSAGES], candidates


async def _empty_list_coro() -> list:
    """workaround: asyncio.gather 不接受非 coroutine, 但有时要传 noop。"""
    return []
```

- [ ] **Step 2: 修改 `_extract_pack` 把 grok_summary 单独标注为高优先级 context**

替换 `_passages_as_context` 调用为新的格式化函数：

```python
def _passages_as_context_v2(passages: list[Passage]) -> str:
    """把 passages 拼成 LLM context，grok_search 来源排最前并标注为"权威清单"。"""
    grok = [p for p in passages if p.source == "grok_search"]
    baike = [p for p in passages if p.source == "baidu_baike"]
    other = [p for p in passages if p.source not in ("grok_search", "baidu_baike")]

    chunks: list[str] = []
    if grok:
        chunks.append("## Grok 综合搜索摘要（多源 cross-check 过的权威清单）\n")
        for p in grok:
            chunks.append(f"[{p.id}] {p.text}")
    if baike:
        chunks.append("\n## 百度百科细节（角色详细资料）\n")
        for p in baike:
            chunks.append(f"[{p.id}] {p.text}")
    if other:
        chunks.append("\n## 其他来源（wiki / 通用搜索）\n")
        for p in other:
            chunks.append(f"[{p.id}] ({p.source}) {p.text}")
    return "\n\n".join(chunks)
```

修改 `_extract_pack` 的 prompt + user content，把候选名也提示进去：

```python
async def _extract_pack(
    rec: IPRecognition,
    passages: list[Passage],
    fidelity_mode: FidelityMode,
    llm_router: Any,
    candidate_names: list[str] | None = None,
) -> IPKnowledgePack:
    candidate_hint = ""
    if candidate_names:
        candidate_hint = (
            f"\n# Grok 给出的候选核心角色名（如下应当被包含为 must_have=true）：\n"
            f"{', '.join(candidate_names[:12])}\n"
        )

    user = (
        f"IP 名：{rec.ip_name}\n"
        f"IP 类型：{rec.ip_type}\n"
        f"{candidate_hint}\n"
        f"## 抽取目标\n"
        f"基于以下素材，输出 IPKnowledgePack JSON。要求：\n"
        f"- characters 至少 8 个（含 must_have=true 标记主角和核心配角）\n"
        f"- places 至少 5 个（含 must_have=true 标记核心地点）\n"
        f"- factions 至少 3 个\n"
        f"- key_events 至少 5 个\n"
        f"- timeline 至少 3 个相对时间锚条目\n\n"
        f"# 素材\n"
        f"{_passages_as_context_v2(passages)}"
    )
    text = await _collect_text(llm_router, _EXTRACT_SYSTEM, user)
    data = _extract_json(text) or {}
    return IPKnowledgePack(
        ip_name=rec.ip_name or "",
        ip_type=rec.ip_type or "other",
        fidelity_mode=fidelity_mode,
        summary=data.get("summary", ""),
        characters=[IPCharacter(**c) for c in (data.get("characters") or [])],
        places=[IPPlace(**p) for p in (data.get("places") or [])],
        factions=[IPFaction(**f) for f in (data.get("factions") or [])],
        iconic_objects=[IPObject(**o) for o in (data.get("iconic_objects") or [])],
        key_events=[IPEvent(**e) for e in (data.get("key_events") or [])],
        tone_lingo=list(data.get("tone_lingo") or []),
        timeline=[IPTimelineEntry(**t) for t in (data.get("timeline") or [])],
        passages=passages,
    )
```

更新 `_EXTRACT_SYSTEM` prompt 说明新的目标和 schema 字段（含 timeline / voice_style / story_arc / faction_owner）。

需要 import 新增 IPTimelineEntry：

```python
from schemas.ip_knowledge_pack import (
    IPKnowledgePack, IPCharacter, IPPlace, IPFaction, IPObject, IPEvent, FidelityMode,
    IPTimelineEntry,
)
```

- [ ] **Step 3: 升级 `_self_check_missing` 检查 4 维度**

```python
_MISSING_CHECK_SYSTEM_V2 = """检查 IPKnowledgePack 完整性，列出 4 维度的遗漏：

输出 JSON:
{
  "missing_characters": ["名字1", "名字2"],
  "missing_places": ["地点1"],
  "missing_factions": ["势力1"],
  "missing_key_events": ["事件1"]
}

如果某维度看着完整，对应数组返回 []。
每个维度最多列 5 个名字。"""


async def _self_check_missing_v2(pack: IPKnowledgePack, llm_router: Any) -> dict[str, list[str]]:
    if not pack.summary:
        return {"missing_characters": [], "missing_places": [], "missing_factions": [], "missing_key_events": []}

    user = (
        f"summary：{pack.summary}\n\n"
        f"已有 characters: {', '.join(c.name for c in pack.characters)}\n"
        f"已有 places: {', '.join(p.name for p in pack.places)}\n"
        f"已有 factions: {', '.join(f.name for f in pack.factions)}\n"
        f"已有 key_events: {', '.join(e.name for e in pack.key_events)}"
    )
    try:
        text = await _collect_text(llm_router, _MISSING_CHECK_SYSTEM_V2, user, max_tokens=512)
        data = _extract_json(text) or {}
    except Exception as exc:  # noqa: BLE001
        logger.warning("self_check_v2_failed", error=str(exc))
        return {"missing_characters": [], "missing_places": [], "missing_factions": [], "missing_key_events": []}

    return {
        "missing_characters": [n for n in (data.get("missing_characters") or []) if isinstance(n, str)][:5],
        "missing_places": [n for n in (data.get("missing_places") or []) if isinstance(n, str)][:5],
        "missing_factions": [n for n in (data.get("missing_factions") or []) if isinstance(n, str)][:5],
        "missing_key_events": [n for n in (data.get("missing_key_events") or []) if isinstance(n, str)][:5],
    }
```

- [ ] **Step 4: 修改 `build_ip_knowledge_pack` 主入口接入新流程 + 2 轮补抓**

```python
MAX_REFETCH_ROUNDS = 2  # 升级自 Phase 1 的 1 轮


async def build_ip_knowledge_pack(
    rec: IPRecognition,
    fidelity_mode: FidelityMode,
    llm_router: Any,
    tavily: Any,
    grok_provider: Any | None = None,
) -> IPKnowledgePack:
    """主入口（Phase 2.1 升级）。"""
    if rec.kind not in ("known_ip", "hybrid") or not rec.ip_name:
        return _empty_pack(rec, fidelity_mode)

    # Step 1+2: 多源抓取
    passages, candidate_names = await _gather_passages_v2(rec, tavily, grok_provider)
    if not passages:
        logger.warning("ip_research_no_passages", ip_name=rec.ip_name)
        return _empty_pack(rec, fidelity_mode)

    # Step 3: 抽取
    pack = await _extract_pack(rec, passages, fidelity_mode, llm_router, candidate_names)

    # Step 4: 自检 + 补抓 (最多 2 轮)
    for round_idx in range(MAX_REFETCH_ROUNDS):
        missing = await _self_check_missing_v2(pack, llm_router)
        missing_chars = missing["missing_characters"]
        missing_places = missing["missing_places"]
        # 只在 characters / places 有漏时补抓（factions/events 不抓，留给抽取 prompt 自己补）
        if not missing_chars and not missing_places:
            break

        extra_passages: list[Passage] = []
        if missing_chars:
            # 用 Baidu 抓漏的角色页（最便宜最准）
            chars_extra = await fetch_baike_characters_batch(
                missing_chars, max_chars=MAX_PASSAGE_CHARS, concurrency=4,
            )
            extra_passages.extend(chars_extra)
        if missing_places:
            # 用 Tavily site 搜地点（百度地名搜索不靠谱）
            for place_name in missing_places:
                place_passages = await fetch_via_tavily_site(
                    place_name, rec.ip_type or "other", tavily, max_per_site=1,
                )
                extra_passages.extend(place_passages)

        if not extra_passages:
            break

        all_passages = (passages + extra_passages)[:MAX_PASSAGES]
        pack = await _extract_pack(rec, all_passages, fidelity_mode, llm_router, candidate_names)

    return pack


def _empty_pack(rec: IPRecognition, fidelity_mode: FidelityMode) -> IPKnowledgePack:
    return IPKnowledgePack(
        ip_name=rec.ip_name or "",
        ip_type=rec.ip_type or "other",
        fidelity_mode=fidelity_mode,
        summary="", characters=[], places=[], factions=[],
        iconic_objects=[], key_events=[], tone_lingo=[],
        passages=[], timeline=[],
    )
```

- [ ] **Step 5: 调用方传 grok_provider**

修改 `services/world_creator_agent_v2.py:_run_ip_research`（Phase 1 已建）。在 `build_ip_knowledge_pack` 调用处：

```python
# 找到 self._last_ip_pack 设值前的 build_ip_knowledge_pack 调用
# 增加 grok_provider 参数:
from llm.grok import GrokProvider  # 顶部 import

# 调用处:
pack = await build_ip_knowledge_pack(
    rec=rec,
    fidelity_mode=fidelity,
    llm_router=self.llm,
    tavily=getattr(self, "tavily", None) or getattr(self.broker, "tavily", None),
    grok_provider=GrokProvider(),  # 新增
)
```

- [ ] **Step 6: 升级测试**

`backend/tests/test_ip_research_pipeline.py` 新增测试：

```python
@pytest.mark.asyncio
async def test_pipeline_uses_grok_candidate_names(monkeypatch):
    """Grok 返回 candidates → 抽取 prompt 应该包含 candidate_hint。"""
    rec = IPRecognition(kind="known_ip", confidence=0.9, ip_name="逐玉", ip_type="tv")

    captured_prompts: list[str] = []

    class CapturingLLM:
        async def stream_with_tools(self, *, messages, **_):
            # 把 user content 存下来
            for m in messages:
                if m.get("role") == "user":
                    captured_prompts.append(m["content"])
            # 返回合规的 pack JSON
            text = '{"summary":"S","characters":[{"name":"樊长玉","role_in_story":"女主","relation_to_protagonist":"本人","traits":[],"must_have":true,"source_passage_ids":[]}],"places":[{"name":"临安镇","must_have":true,"source_passage_ids":[]}],"factions":[],"iconic_objects":[],"key_events":[],"tone_lingo":[],"timeline":[]}'
            for ch in text:
                yield {"type": "text_delta", "text": ch}

    fake_grok = AsyncMock()
    fake_grok_result = AsyncMock()
    fake_grok_result.text = "张凌赫 饰 谢征\n田曦薇 饰 樊长玉\n任豪 饰 李怀安"
    fake_grok_result.citations = []
    fake_grok.web_search.return_value = fake_grok_result

    monkeypatch.setattr(
        "services.ip_research_pipeline.fetch_wikipedia",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        "services.ip_research_pipeline.fetch_baike_show",
        AsyncMock(return_value=[Passage(id="bs1", text="百度剧主页内容", tags=[], source="baidu_baike")]),
    )
    monkeypatch.setattr(
        "services.ip_research_pipeline.fetch_baike_characters_batch",
        AsyncMock(return_value=[]),
    )

    pack = await build_ip_knowledge_pack(
        rec, "strict", llm_router=CapturingLLM(),
        tavily=AsyncMock(search=AsyncMock(return_value=[])),
        grok_provider=fake_grok,
    )

    # candidate_hint 应该出现在抽取 prompt 里
    found = any("樊长玉" in p and "Grok 给出的候选" in p for p in captured_prompts)
    assert found, f"candidate hint missing; captured prompts (first 200 chars): {[p[:200] for p in captured_prompts]}"
    assert pack.ip_name == "逐玉"
    assert "樊长玉" in pack.must_have_character_names()


@pytest.mark.asyncio
async def test_pipeline_self_check_v2_four_dimensions(monkeypatch):
    """完整性自检应能检查 4 维度并触发针对性补抓。"""
    rec = IPRecognition(kind="known_ip", confidence=0.9, ip_name="X", ip_type="tv")

    extract1 = '{"summary":"S long enough","characters":[{"name":"A","role_in_story":"主","relation_to_protagonist":"本人","traits":[],"must_have":true,"source_passage_ids":[]}],"places":[],"factions":[],"iconic_objects":[],"key_events":[],"tone_lingo":[],"timeline":[]}'
    missing = '{"missing_characters":["B"],"missing_places":["P1"],"missing_factions":[],"missing_key_events":[]}'
    extract2 = '{"summary":"S2","characters":[{"name":"A","role_in_story":"主","relation_to_protagonist":"本人","traits":[],"must_have":true,"source_passage_ids":[]},{"name":"B","role_in_story":"配角","relation_to_protagonist":"友","traits":[],"must_have":true,"source_passage_ids":[]}],"places":[{"name":"P1","must_have":true,"source_passage_ids":[]}],"factions":[],"iconic_objects":[],"key_events":[],"tone_lingo":[],"timeline":[]}'
    no_missing = '{"missing_characters":[],"missing_places":[],"missing_factions":[],"missing_key_events":[]}'

    class SeqLLM:
        def __init__(self, *texts):
            self.texts = list(texts); self.i = 0
        async def stream_with_tools(self, **_):
            t = self.texts[min(self.i, len(self.texts) - 1)]
            self.i += 1
            for ch in t:
                yield {"type": "text_delta", "text": ch}

    monkeypatch.setattr(
        "services.ip_research_pipeline.fetch_wikipedia",
        AsyncMock(return_value=[Passage(id="w1", text="...", tags=[], source="wikipedia")]),
    )
    monkeypatch.setattr(
        "services.ip_research_pipeline.fetch_baike_show",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        "services.ip_research_pipeline.fetch_baike_characters_batch",
        AsyncMock(return_value=[Passage(id="b1", text="角色B详情", tags=[], source="baidu_baike")]),
    )

    pack = await build_ip_knowledge_pack(
        rec, "strict",
        llm_router=SeqLLM(extract1, missing, extract2, no_missing),
        tavily=AsyncMock(search=AsyncMock(return_value=[{"content": "P1 detail", "url": "x"}])),
        grok_provider=None,
    )
    assert "B" in [c.name for c in pack.characters]
    assert "P1" in pack.must_have_place_names()
```

- [ ] **Step 7: 跑所有 IP research 相关测试**

```bash
docker exec talealive-backend-noreload python -m pytest \
  tests/test_ip_research_pipeline.py \
  tests/test_grok_search_extractor.py \
  tests/test_baidu_baike_extractor.py \
  tests/test_ip_knowledge_pack_schema.py \
  -v
```
Expected: 全部 pass。原有 6 个 ip_research_pipeline test + 2 个新增 = 8 个 pass.

---

## Task 9：Phase 2.0+2.1 端到端验收

**Files:** 无代码改动，纯验证 + 文档

- [ ] **Step 1: 跑一次逐玉 strict 生成**

通过 admin UI（或 curl 复用 Phase 1 的两阶段流程）：
1. 创建 draft "影视剧 逐玉"
2. phase_a 完成 → choose strict
3. 等 phase_b 完成（~150s 含 Grok 调用 + 百度抓取）

观察 SSE 流：应该看到 ip_research stage 跑了较长时间（Grok 1 次 + 百度多次 + 抽取 1 次 + 自检 ≤2 轮）

- [ ] **Step 2: 一次性查关键指标**

```bash
docker exec talealive-db-1 psql -U postgres -d talealive -c "
WITH latest_draft AS (
  SELECT id FROM world_drafts
  WHERE payload->>'name' LIKE '%逐玉%'
  ORDER BY updated_at DESC LIMIT 1
),
latest_pack AS (
  SELECT pack_json FROM ip_knowledge_packs
  WHERE draft_id IN (SELECT id FROM latest_draft)
  ORDER BY created_at DESC LIMIT 1
)
SELECT
  json_array_length(pack_json->'characters') AS char_n,
  json_array_length(pack_json->'places') AS place_n,
  json_array_length(pack_json->'factions') AS faction_n,
  json_array_length(pack_json->'key_events') AS event_n,
  json_array_length(pack_json->'timeline') AS timeline_n,
  json_array_length(pack_json->'passages') AS passages_n
FROM latest_pack;"
```
Expected (Phase 2.1 验收阈值)：char_n ≥ 8, place_n ≥ 5, faction_n ≥ 3, event_n ≥ 5, timeline_n ≥ 3.

- [ ] **Step 3: 看具体角色清单是否含原作核心人物**

```bash
docker exec talealive-db-1 psql -U postgres -d talealive -c "
WITH latest_pack AS (
  SELECT pack_json FROM ip_knowledge_packs
  WHERE pack_json->>'ip_name' = '逐玉'
  ORDER BY created_at DESC LIMIT 1
)
SELECT
  (jsonb_array_elements((pack_json::text)::jsonb -> 'characters')) ->> 'name' AS name,
  ((jsonb_array_elements((pack_json::text)::jsonb -> 'characters')) ->> 'must_have')::text AS must_have
FROM latest_pack;"
```
Expected: 至少包含 樊长玉 / 谢征 / 李怀安 / 俞浅浅 / 齐旻 / 魏严 / 其中 4-5 个 (Grok 给的清单覆盖)。

- [ ] **Step 4: 写 Phase 2.1 baseline 报告**

Append 到 `docs/_archive/ip-fidelity-phase1-zhuyu-baseline.md`：

```markdown

## Phase 2.1 完成（2026-05-14）

引入 Grok + 百度百科作主搜索源后的 IP Pack 抽取结果：

| 指标 | Phase 1 | Phase 2.1 |
|---|---|---|
| IP Pack characters 数 | 2 | <填实测> |
| IP Pack must_have 数 | 2 | <填实测> |
| IP Pack places 数 | 0 | <填实测> |
| IP Pack factions 数 | 0 | <填实测> |
| key_events 数 | 4 | <填实测> |
| timeline 条目 | (无字段) | <填实测> |

### 复刻的原作角色清单
（填实测得到的 must_have_characters）

### Phase 2.2-2.7 待办（提醒下一阶段）
- 防线 1-4（structured output / two-step / 分层 prompt / 双轨 critic）尚未应用
- NPC / location schema 仍是 Phase 1 的 5/2 字段
- 下游 lore_pack / characters 仍编"青州城"等假地名（IP Pack 已有正确地名，但 prompt 未用）
```

---

## Self-Review Checklist

### Spec coverage（Phase 2.0+2.1 范围内）

| Spec 节 | 对应 Task | Coverage |
|---|---|---|
| §2.1 IP Research 升级（Grok+百度） | T5, T6, T8 | ✅ |
| §5.1 修 lore_pack=0 bug | T1 | ✅ |
| §5.3 shared_events / relations_pack 持久化 | T2, T3 | ✅ |
| IPKnowledgePack schema 扩展（timeline 等） | T7 | ✅ |
| 实测验收 | T4, T9 | ✅ |

### 显式延后到后续 plan

| Spec 节 | 后续 phase | 说明 |
|---|---|---|
| §3 防线 1-4 | Phase 2.2 / 2.5 | structured output / two-step / 双轨 critic |
| §5.2 lore_pack 接 IP Pack | Phase 2.4 | IP-aware lore 维度 |
| §6 Schema 扩展（Location 2→8 / NPC 5→9） | Phase 2.3 | Pydantic + migration + builder 升级 |
| §7 SSE 子事件 + 前端展示 | Phase 2.6 | GenerationLoadingScreen 折叠区 |
| §10 实施 phase 2.7 5IP 验收 | Phase 2.7 | 全部完成后回归 |

### Placeholder scan

✅ 每个 Task 有完整代码 / 命令 / expected output。  
✅ "找出 bug 根因再修"是 T1-T3 的本意（诊断 task），不算 placeholder（有具体 hypothesis 清单 + 调试命令）。

### Type consistency

- `Passage.source` Literal 在 T5 + T6 各加 `"grok_search"` / `"baidu_baike"`（共两处编辑同一文件）
- `IPKnowledgePack` schema 新增 `timeline` 字段在 T7 定义，T8 `_extract_pack` 使用
- `IPCharacter.voice_style / story_arc`、`IPPlace.faction_owner` 在 T7 定义但 T8 暂不强制使用（后续 phase 用），向后兼容 OK
