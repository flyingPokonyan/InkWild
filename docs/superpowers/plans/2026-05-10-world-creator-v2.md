# 世界 / 剧本生成 Agent v2 · Master Implementation Plan

> **状态：已完成（2026-05-10）。** M1–M5 全部 milestone 落地，含 W6 heavy critic + repair pass。每个 task 的产出参见 `docs/superpowers/plans/checkpoints/2026-05-10-*.md`（28 个 checkpoint 文件）。`world_creator_v2_enabled` 自 2026-05-12 起默认 True。下方 task checkbox 全部 ✅。

> **For agentic workers (历史)：** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 把世界/剧本生成 Agent 从"够用"升级到"扛得住自由互动 + 高保真复刻"——通过 ResearchPack 结构化保真、角色分批、lore_pack、shared_events、events_data 钩子、运行时引擎接入、并发优化、retry/checkpoint 实现 spec §0.2 的五个瓶颈全数破除。

**Architecture:** 沿用现有五层模型（policy → research → strategy → execution → validation），扩展为 12 阶段流；新增 4 个 JSON 字段在 `worlds` 表（lore_pack / shared_events / events_data + intermediate_state 在 generation_tasks），运行时 NPC Agent / world_simulator 按需召回新字段；feature flag (`WORLD_CREATOR_V2_ENABLED`) 控制 v1/v2 切换，灰度上线。

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy 2.0 async / Alembic / asyncpg / structlog / sse-starlette / pytest-asyncio + pytest（后端）；Next.js 16 / React 19 / TypeScript / Zustand（前端）

**Spec:** [`docs/superpowers/specs/2026-05-10-world-creator-overhaul-design.md`](../specs/2026-05-10-world-creator-overhaul-design.md)

**Git 状态:** 项目不是 git repo（参考 `docs/superpowers/specs/2026-05-08-frontend-refactor-master-plan.md` line 30），交付按"自然 checkpoint"组织——每完成一个 task 跑测试 + 写阶段总结到 `docs/superpowers/plans/checkpoints/`，不走 commit；plan 中所有 "git commit" 步骤替换为"checkpoint：跑测试 + 写阶段总结"。

---

## 0. Milestone 总览

```
M1 (基础 + ResearchPack)        ── 1.0-1.5 周 ──> 可独立 ship: admin 后台跑生成时 ResearchPack 已结构化（含 passages + IPCanon）
   │
   ▼
M2 (World 厚度)                 ── 2.0 周 ─────> 可独立 ship: 30+ 角色 + lore_pack + shared_events + relations_pack
   │
   ▼
M3 (事件骨架 + DSL)              ── 1.5-2.0 周 ─> 可独立 ship: 自由世界含 events_data 钩子（含 rumors）
   │
   ▼
M4 (质量与容错)                  ── 1.0 周 ─────> 可独立 ship: Critic 分级 + moderation + retry/checkpoint
   │
   ▼
M5 (运行时 + 前端 + Script v2)   ── 1.5 周 ─────> 可独立 ship: NPC Agent 消费新字段 + 前端进度条 + Script 同步升级
```

每 milestone 可独立测试 ship，feature flag (`WORLD_CREATOR_V2_ENABLED`) 在 M1 引入，M5 完成后默认 true。

**并行机会**：
- M2 内部三个子组件（characters / lore / shared_events）可并行（spec §12.3 已分析依赖图）
- M5 内的"运行时接入"和"前端反馈"可并行
- M3 的 condition_dsl 解析器与 events_data 生成可并行

---

## 1. 文件影响面（全 milestone 总览）

### 后端 - 新建文件

| 路径 | 责任 | M |
|---|---|---|
| `backend/migrations/versions/<rev>_world_creator_v2_fields.py` | Alembic：worlds 加 3 字段 + generation_tasks 加 1 字段 | M1 |
| `backend/schemas/research_pack.py` | ResearchPack / Passage / IPCanon dataclass + Pydantic | M1 |
| `backend/services/research_pack_builder.py` | 三路合并：Tavily passages / IP probe / admin_note 切片 | M1 |
| `backend/services/lore_pack_builder.py` | lore_dimensions + lore_pack 两阶段 | M2 |
| `backend/services/character_roster_builder.py` | character_roster + 分批生成 + dedup 校验 | M2 |
| `backend/services/shared_events_builder.py` | 从 passages 抽取 + LLM 补；含 source_passage_ids | M2 |
| `backend/services/relations_pack_builder.py` | 反向推每 NPC important_relations + 派系兜底 | M2 |
| `backend/services/events_data_builder.py` | events_data 生成（kind=npc_intent_driven / conditional + rumors） | M3 |
| `backend/engine/condition_dsl.py` | DSL 解析器（白名单 ops，~200 行） | M3 |
| `backend/services/world_critic_service.py` | Critic 分级（形状校验 / 轻 critic / 运行时校验） | M4 |
| `backend/services/world_moderation_service.py` | 生成期 moderation pass | M4 |
| `backend/services/world_creator_agent_v2.py` | v2 主入口（与现 v1 并存，feature flag 切换） | 跨 M |
| `backend/tests/test_research_pack.py` | M1 单元测试 | M1 |
| `backend/tests/test_lore_pack.py` | M2 单元测试 | M2 |
| `backend/tests/test_character_batch.py` | M2 单元测试 | M2 |
| `backend/tests/test_shared_events.py` | M2 单元测试 | M2 |
| `backend/tests/test_events_data_dsl.py` | M3 单元测试 | M3 |
| `backend/tests/test_world_simulator_events.py` | M5 单元测试 | M5 |
| `backend/tests/test_npc_agent_lore_injection.py` | M5 单元测试 | M5 |
| `backend/tests/test_world_creator_v2_e2e.py` | M5 集成测试 | M5 |

### 后端 - 修改文件

| 路径 | 修改 | M |
|---|---|---|
| `backend/config.py` / `backend/settings.py` | 加 `WORLD_CREATOR_V2_ENABLED` 配置 + 容量上限常量 | M1 |
| `backend/models/generation_task.py` | 加 `intermediate_state` Column | M1 |
| `backend/models/world.py` | 加 `lore_pack / shared_events / events_data` JSON Column | M1 |
| `backend/services/research_broker.py` | 暴露 `build_pack(request) → ResearchPack` 方法 | M1 |
| `backend/services/world_creator_agent.py` | v1 入口保留，v2 链路在 v2 主入口；retry / intermediate_state 织入 | M4 |
| `backend/services/generation_task_service.py` | intermediate_state 写入 + retry 接入 | M4 |
| `backend/services/generation_prompt_builder.py` | 加新阶段 prompt（lore / character_roster / shared_events / events_data） | M2/M3 |
| `backend/services/generation_strategy_service.py` | brief 输出加 `relevant_passage_ids` 字段 | M2 |
| `backend/api/admin.py` | feature flag 判断 + ResearchPack 容量校验 422 | M1 |
| `backend/engine/orchestrator.py` | NPC Agent kwargs 加 `relevant_lore / involved_shared_events / relevant_rumors` | M5 |
| `backend/engine/npc_agent.py` | prompt builder 接入新字段 | M5 |
| `backend/engine/world_simulator.py` | tick 加 events_data trigger 检查 | M5 |
| `backend/engine/memory_manager.py` | 加 `find_relevant_lore` / `find_npc_shared_events` / `find_npc_rumors` | M5 |

### 前端 - 修改文件

| 路径 | 修改 | M |
|---|---|---|
| `frontend/lib/admin-sse-events.ts` | 加新 phase 名 + ProgressMeta schema + subtask 事件 | M5 |
| `frontend/components/admin/editor/DraftEditorShell.tsx` | stages map + 子任务进度条 | M5 |
| `frontend/components/admin/editor/sections/*` | 新增 LorePackSection / SharedEventsSection / EventsDataSection（read-only） | M5 |
| `frontend/components/admin/editor/EditorSection.tsx` | 复用渲染新 section | M5 |

---

## 2. Milestone 1: 基础 + ResearchPack

> 目标：admin 跑一次生成后，`generation_tasks.intermediate_state.research_pack` 含结构化 ResearchPack（passages + IPCanon），admin 在草稿编辑器看到 read-only ResearchPack 内容；feature flag 关闭时走 v1 旧路径不受影响。

### Task 1.1: Alembic 迁移

**Files:**
- Create: `backend/migrations/versions/<auto-rev>_world_creator_v2_fields.py`
- Modify: `backend/models/world.py`, `backend/models/generation_task.py`

- [x] **Step 1: 写迁移目标的失败测试**

```python
# backend/tests/test_world_creator_v2_migration.py
import pytest
from sqlalchemy import inspect

@pytest.mark.asyncio
async def test_worlds_table_has_v2_fields(async_engine):
    async with async_engine.connect() as conn:
        cols = await conn.run_sync(lambda c: {col["name"] for col in inspect(c).get_columns("worlds")})
    assert "lore_pack" in cols
    assert "shared_events" in cols
    assert "events_data" in cols

@pytest.mark.asyncio
async def test_generation_tasks_has_intermediate_state(async_engine):
    async with async_engine.connect() as conn:
        cols = await conn.run_sync(lambda c: {col["name"] for col in inspect(c).get_columns("generation_tasks")})
    assert "intermediate_state" in cols
```

- [x] **Step 2: 跑测试确认失败**

Run: `cd backend && python -m pytest tests/test_world_creator_v2_migration.py -v`
Expected: FAIL（字段不存在）

- [x] **Step 3: 用 alembic 自动生成迁移骨架**

Run: `cd backend && alembic revision --autogenerate -m "world_creator_v2_fields"`
Note: 拿到 revision hash，rename 文件成 `<hash>_world_creator_v2_fields.py`

- [x] **Step 4: 编辑迁移内容**

```python
# backend/migrations/versions/<hash>_world_creator_v2_fields.py
"""world_creator_v2_fields

Revision ID: <hash>
Revises: <prev>
Create Date: 2026-05-10 ...
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "<hash>"
down_revision = "<prev>"

def upgrade():
    op.add_column("worlds", sa.Column("lore_pack", JSONB, nullable=True))
    op.add_column("worlds", sa.Column("shared_events", JSONB, nullable=True))
    op.add_column("worlds", sa.Column("events_data", JSONB, nullable=True))
    op.add_column("generation_tasks", sa.Column("intermediate_state", JSONB, nullable=True))

def downgrade():
    op.drop_column("generation_tasks", "intermediate_state")
    op.drop_column("worlds", "events_data")
    op.drop_column("worlds", "shared_events")
    op.drop_column("worlds", "lore_pack")
```

- [x] **Step 5: 同步 ORM 模型**

修改 `backend/models/world.py`，加：
```python
lore_pack: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=None)
shared_events: Mapped[list | None] = mapped_column(JSONB, nullable=True, default=None)
events_data: Mapped[list | None] = mapped_column(JSONB, nullable=True, default=None)
```

修改 `backend/models/generation_task.py`，加：
```python
intermediate_state: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=None)
```

- [x] **Step 6: 跑迁移**

Run: `cd backend && alembic upgrade head`

- [x] **Step 7: 跑测试验证**

Run: `cd backend && python -m pytest tests/test_world_creator_v2_migration.py -v`
Expected: PASS

- [x] **Step 8: Checkpoint**

写 `docs/superpowers/plans/checkpoints/2026-05-10-task-1.1.md` 简短记录：迁移 hash + downgrade 已验证可逆 + 测试 PASS。

---

### Task 1.2: Feature flag + 容量上限常量

**Files:**
- Modify: `backend/config.py`（或 `backend/settings.py`）
- Test: 复用 `tests/test_settings.py` 或新建

- [x] **Step 1: 写失败测试**

```python
# backend/tests/test_world_creator_v2_settings.py
from config import settings

def test_world_creator_v2_flag_default_false():
    assert settings.world_creator_v2_enabled is False

def test_research_pack_limits_present():
    assert settings.research_pack_max_passages == 100
    assert settings.research_pack_max_passage_chars == 600
    assert settings.research_pack_max_admin_description_chars == 50_000
```

- [x] **Step 2: 跑测试确认 FAIL**

Run: `cd backend && python -m pytest tests/test_world_creator_v2_settings.py -v`

- [x] **Step 3: 加配置项**

修改 `backend/config.py` 的 Settings 类：
```python
class Settings(BaseSettings):
    # ... 现有字段 ...
    world_creator_v2_enabled: bool = False
    research_pack_max_passages: int = 100
    research_pack_max_passage_chars: int = 600
    research_pack_max_admin_description_chars: int = 50_000
```

- [x] **Step 4: 跑测试 PASS**

Run: `cd backend && python -m pytest tests/test_world_creator_v2_settings.py -v`

- [x] **Step 5: Checkpoint**

记录到 `checkpoints/2026-05-10-task-1.2.md`。

---

### Task 1.3: ResearchPack schema

**Files:**
- Create: `backend/schemas/research_pack.py`
- Test: `backend/tests/test_research_pack_schema.py`

- [x] **Step 1: 写失败测试**

```python
# backend/tests/test_research_pack_schema.py
import pytest
from pydantic import ValidationError
from schemas.research_pack import ResearchPack, Passage, IPCanon

def test_passage_round_trip():
    p = Passage(id="p_001", text="content", tags=["character:A"], source="tavily")
    assert p.id == "p_001"
    assert p.source == "tavily"

def test_passage_invalid_source_rejected():
    with pytest.raises(ValidationError):
        Passage(id="p_001", text="x", tags=[], source="invalid")

def test_research_pack_empty_default():
    pack = ResearchPack(summary="", passages=[], ip_canon=IPCanon())
    assert pack.passages == []
    assert pack.ip_canon.canonical_names == []

def test_ip_canon_truncation():
    ipc = IPCanon(canonical_names=["x"] * 300)
    pack = ResearchPack(summary="", passages=[], ip_canon=ipc)
    # truncation 由 builder 做，schema 层不强制
    assert len(pack.ip_canon.canonical_names) == 300
```

- [x] **Step 2: 跑测试 FAIL**

Run: `cd backend && python -m pytest tests/test_research_pack_schema.py -v`

- [x] **Step 3: 写 schema**

```python
# backend/schemas/research_pack.py
from typing import Literal
from pydantic import BaseModel, Field

PassageSource = Literal["tavily", "ip_probe", "admin_note"]

class Passage(BaseModel):
    id: str
    text: str
    tags: list[str] = Field(default_factory=list)
    source: PassageSource

class IPCanon(BaseModel):
    title_guesses: list[str] = Field(default_factory=list)
    canonical_names: list[str] = Field(default_factory=list)
    canonical_places: list[str] = Field(default_factory=list)
    iconic_objects: list[str] = Field(default_factory=list)
    lingo: list[str] = Field(default_factory=list)
    notable_events: list[str] = Field(default_factory=list)

class ResearchPack(BaseModel):
    summary: str
    passages: list[Passage]
    ip_canon: IPCanon
```

- [x] **Step 4: 跑测试 PASS**

- [x] **Step 5: Checkpoint**

---

### Task 1.4: Passage 切片器（admin_note 路径）

**Files:**
- Modify: `backend/services/research_pack_builder.py`（新建）
- Test: `backend/tests/test_research_pack_admin_note.py`

- [x] **Step 1: 失败测试**

```python
# backend/tests/test_research_pack_admin_note.py
from services.research_pack_builder import slice_admin_note_to_passages

def test_short_description_one_passage():
    passages = slice_admin_note_to_passages("一段短描述", max_chars=600)
    assert len(passages) == 1
    assert passages[0].source == "admin_note"
    assert passages[0].text == "一段短描述"

def test_long_description_paragraph_split():
    long = "段落一。\n\n段落二。\n\n段落三。"
    passages = slice_admin_note_to_passages(long, max_chars=600)
    assert len(passages) == 3
    assert all(p.source == "admin_note" for p in passages)

def test_oversize_paragraph_chunked():
    long = "x" * 1500
    passages = slice_admin_note_to_passages(long, max_chars=600)
    assert len(passages) == 3  # 600 / 600 / 300
    assert len(passages[0].text) == 600

def test_unique_ids():
    long = "段落一。\n\n段落二。\n\n段落三。"
    passages = slice_admin_note_to_passages(long, max_chars=600)
    ids = [p.id for p in passages]
    assert len(set(ids)) == len(ids)
```

- [x] **Step 2: 跑 FAIL**

- [x] **Step 3: 实现**

```python
# backend/services/research_pack_builder.py
import uuid
from schemas.research_pack import Passage

def slice_admin_note_to_passages(text: str, max_chars: int) -> list[Passage]:
    text = (text or "").strip()
    if not text:
        return []
    passages: list[Passage] = []
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()] or [text]
    for para in paragraphs:
        # 段落超限则按 max_chars 硬切
        for offset in range(0, len(para), max_chars):
            chunk = para[offset:offset + max_chars]
            passages.append(Passage(
                id=f"p_admin_{uuid.uuid4().hex[:8]}",
                text=chunk,
                tags=[],
                source="admin_note",
            ))
    return passages
```

- [x] **Step 4: 跑 PASS**

- [x] **Step 5: Checkpoint**

---

### Task 1.5: Tavily 改造（保留原文段产出 Passage list）

**Files:**
- Modify: `backend/services/research_broker.py`（加 `collect_passages` 方法，保留 `collect_artifacts` 不动以防 v1 链路用）
- Test: `backend/tests/test_research_broker_passages.py`

- [x] **Step 1: 失败测试**

```python
# backend/tests/test_research_broker_passages.py
import pytest
from unittest.mock import AsyncMock
from services.research_broker import ResearchBroker
from schemas.research import ResearchRequest

@pytest.mark.asyncio
async def test_collect_passages_from_tavily():
    fake_tavily = AsyncMock()
    fake_tavily.search.return_value = [
        {"title": "T1", "url": "u1", "content": "原文段一" * 30},
        {"title": "T2", "url": "u2", "content": "原文段二" * 50},
    ]
    broker = ResearchBroker(tavily=fake_tavily, web_searcher=None, llm_router=None)
    req = ResearchRequest(stage="world_base", goal="g", queries=["q1"])
    passages = await broker.collect_passages(req, max_chars=600)
    
    assert len(passages) == 2
    assert all(p.source == "tavily" for p in passages)
    assert all(len(p.text) <= 600 for p in passages)
    assert passages[0].tags  # tavily 路径应至少给 source URL tag

@pytest.mark.asyncio
async def test_collect_passages_empty_when_no_tavily():
    broker = ResearchBroker(tavily=None, web_searcher=None, llm_router=None)
    req = ResearchRequest(stage="world_base", goal="g", queries=["q1"])
    passages = await broker.collect_passages(req, max_chars=600)
    assert passages == []
```

- [x] **Step 2: 跑 FAIL**

- [x] **Step 3: 实现 `collect_passages`**

```python
# 加到 backend/services/research_broker.py
from schemas.research_pack import Passage
import uuid

class ResearchBroker:
    # ... 现有方法保留 ...
    
    async def collect_passages(self, request: ResearchRequest, max_chars: int) -> list[Passage]:
        if not self.tavily:
            return []
        passages: list[Passage] = []
        queries = self._dedupe_queries(request.queries, MAX_TAVILY_QUERIES_PER_REQUEST)
        for query in queries:
            try:
                results = await self.tavily.search(query, max_results=MAX_TAVILY_RESULTS_PER_QUERY)
            except Exception:
                continue
            for r in results:
                content = (r.get("content") or "")[:max_chars]
                if not content:
                    continue
                passages.append(Passage(
                    id=f"p_tav_{uuid.uuid4().hex[:8]}",
                    text=content,
                    tags=[f"source:{r.get('url', '')}", f"query:{query}"],
                    source="tavily",
                ))
        return passages
```

- [x] **Step 4: 跑 PASS**

- [x] **Step 5: Checkpoint**

---

### Task 1.6: IP probing LLM call

**Files:**
- Create: `backend/services/research_pack_builder.py` 加 `probe_ip_canon` 函数
- Test: `backend/tests/test_research_pack_ip_probe.py`

- [x] **Step 1: 失败测试**

```python
# backend/tests/test_research_pack_ip_probe.py
import pytest
import json
from unittest.mock import AsyncMock
from services.research_pack_builder import probe_ip_canon
from schemas.research_pack import IPCanon

@pytest.mark.asyncio
async def test_probe_ip_canon_returns_structured():
    fake_router = AsyncMock()
    fake_router.complete_json.return_value = json.dumps({
        "title_guesses": ["琅琊榜"],
        "canonical_names": ["梅长苏", "靖王"],
        "canonical_places": ["苏宅"],
        "iconic_objects": ["麒麟才子琅琊榜首"],
        "lingo": ["江左盟"],
        "notable_events": ["赤焰之案"],
    })
    canon = await probe_ip_canon("一个民国权谋世界，主角是梅长苏", llm_router=fake_router)
    assert isinstance(canon, IPCanon)
    assert "梅长苏" in canon.canonical_names

@pytest.mark.asyncio
async def test_probe_ip_canon_handles_invalid_json():
    fake_router = AsyncMock()
    fake_router.complete_json.return_value = "not json"
    canon = await probe_ip_canon("desc", llm_router=fake_router)
    # 失败时返回空 canon 不抛错
    assert canon.canonical_names == []
```

- [x] **Step 2: 跑 FAIL**

- [x] **Step 3: 实现**

```python
# 加到 backend/services/research_pack_builder.py
import json
from llm.router import LLMRouter
from schemas.research_pack import IPCanon
import structlog

logger = structlog.get_logger()

IP_PROBE_SYSTEM = """你是一个 IP / 题材识别助手。
给你一段世界生成描述，输出你（作为 LLM）已知的、与该描述强相关的：
- 候选作品名（title_guesses）
- 标志性人名（canonical_names）
- 标志性地名（canonical_places）
- 标志性物件（iconic_objects）
- 标志性称谓 / 台词风格（lingo）
- 著名事件名（notable_events）

如果描述指向你不熟悉的 IP / 原创世界，所有字段输出空数组即可。
严格 JSON 输出，不包含解释文字。"""

async def probe_ip_canon(description: str, llm_router: LLMRouter) -> IPCanon:
    try:
        text = await llm_router.complete_json(
            slot="research_summary",
            system=IP_PROBE_SYSTEM,
            messages=[{"role": "user", "content": description}],
            max_tokens=1024,
        )
        data = json.loads(text)
        return IPCanon(**{
            k: data.get(k, []) for k in (
                "title_guesses", "canonical_names", "canonical_places",
                "iconic_objects", "lingo", "notable_events",
            )
        })
    except Exception as exc:
        logger.warning("ip_probe_failed", error=str(exc))
        return IPCanon()
```

> 注：`LLMRouter.complete_json` 接口若不存在按现有 router 调用方式适配。

- [x] **Step 4: 跑 PASS**

- [x] **Step 5: Checkpoint**

---

### Task 1.7: ResearchPack 三路合并

**Files:**
- Modify: `backend/services/research_pack_builder.py` 加 `build_research_pack`
- Test: `backend/tests/test_research_pack_merge.py`

- [x] **Step 1: 失败测试**

```python
# backend/tests/test_research_pack_merge.py
import pytest
from unittest.mock import AsyncMock
from schemas.research_pack import Passage, IPCanon
from services.research_pack_builder import build_research_pack

@pytest.mark.asyncio
async def test_three_route_merge_dedup_and_priority():
    fake_broker = AsyncMock()
    fake_broker.collect_passages.return_value = [
        Passage(id="p_tav_1", text="tavily 内容", tags=[], source="tavily"),
    ]
    fake_broker.summarize_passages.return_value = "整体摘要"
    
    fake_router = AsyncMock()
    fake_router.complete_json.return_value = '{"canonical_names":["A"],"title_guesses":["B"]}'
    
    pack = await build_research_pack(
        description="一段描述。\n\n第二段。",
        broker=fake_broker,
        llm_router=fake_router,
        max_passages=100,
        max_passage_chars=600,
    )
    
    sources = {p.source for p in pack.passages}
    assert sources == {"tavily", "admin_note"}  # ip_probe 路径不出 passage，只出 canon
    assert pack.ip_canon.canonical_names == ["A"]
    assert pack.summary == "整体摘要"

@pytest.mark.asyncio
async def test_total_passages_capped_priority_admin_then_tavily():
    fake_broker = AsyncMock()
    fake_broker.collect_passages.return_value = [
        Passage(id=f"p_tav_{i}", text="x", tags=[], source="tavily")
        for i in range(60)
    ]
    fake_broker.summarize_passages.return_value = ""
    fake_router = AsyncMock()
    fake_router.complete_json.return_value = "{}"
    
    long_admin = "\n\n".join(["段落"] * 50)
    pack = await build_research_pack(
        description=long_admin,
        broker=fake_broker, llm_router=fake_router,
        max_passages=80, max_passage_chars=600,
    )
    # 80 总额：50 admin（优先）+ 30 tavily（截断）
    assert len(pack.passages) == 80
    admin_count = sum(1 for p in pack.passages if p.source == "admin_note")
    tavily_count = sum(1 for p in pack.passages if p.source == "tavily")
    assert admin_count == 50
    assert tavily_count == 30
```

- [x] **Step 2: 跑 FAIL**

- [x] **Step 3: 实现**

```python
# 加到 backend/services/research_pack_builder.py
from schemas.research_pack import ResearchPack
from schemas.research import ResearchRequest
import asyncio

async def build_research_pack(
    description: str,
    broker,                     # ResearchBroker 实例
    llm_router,                 # LLMRouter
    max_passages: int,
    max_passage_chars: int,
    research_request: ResearchRequest | None = None,
) -> ResearchPack:
    # 三路并发
    admin_task = asyncio.to_thread(slice_admin_note_to_passages, description, max_passage_chars)
    tavily_task = broker.collect_passages(
        research_request or ResearchRequest(stage="world_base", goal=description, queries=[description]),
        max_chars=max_passage_chars,
    )
    canon_task = probe_ip_canon(description, llm_router=llm_router)
    
    admin_passages, tavily_passages, ip_canon = await asyncio.gather(
        admin_task, tavily_task, canon_task,
    )
    
    # 容量裁剪：优先 admin > tavily > ip_probe（ip_probe 不产 passage）
    passages = list(admin_passages)
    remaining = max_passages - len(passages)
    if remaining > 0:
        passages.extend(tavily_passages[:remaining])
    
    # summary 兼容（v1 链路有用）
    summary = await broker.summarize_passages(passages) if passages else ""
    
    return ResearchPack(summary=summary, passages=passages, ip_canon=ip_canon)
```

- [x] **Step 4: 把 `summarize_passages` 加到 ResearchBroker**

```python
# backend/services/research_broker.py
async def summarize_passages(self, passages: list[Passage]) -> str:
    if not passages:
        return ""
    combined = "\n\n".join(p.text for p in passages[:30])  # 摘要不需要看全部
    # 复用现有 _summarize 逻辑或简化版
    return await self._summarize_text(combined)
```

- [x] **Step 5: 跑 PASS**

- [x] **Step 6: Checkpoint**

---

### Task 1.8: API 层容量上限校验

**Files:**
- Modify: `backend/api/admin.py` 的 `/world-generation-tasks` POST handler
- Test: `backend/tests/test_admin_world_gen_validation.py`

- [x] **Step 1: 失败测试**

```python
# backend/tests/test_admin_world_gen_validation.py
import pytest

@pytest.mark.asyncio
async def test_description_over_limit_rejected_422(admin_client):
    over = "x" * 60_000
    resp = await admin_client.post("/api/admin/world-generation-tasks", json={
        "description": over, "genre": "", "era": "",
    })
    assert resp.status_code == 422
    assert "description too long" in resp.json()["message"].lower()

@pytest.mark.asyncio
async def test_description_under_limit_ok(admin_client):
    resp = await admin_client.post("/api/admin/world-generation-tasks", json={
        "description": "正常长度描述", "genre": "", "era": "",
    })
    assert resp.status_code == 200
```

- [x] **Step 2: 跑 FAIL**

- [x] **Step 3: 加 API 校验**

```python
# backend/api/admin.py 在 /world-generation-tasks handler 入口加：
from config import settings

@router.post("/world-generation-tasks")
async def create_world_generation_task(req: WorldGenerationRequest, ...):
    if len(req.description) > settings.research_pack_max_admin_description_chars:
        raise HTTPException(
            status_code=422,
            detail=f"description too long (max {settings.research_pack_max_admin_description_chars} chars)",
        )
    # ... 现有逻辑
```

- [x] **Step 4: 同步加到 `/script-generation-tasks`**（outline 字段同样校验）

- [x] **Step 5: 跑 PASS**

- [x] **Step 6: Checkpoint**

---

### Task 1.9: WorldCreatorAgent v2 入口（feature flag 切换）

**Files:**
- Create: `backend/services/world_creator_agent_v2.py`
- Modify: `backend/services/generation_task_service.py`
- Test: `backend/tests/test_world_creator_v2_entry.py`

- [x] **Step 1: 失败测试**

```python
# backend/tests/test_world_creator_v2_entry.py
import pytest
from unittest.mock import patch

@pytest.mark.asyncio
async def test_v2_flag_off_uses_v1(generation_task_service):
    with patch("config.settings.world_creator_v2_enabled", False):
        with patch("services.world_creator_agent.WorldCreatorAgent.create_world") as v1_mock:
            v1_mock.return_value = mock_async_gen([{"event": "done", "data": {}}])
            await generation_task_service.launch_world_generation("task_id_v1")
            v1_mock.assert_called_once()

@pytest.mark.asyncio
async def test_v2_flag_on_uses_v2(generation_task_service):
    with patch("config.settings.world_creator_v2_enabled", True):
        with patch("services.world_creator_agent_v2.WorldCreatorAgentV2.create_world") as v2_mock:
            v2_mock.return_value = mock_async_gen([{"event": "done", "data": {}}])
            await generation_task_service.launch_world_generation("task_id_v2")
            v2_mock.assert_called_once()
```

> `mock_async_gen` 是测试 helper：把 list 包成 async generator。在 `tests/conftest.py` 加。

- [x] **Step 2: 跑 FAIL**

- [x] **Step 3: 创建 v2 入口骨架**

```python
# backend/services/world_creator_agent_v2.py
"""WorldCreator Agent v2 — ResearchPack-driven 12-stage generation."""
from typing import AsyncIterator

class WorldCreatorAgentV2:
    def __init__(self, llm, image_gen, broker, prompt_builder, strategy_service):
        self.llm = llm
        self.image_gen = image_gen
        self.broker = broker
        self.prompt_builder = prompt_builder
        self.strategy_service = strategy_service
    
    async def create_world(self, description: str, genre: str = "", era: str = "") -> AsyncIterator[dict]:
        # M1 阶段只跑 research_pack 阶段，其余 emit "not_implemented" warning
        from services.research_pack_builder import build_research_pack
        from config import settings
        
        yield {"event": "progress", "data": {"phase": "research_pack", "code": "started", "meta": {"stage_index": 0, "total_stages": 12}}}
        pack = await build_research_pack(
            description=description,
            broker=self.broker,
            llm_router=self.llm,
            max_passages=settings.research_pack_max_passages,
            max_passage_chars=settings.research_pack_max_passage_chars,
        )
        yield {"event": "progress", "data": {"phase": "research_pack", "code": "completed", "meta": {
            "stage_index": 0, "total_stages": 12,
            "payload_summary": {"passages": len(pack.passages), "canonical_names": len(pack.ip_canon.canonical_names)},
        }}}
        # M2-M5 阶段后续 milestone 填，本 milestone 暂时 emit not_yet 然后 done
        yield {"event": "warning", "data": {"phase": "world_base", "code": "not_yet_implemented", "message": "v2 后续 milestone 实现"}}
        yield {"event": "result", "data": {"research_pack": pack.dict()}}
        yield {"event": "done", "data": {}}
```

- [x] **Step 4: 改 `generation_task_service.launch_world_generation`**

```python
# backend/services/generation_task_service.py 找到 launch_world_generation
from config import settings
from services.world_creator_agent import WorldCreatorAgent
from services.world_creator_agent_v2 import WorldCreatorAgentV2

async def launch_world_generation(self, task_id: str):
    task = await self._load_task(task_id)
    payload = task.request_payload
    
    if settings.world_creator_v2_enabled:
        agent = WorldCreatorAgentV2(...)  # 现有 dependency 注入照搬
    else:
        agent = WorldCreatorAgent(...)
    
    async for event in agent.create_world(payload["description"], payload.get("genre", ""), payload.get("era", "")):
        await self._record_event(task_id, event["event"], event["data"])
    # ... 现有 status 更新逻辑
```

- [x] **Step 5: 跑 PASS**

- [x] **Step 6: Checkpoint**

---

### Task 1.10: intermediate_state 写入

**Files:**
- Modify: `backend/services/generation_task_service.py`
- Test: `backend/tests/test_intermediate_state.py`

- [x] **Step 1: 失败测试**

```python
# backend/tests/test_intermediate_state.py
import pytest
from sqlalchemy import select
from models.generation_task import GenerationTask

@pytest.mark.asyncio
async def test_intermediate_state_merge_on_completed_event(generation_task_service, db):
    task = await generation_task_service.start_world_generation(...)
    
    # 模拟 phase=research_pack 的 completed 事件
    await generation_task_service.record_intermediate(
        task.id,
        phase="research_pack",
        snapshot={"passages": [], "ip_canon": {"canonical_names": ["A"]}},
    )
    await generation_task_service.record_intermediate(
        task.id,
        phase="lore_pack",
        snapshot={"dimensions": []},
    )
    
    refreshed = (await db.execute(select(GenerationTask).where(GenerationTask.id == task.id))).scalar_one()
    assert "research_pack" in refreshed.intermediate_state
    assert "lore_pack" in refreshed.intermediate_state
    # research_pack 不被覆盖
    assert refreshed.intermediate_state["research_pack"]["ip_canon"]["canonical_names"] == ["A"]
```

- [x] **Step 2: 跑 FAIL**

- [x] **Step 3: 实现 `record_intermediate`**

```python
# backend/services/generation_task_service.py
async def record_intermediate(self, task_id: str, phase: str, snapshot: dict):
    """每阶段 completed 时调用，merge 到 intermediate_state JSON 字段。"""
    async with self.session_factory() as session:
        try:
            task = (await session.execute(
                select(GenerationTask).where(GenerationTask.id == task_id).with_for_update()
            )).scalar_one()
            current = dict(task.intermediate_state or {})
            current[phase] = snapshot
            task.intermediate_state = current
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```

- [x] **Step 4: WorldCreatorAgentV2 在每个 phase completed 时调用 `record_intermediate`**

> 改 `world_creator_agent_v2.py` 里 yield completed 之前调 `await task_service.record_intermediate(self.task_id, phase, snapshot)`。
> 这意味着 v2 agent 需要持有 task_id（在 `launch_world_generation` 创建 v2 agent 时传入）。

- [x] **Step 5: 跑 PASS**

- [x] **Step 6: Checkpoint**

---

### Task 1.11: 草稿编辑器展示 ResearchPack（read-only）

**Files:**
- Create: `frontend/components/admin/editor/sections/ResearchPackSection.tsx`
- Modify: `frontend/components/admin/editor/DraftEditorShell.tsx` 注册新 section

- [x] **Step 1: 写组件**

```tsx
// frontend/components/admin/editor/sections/ResearchPackSection.tsx
import { JsonField } from "../JsonField";

type Props = {
  researchPack?: {
    summary?: string;
    passages?: Array<{ id: string; text: string; source: string; tags: string[] }>;
    ip_canon?: {
      title_guesses?: string[];
      canonical_names?: string[];
      canonical_places?: string[];
    };
  };
};

export function ResearchPackSection({ researchPack }: Props) {
  if (!researchPack) return null;
  return (
    <section className="lv-section">
      <h2 className="lv-t-h2">研究包（read-only）</h2>
      <div className="text-meta opacity-70">摘要</div>
      <p className="lv-t-body whitespace-pre-wrap">{researchPack.summary ?? "—"}</p>
      
      <div className="lv-t-h3 mt-4">IP Canon</div>
      <ul className="lv-t-body">
        <li>候选作品：{researchPack.ip_canon?.title_guesses?.join(" / ") || "—"}</li>
        <li>人名：{researchPack.ip_canon?.canonical_names?.join("、") || "—"}</li>
        <li>地名：{researchPack.ip_canon?.canonical_places?.join("、") || "—"}</li>
      </ul>
      
      <div className="lv-t-h3 mt-4">Passages（{researchPack.passages?.length ?? 0} 条）</div>
      <details>
        <summary className="lv-t-body cursor-pointer">展开</summary>
        <JsonField value={researchPack.passages ?? []} />
      </details>
    </section>
  );
}
```

- [x] **Step 2: 在 DraftEditorShell 注册**

修改 `frontend/components/admin/editor/DraftEditorShell.tsx` 的 section 列表，加上 ResearchPackSection（仅在 draft.payload.research_pack 存在时展示）。

- [x] **Step 3: 手动测**

启动 `cd frontend && npm run dev`，admin 后台跑一次 v2 generation（先在 .env 临时设 `WORLD_CREATOR_V2_ENABLED=true`），打开 draft editor 验证 ResearchPack 显示正常。

- [x] **Step 4: Checkpoint**

记录 M1 完成 + 截图存 `checkpoints/2026-05-10-task-1.11.md`。

---

### M1 验收

- [x] 所有 task 单元测试 PASS
- [x] 在 `WORLD_CREATOR_V2_ENABLED=false` 下旧 v1 链路完全不受影响（手动跑一次 v1 生成验证）
- [x] 在 `WORLD_CREATOR_V2_ENABLED=true` 下生成任务跑出 ResearchPack（含 passages + IPCanon），admin 在草稿编辑器看得到
- [x] `generation_tasks.intermediate_state.research_pack` 字段被正确写入
- [x] 手动构造 60K char description，POST 返回 422
- [x] 写 M1 总结到 `docs/superpowers/plans/checkpoints/2026-05-M1-summary.md`：实际工时 / 偏离预估的部分 / M2 入场前需要先解决的遗留

---

## 3. Milestone 2: World 厚度（角色分批 + lore_pack + shared_events + relations_pack）

> 目标：admin 跑一次 v2 生成产出含 30+ 完整 NPC、动态 lore_pack（≥1 维度）、≥10 条 shared_events（含 source_passage_ids）、每 NPC ≥3 条 important_relations 的 world 草稿。

> 任务清单（M1 完成后细化到 step 级别）：

### Task 2.1: lore_dimensions 阶段

**Files:** `backend/services/lore_pack_builder.py` (new), `backend/services/generation_prompt_builder.py` (modify), `backend/tests/test_lore_dimensions.py` (new)

**Approach:** planner LLM (slot=`research_planning`) 根据 description + ResearchPack.ip_canon 输出 dimensions 清单 `[{key, name, why_relevant}]`，2-6 个；轻 critic 兜底（如题材不需要可输出空）。

### Task 2.2: lore_pack 逐维度生成（并发）

**Files:** `lore_pack_builder.py` 加 `build_dimension_content`, `world_creator_agent_v2.py` 接入

**Approach:** `asyncio.gather` 并发 4 路（受 `Semaphore` 限），每路独立 LLM call (slot=`admin_generation`)，每维度产 `content_blocks: [{heading, body}]`；emit subtask_started/completed 事件。

### Task 2.3: character_roster 阶段

**Files:** `backend/services/character_roster_builder.py` (new), `backend/tests/test_character_roster.py`

**Approach:** planner LLM 出 N 名字 + role_tag + 派系归属 + is_image_target（playable 必标 true，其他启发式标 N_image_target）。N 由 LLM 自决（描述里有"我要 30 个角色"启发式提取，否则按题材规模启发式 12-30）。

### Task 2.4: characters 分批生成

**Files:** `character_roster_builder.py` 加 `build_characters_in_batches`, `world_creator_agent_v2.py`

**Approach:** roster N 人 → ⌈N/6⌉ 批，每批 ≤6 人，并发 4 路（Semaphore）；每批 LLM 收 ResearchPack + lore_pack + 本批 roster 子集 + brief；批后 dedup 校验（roster name 1:1，多/少/重命名都报错回退 retry）。

### Task 2.5: shared_events 抽取 + LLM 补

**Files:** `backend/services/shared_events_builder.py` (new), `backend/tests/test_shared_events.py`

**Approach:** 第一步从 ResearchPack.passages 抽取（LLM call 输入 passages 子集 + characters，输出 shared_events 含 source_passage_ids）；第二步如总数 < K_min=5，LLM 补到 K_min；第三步 form 校验（involved_npcs ⊆ characters.name）。

### Task 2.6: relations_pack 反向推导（无 LLM）

**Files:** `backend/services/relations_pack_builder.py` (new), `backend/tests/test_relations_pack.py`

**Approach:** Python 计算：每 NPC important_relations = `set(shared_events 涉及自己的 → 拉对方) | set(同派系核心) | set(敌对派系核心)`；每条 relation 含 `(target, trust, kind, why → shared_event_id 或 "faction:X")`。

### Task 2.7: 串入 world_creator_agent_v2

**Files:** `world_creator_agent_v2.py`

**Approach:** 按 spec §12.3 并发图执行：world_base 之后，C1+C2 并发；D1+D2 跨阶段并发；E1 等 D2 完成后跑；E2 等 E1 完成后跑（Python，瞬时）；每个阶段 emit started/completed + intermediate_state snapshot。

### Task 2.8: 草稿编辑器新 section

**Files:** `frontend/components/admin/editor/sections/LorePackSection.tsx`, `CharactersSection.tsx`（升级现有显示 30+ 角色）, `SharedEventsSection.tsx`

### M2 验收
- 30 NPC 规模 world 生成跑通，跨批 dedup 通过
- shared_events ≥ 60% 含 source_passage_ids 非空
- lore_pack 至少 1 个维度有 ≥2 个 content_blocks
- 草稿编辑器展示新 section 完整

---

## 4. Milestone 3: 事件骨架 + condition_dsl

> 目标：world 草稿含 events_data ≥ 5 条（含 rumors），condition_dsl 解析器单元测试覆盖率 ≥ 90%。

### Task 3.1: condition_dsl 解析器

**Files:** `backend/engine/condition_dsl.py` (new), `backend/tests/test_condition_dsl.py`

**Approach:** 自写 mini-parser（spec Q4 决策）。白名单 ops：
- 二元：`AND` `OR` `>` `>=` `<` `<=` `==` `!=`
- 一元：`NOT`
- 函数：`time_after('day_N')` / `location_is('name')` / `player_did('action_phrase')`
- 字段引用：`world_state.<key>`（lookup `game_state.world_state[key]`）

实现：`tokenize → parse_expr (递归下降) → eval(game_state) → bool`。无函数调用解析（白名单内函数调用是字面 sentinel，不是 Python 调用）。fuzzer 测试拒绝任何注入字符。

### Task 3.2: events_data 生成阶段

**Files:** `backend/services/events_data_builder.py` (new), `backend/tests/test_events_data_builder.py`

**Approach:** LLM 收 ResearchPack + characters + locations + shared_events + lore_pack，输出 events_data list（kind=`npc_intent_driven` / `conditional`，每条含 trigger.condition_dsl + rumors）。生成期校验：condition_dsl 用 `condition_dsl.parse(...)` 解析，失败的 event 标 disabled + warning。引用一致性校验（spec §4.4 表格）。

### Task 3.3: rumors schema + knower_npcs 校验

**Files:** `events_data_builder.py` 内, `tests/test_events_data_rumors.py`

**Approach:** 每条 event 至少 1 条 rumor（如 LLM 没生成强制补一条空模板让 admin 后续填）；knower_npcs ⊆ characters.name 校验。

### Task 3.4: 串入 world_creator_agent_v2

**Files:** `world_creator_agent_v2.py`

**Approach:** stage F: events_data，依赖 lore_pack + characters + shared_events + locations 全部完成；分批生成（每批 ≤5 events），并发 3 路；emit subtask_*。

### M3 验收
- events_data ≥ 5 条，每条 condition_dsl 可被解析器接受
- 至少 3 条 events kind=npc_intent_driven，2 条 kind=conditional
- 至少 50% events 含 ≥1 条 rumors
- DSL fuzzer 测试通过（10K 随机注入字符不崩）

---

## 5. Milestone 4: 质量与容错（Critic 分级 + moderation + retry/checkpoint）

### Task 4.1: 形状校验（无 LLM）

**Files:** `backend/services/world_critic_service.py` (new), `tests/test_world_critic_shape.py`

**Approach:** Python 函数 `validate_world_shape(world_payload) → list[ValidationError]`，按 spec §4.4 表格全部校验。返回错误 list，给 critic gate 决定是 fail 还是 标 quality_warning。

### Task 4.2: 轻 critic（lore + shared_events）

**Files:** `world_critic_service.py` 加 `light_critic_lore` / `light_critic_shared_events`

**Approach:** 每个一次 LLM pass（slot=`admin_generation`），输入产物 + ip_canon，输出 `{warnings: [string]}`，无修复——warnings 直接进 quality_warnings。

### Task 4.3: 重 critic（characters + playable）保留 + 接入 v2

**Files:** `world_critic_service.py` 加 `heavy_critic_characters` 包装现有逻辑

**Approach:** 现有 `_normalize_generation_review_result` + `_build_repair_note` 抽到新 service，v2 调用相同逻辑。

### Task 4.4: 运行时校验 events_data

**Files:** `world_critic_service.py` 加 `validate_events_runtime`

**Approach:** 用 `condition_dsl.parse` 检查每个 event.trigger.condition_dsl，失败的 event 标 `disabled=true` + warning（不阻断发布）。

### Task 4.5: Moderation pass

**Files:** `backend/services/world_moderation_service.py` (new), `tests/test_world_moderation.py`

**Approach:** 抽样所有自由文本字段（characters[].personality / characters[].secret / shared_events[].summary / events_data[].summary / lore_pack content_blocks），调 `services/moderation.py` 现有接口（slot=`moderation_slot`），命中标 `quality_warnings: ["moderation_flag:<reason>"]`，**不阻断生成**。

### Task 4.6: 发布前 moderation 拦截

**Files:** `backend/api/admin.py` 的 `publish_world_draft` / `publish_script_draft`

**Approach:** commit 前检查 `payload.quality_warnings` 含 `moderation_flag:*`，含则要 admin 显式发 `?force_publish=true` query param 才允许发布；否则 422 + 详情。

### Task 4.7: LLM 阶段 transient retry

**Files:** `backend/services/world_creator_agent_v2.py` 加 `_with_retry` 装饰器

**Approach:** 定义 `transient_exceptions = (APIConnectionError, APITimeoutError, RateLimitError, ServerError)`，写 wrapper：
```python
async def _with_retry(coro_factory, max_attempts=2, backoffs=(1, 3)):
    for attempt in range(max_attempts + 1):
        try:
            return await coro_factory()
        except transient_exceptions as exc:
            if attempt >= max_attempts:
                raise
            await emit_warning("transient_retry", attempt=attempt+1, max_attempts=max_attempts+1)
            await asyncio.sleep(backoffs[attempt])
```

每个 LLM stage 用 `_with_retry(lambda: self.llm.complete_json(...))` 包裹。

### Task 4.8: 集成测试（容错 + critic）

**Files:** `backend/tests/test_world_creator_v2_resilience.py`

**Approach:** mock LLM 注入 transient timeout（前 2 次失败、第 3 次成功），断言 retry 自动救活；mock LLM 输出违反 shape 校验的产物，断言 critic gate 标 quality_warnings；mock moderation 命中，断言发布拦截 422。

### M4 验收
- 所有 critic 档位测试 PASS
- transient retry 集成测试 PASS（失败 → 自动 retry → 成功）
- moderation 命中场景下 publish 默认拒绝 + force_publish 可强制
- intermediate_state 在每阶段 completed 时可见

---

## 6. Milestone 5: 运行时 + 前端 + Script 模式

### Task 5.1: NPC Agent 注入 relevant_lore

**Files:** `backend/engine/memory_manager.py` 加 `find_relevant_lore`, `backend/engine/orchestrator.py` 加 kwargs, `backend/engine/npc_agent.py` 接入 prompt

**Approach:**
- `find_relevant_lore(npc_knowledge: list[str], lore_pack: dict, top_k=3) → list[ContentBlock]`：用 `services/embedding_service.py` 余弦匹配 npc.knowledge 字段与 lore_pack 各 content_blocks
- orchestrator 在构建 npc_tasks kwargs 时调用，传 `relevant_lore` 字段
- npc_agent prompt 加段："## 相关世界规则（可引用，避免编造）"

### Task 5.2: NPC Agent 注入 involved_shared_events

**Files:** `memory_manager.py` 加 `find_npc_shared_events`, `orchestrator.py`, `npc_agent.py`

**Approach:** `find_npc_shared_events(npc_name, shared_events) → list`，过滤 `involved_npcs` 含该 NPC 的事件，每条 event 用 `perceptions[npc_name]` 视角呈现（不泄露其他 NPC 的认知）。

### Task 5.3: NPC Agent 注入 relevant_rumors

**Files:** `memory_manager.py` 加 `find_npc_rumors`, `orchestrator.py`, `npc_agent.py`

**Approach:** `find_npc_rumors(npc_name, events_data, triggered_event_ids: set) → list[str]`，过滤未触发 events 中 `rumors[].knower_npcs` 含该 NPC 的 rumor 文本；NPC Agent prompt 提示"如对话话题相关，可自然提及，不要每轮都提"。

### Task 5.4: world_simulator 接入 events_data

**Files:** `backend/engine/world_simulator.py`, `backend/tests/test_world_simulator_events.py`

**Approach:** `tick(game_state, world_data)` 末尾加：
- 遍历 `world_data.get("events_data", [])`
- 跳过 `disabled=true`
- 解析 trigger.condition_dsl，eval 通过 → 命中
- kind=conditional：产出 world_event，应用 effects 到 game_state
- kind=npc_intent_driven：注入 `game_state.npc_intents[npc_name] = intent_payload`
- 已触发的 event id 记到 `game_state.triggered_event_ids`（防重复触发）

### Task 5.5: 前端 SSE 反馈协议

**Files:** `frontend/lib/admin-sse-events.ts`

**Approach:** 加 `ProgressMeta` interface（spec §8.3），`dispatchAdminSseEvent` 解析 meta 字段透传给 onProgress 回调。

### Task 5.6: DraftEditorShell stages map + 子任务进度条

**Files:** `frontend/components/admin/editor/DraftEditorShell.tsx`

**Approach:** 维护 `stages: Map<phase, StageStatus>` state；onProgress 回调按 code 转移状态机（`started → running`，`completed → completed`，`subtask_started → 子任务计数`）；UI 渲染顶部进度条（主阶段 X/12）+ 当前阶段子任务条（M/N）。

### Task 5.7: Script 模式同步升级

**Files:** `backend/services/world_creator_agent_v2.py` 的 `create_script` 方法

**Approach:** 复用 v2 的 ResearchPack / events_data_builder（kind 含 a+b+c）/ critic 分级；不重出 characters/lore_pack/shared_events（继承 world）。

### Task 5.8: 端到端集成测试

**Files:** `backend/tests/test_world_creator_v2_e2e.py`, `backend/tests/test_script_creator_v2_e2e.py`

**Approach:** mock LLM 出固定产物，跑完整 12 阶段 flow，断言：
- 事件序列完整（每阶段 started + completed）
- 并发主阶段含 subtask_started + subtask_completed
- intermediate_state 增量正确
- 最终 result 含所有新字段

### Task 5.9: 上线前 acceptance test（手动）

跑一次真实 IP 复刻（如"《琅琊榜》风格民国权谋"），人工对照 spec §13 AC1-AC10 验收清单逐条勾选。

### M5 验收
- AC1-AC10 全部通过
- 真实 30 NPC world 生成总耗时 ≤ 35 min P50
- 玩家在自由世界游玩 30 分钟撞到 ≥1 个 events_data 触发或 ≥1 条 rumor

---

## 7. 上线流程

1. 所有 milestone 完成
2. `WORLD_CREATOR_V2_ENABLED=true` 在 staging 跑 5 次真实生成（不同 IP / 题材），人工评估质量
3. prod 默认改 `WORLD_CREATOR_V2_ENABLED=true`
4. 观察 1 周（generation_tasks 表跑统计 + admin 反馈），无重大问题
5. 删除 v1 代码（`world_creator_agent.py` 标 deprecated 一周后删，`world_creator_agent_v2.py` rename 回 `world_creator_agent.py`）

---

## 8. 后续 milestone（不在本 plan 范围）

按 spec §11 非目标列表，以下留作未来：
- 任意阶段 resume
- 文件上传（PDF / 文档作为素材）
- 老世界 backfill
- events_data leakage 兜底（trigger d）
- 草稿编辑全套结构化 UI
- Tavily fallback 链
- task cancellation
- director_agent 改造（按 location 预过滤）
- 持久化研究缓存

---

> Plan 完。M1 详细，M2-M5 高层。M(N-1) 完成后 invoke writing-plans 细化 M(N) 到 step 级别。
