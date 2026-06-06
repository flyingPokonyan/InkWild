# IP Fidelity Engine — Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把"输入 IP 名 → 生成出忠于原作的世界（关键人物全员到位 + 核心地名/势力对齐）"做成创作工坊的核心能力。Phase 1 验证整套思路，目标是逐玉这种 cutoff 之后的新剧也能复刻男女主 + 至少 1 个二级角色（如李怀安）+ 临安镇 + 武安侯将军等核心元素。

**Architecture:** 在现有 14 阶段流水线开头插入 Stage 0「IP 识别」，根据置信度展示中介卡片让 admin 选 strict/loose/none 三档复刻模式；strict/loose 时跑 IP Research 子流水线（Tavily + 维基多源 RAG 抽取出 IPKnowledgePack 落表），下游 world_base/character_roster/characters 三个核心 stage prompt 从「参考」改为「必须使用」硬约束。Pipeline 暂停通过两阶段 generation_task 实现（Stage 0 task succeed → 前端展示卡片 → 调 continue 接口启动 phase_b task）。

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy 2.0 async / Alembic / Pydantic / Tavily / 现有 LLMRouter / Next.js 16 / React 19 / TanStack Query / Zustand

**Spec:** [`docs/superpowers/specs/2026-05-14-ip-fidelity-engine-design.md`](../specs/2026-05-14-ip-fidelity-engine-design.md)

**Out of Phase 1 scope** (留给 Phase 2/3)：
- 百度百科 / 萌百 / 游侠 直抓 parser（Phase 1 全靠 Tavily `site:` 搜索）
- lore_dimensions / shared_events / events_data 的 prompt 改造（先改最关键的 3 个 stage）
- critic IP 一致性硬卡口
- IP 复刻金标准测试集 + 逐玉重生成对比样板（Phase 3）
- admin 后台 IP Pack 只读查看页

---

## File Structure

### 新增文件

| 文件 | 责任 |
|---|---|
| `backend/schemas/ip_knowledge_pack.py` | IPCharacter / IPPlace / IPKnowledgePack pydantic schemas |
| `backend/models/ip_knowledge_pack.py` | SQLAlchemy ORM 模型 |
| `backend/migrations/versions/<hash>_add_ip_knowledge_packs.py` | Alembic migration |
| `backend/services/ip_recognizer.py` | Stage 0：IP 识别 LLM call + Tavily verify |
| `backend/services/ip_pack_extractors/__init__.py` | 抓取源插件目录 |
| `backend/services/ip_pack_extractors/wikipedia.py` | zh.wikipedia.org 直抓 + parse |
| `backend/services/ip_pack_extractors/tavily_site.py` | Tavily `site:` 多源搜索包装 |
| `backend/services/ip_research_pipeline.py` | 多源抓取 + RAG 抽取 + 完整性自检 |
| `backend/services/ip_pack_storage.py` | IPKnowledgePack 落表 / 查询 |
| `backend/tests/test_ip_recognizer.py` | recognizer mock 测试 |
| `backend/tests/test_ip_research_pipeline.py` | pipeline 集成测试（mock LLM/HTTP） |
| `backend/tests/test_ip_pack_extractors.py` | extractors 单测（含真实 wiki fixtures） |
| `frontend/components/admin/workshop/IPRecognitionCard.tsx` | 中介卡片 UI |

### 修改文件

| 文件 | 变更 |
|---|---|
| `backend/services/world_creator_agent_v2.py` | Stage 0 注入到 pipeline 开头；下游 world_base/character_roster/characters 接 IPKnowledgePack 并改 prompt 为硬约束 |
| `backend/services/character_roster_builder.py` | prompt 改为「必须包含 must_have characters」 |
| `backend/services/generation_task_service.py` | 支持「Stage 0 完成后暂停 + continue」两阶段任务 |
| `backend/api/admin.py` | 新增 `POST /admin/world-drafts/{id}/continue-generation` 接口；草稿 payload 接受 `fidelity_mode` 字段 |
| `backend/schemas/research_pack.py` | 保留向后兼容；标注 IPCanon 为 deprecated 注释 |
| `frontend/lib/admin-sse-events.ts` | 新增 `IPRecognitionEvent` 类型 |
| `frontend/components/admin/editor/DraftEditorShell.tsx` | 收到 ip_recognition 事件时渲染 IPRecognitionCard |

---

## Task 1：IPKnowledgePack pydantic schemas

**Files:**
- Create: `backend/schemas/ip_knowledge_pack.py`
- Test: `backend/tests/test_ip_knowledge_pack_schema.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_ip_knowledge_pack_schema.py
from schemas.ip_knowledge_pack import (
    IPCharacter, IPPlace, IPKnowledgePack, FidelityMode,
)


def test_ip_character_minimal():
    c = IPCharacter(
        name="樊长玉",
        role_in_story="女主",
        relation_to_protagonist="本人",
        traits=["坚韧", "天生神力"],
        must_have=True,
        source_passage_ids=["p_tav_67fbf021"],
    )
    assert c.must_have is True
    assert c.name == "樊长玉"


def test_ip_knowledge_pack_full():
    pack = IPKnowledgePack(
        ip_name="逐玉",
        ip_type="tv",
        fidelity_mode="strict",
        summary="屠户女与落难侯爷假婚成真...",
        characters=[
            IPCharacter(name="樊长玉", role_in_story="女主",
                        relation_to_protagonist="本人", traits=[], must_have=True,
                        source_passage_ids=[]),
        ],
        places=[
            IPPlace(name="临安镇", description="女主家乡", must_have=True, source_passage_ids=[]),
        ],
        factions=[],
        iconic_objects=[],
        key_events=[],
        tone_lingo=[],
        passages=[],
    )
    assert pack.must_have_character_names() == ["樊长玉"]
    assert pack.must_have_place_names() == ["临安镇"]


def test_fidelity_mode_literal():
    pack = IPKnowledgePack(ip_name="X", ip_type="other", fidelity_mode="loose",
                           summary="", characters=[], places=[], factions=[],
                           iconic_objects=[], key_events=[], tone_lingo=[], passages=[])
    assert pack.fidelity_mode == "loose"
```

Run: `cd backend && python -m pytest tests/test_ip_knowledge_pack_schema.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 2: Implement schemas**

```python
# backend/schemas/ip_knowledge_pack.py
"""IP Knowledge Pack — 高复刻 IP 的结构化原作知识包。

下游 world_creator stage 接收此 pack 替代旧的 IPCanon，
通过硬约束 prompt 保证生成的世界忠于原作。
"""
from typing import Literal

from pydantic import BaseModel, Field

from schemas.research_pack import Passage

FidelityMode = Literal["strict", "loose", "none"]


class IPCharacter(BaseModel):
    name: str
    role_in_story: str  # "女主" / "男主" / "反派" / "配角" 等
    relation_to_protagonist: str  # "本人" / "丈夫" / "师兄" / "母亲" 等
    traits: list[str] = Field(default_factory=list)
    must_have: bool  # 是否核心人物，critic 用
    source_passage_ids: list[str] = Field(default_factory=list)


class IPPlace(BaseModel):
    name: str
    description: str = ""
    must_have: bool = False
    source_passage_ids: list[str] = Field(default_factory=list)


class IPFaction(BaseModel):
    name: str
    description: str = ""
    source_passage_ids: list[str] = Field(default_factory=list)


class IPObject(BaseModel):
    name: str
    description: str = ""
    source_passage_ids: list[str] = Field(default_factory=list)


class IPEvent(BaseModel):
    name: str
    description: str = ""
    source_passage_ids: list[str] = Field(default_factory=list)


class IPKnowledgePack(BaseModel):
    ip_name: str
    ip_type: str  # "tv" / "movie" / "novel" / "anime" / "game" / "other"
    fidelity_mode: FidelityMode
    summary: str
    characters: list[IPCharacter]
    places: list[IPPlace]
    factions: list[IPFaction]
    iconic_objects: list[IPObject]
    key_events: list[IPEvent]
    tone_lingo: list[str]
    passages: list[Passage]

    def must_have_character_names(self) -> list[str]:
        return [c.name for c in self.characters if c.must_have]

    def must_have_place_names(self) -> list[str]:
        return [p.name for p in self.places if p.must_have]
```

- [ ] **Step 3: Run tests**

Run: `cd backend && python -m pytest tests/test_ip_knowledge_pack_schema.py -v`
Expected: 3 PASS

- [ ] **Step 4: Commit**

```bash
git add backend/schemas/ip_knowledge_pack.py backend/tests/test_ip_knowledge_pack_schema.py
git commit -m "feat(ip-fidelity): add IPKnowledgePack schemas"
```

---

## Task 2：ip_knowledge_packs 表 model + migration

**Files:**
- Create: `backend/models/ip_knowledge_pack.py`
- Create: `backend/migrations/versions/<auto>_add_ip_knowledge_packs.py`
- Modify: `backend/models/__init__.py`（确认新 model 被导入，便于 metadata 收集）

- [ ] **Step 1: Implement model**

```python
# backend/models/ip_knowledge_pack.py
from datetime import datetime
from uuid import uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class IPKnowledgePack(Base):
    __tablename__ = "ip_knowledge_packs"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    world_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("worlds.id"), nullable=True, index=True)
    draft_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("world_drafts.id"), nullable=True, index=True)
    ip_name: Mapped[str] = mapped_column(String(200), nullable=False)
    fidelity_mode: Mapped[str] = mapped_column(String(20), nullable=False)
    pack_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
```

Add import to `backend/models/__init__.py` so Alembic autogenerate sees it:

```python
# 在已有 imports 下添加
from .ip_knowledge_pack import IPKnowledgePack  # noqa: F401
```

- [ ] **Step 2: Generate migration**

Run:
```bash
cd backend && alembic revision --autogenerate -m "add ip_knowledge_packs"
```

Inspect the generated file under `backend/migrations/versions/`. Verify it contains `op.create_table("ip_knowledge_packs", ...)` and the indexes on `world_id` and `draft_id`. Tweak if autogenerate misses anything (常见：JSON 列在 SQLite 跑测试时需要 `JSON` 而非 `JSONB`；保持 JSON 即可，跨 DB 兼容)。

- [ ] **Step 3: Apply migration**

Run:
```bash
docker exec talealive-backend-1 alembic upgrade head
docker exec talealive-db-1 psql -U postgres -d talealive -c "\d ip_knowledge_packs"
```
Expected: 表结构包含 id / world_id / draft_id / ip_name / fidelity_mode / pack_json / created_at

- [ ] **Step 4: Commit**

```bash
git add backend/models/ip_knowledge_pack.py backend/models/__init__.py backend/migrations/versions/*_add_ip_knowledge_packs.py
git commit -m "feat(ip-fidelity): add ip_knowledge_packs table"
```

---

## Task 3：IP Recognizer service（Stage 0）

**Files:**
- Create: `backend/services/ip_recognizer.py`
- Create: `backend/tests/test_ip_recognizer.py`

- [ ] **Step 1: Define schema additions in same file as recognizer**

```python
# backend/services/ip_recognizer.py
"""Stage 0：从用户自由文本识别是否指向某个已知 IP。

输出 IPRecognition：kind / confidence / ip_name / ip_type / one_liner / source_hints
后续 Stage A+ 仅当 kind in (known_ip, hybrid) 时执行 IP Research。
"""
import json
from typing import Any, Literal

import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger()

IPKind = Literal["known_ip", "hybrid", "original"]
IPType = Literal["tv", "movie", "novel", "anime", "game", "other"]


class IPRecognition(BaseModel):
    kind: IPKind
    confidence: float = Field(ge=0.0, le=1.0)
    ip_name: str | None = None
    ip_type: IPType | None = None
    one_liner: str | None = None
    source_hints: list[str] = Field(default_factory=list)


_RECOGNIZER_SYSTEM = """你判断用户输入的世界描述是否指向某个已知 IP（影视剧 / 小说 / 动漫 / 游戏）。

输出 JSON，字段：
- kind: "known_ip"（明确指向某 IP）/ "hybrid"（混合多个 IP 或借鉴）/ "original"（原创世界）
- confidence: 0~1
- ip_name: known_ip / hybrid 时必填
- ip_type: tv / movie / novel / anime / game / other
- one_liner: 一句话简介（30 字内）
- source_hints: 推荐查询关键词（如百度百科 / 维基条目名）

特别注意：
- 如果输入文本包含具体作品名（《XX》/「XX」/影视剧 XX），即使你不确定该作品是否真实存在（如训练截止后的新作），也应输出 kind=known_ip 且 confidence=0.7，由后续 Tavily 验证调整。
- 纯描述性、无作品名的输入（如"未来火星上的官僚社会"）输出 kind=original。

严格 JSON 输出，无解释文字。"""


async def _collect_text(llm_router: Any, system: str, user: str, max_tokens: int = 512) -> str:
    parts: list[str] = []
    async for ev in llm_router.stream_with_tools(
        messages=[{"role": "user", "content": user}],
        tools=[],
        system=system,
        max_tokens=max_tokens,
    ):
        if ev.get("type") == "text_delta":
            parts.append(ev.get("text", ""))
    return "".join(parts).strip()


def _extract_json(text: str) -> dict | None:
    candidates = [text]
    if "```json" in text:
        for part in text.split("```json")[1:]:
            candidates.append(part.split("```", 1)[0].strip())
    if "{" in text and "}" in text:
        candidates.append(text[text.find("{"): text.rfind("}") + 1])
    for c in candidates:
        try:
            parsed = json.loads(c)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            continue
    return None


async def _tavily_verify(ip_name: str, tavily: Any | None) -> bool:
    """快速验证：Tavily 搜 ip_name，看是否有结果且第一条标题包含 ip_name。"""
    if tavily is None or not ip_name:
        return False
    try:
        results = await tavily.search(query=ip_name, max_results=3)
        if not results:
            return False
        first_title = (results[0].get("title") or "").lower()
        return ip_name.lower() in first_title
    except Exception as exc:  # noqa: BLE001
        logger.warning("tavily_verify_failed", ip_name=ip_name, error=str(exc))
        return False


async def recognize_ip(description: str, llm_router: Any, tavily: Any | None = None) -> IPRecognition:
    """Stage 0：识别 description 指向的 IP。失败时返回 original/0.0。"""
    if not description.strip():
        return IPRecognition(kind="original", confidence=0.0)
    try:
        text = await _collect_text(llm_router, _RECOGNIZER_SYSTEM, description)
        data = _extract_json(text)
        if not data:
            logger.warning("ip_recognition_parse_failed", text_preview=text[:200])
            return IPRecognition(kind="original", confidence=0.0)
        rec = IPRecognition(
            kind=data.get("kind", "original"),
            confidence=float(data.get("confidence", 0.0)),
            ip_name=data.get("ip_name"),
            ip_type=data.get("ip_type"),
            one_liner=data.get("one_liner"),
            source_hints=data.get("source_hints") or [],
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("ip_recognition_failed", error=str(exc))
        return IPRecognition(kind="original", confidence=0.0)

    # Tavily 二次验证：known_ip 且 0.6~0.85 区间时才需要
    if rec.kind == "known_ip" and rec.ip_name and 0.6 <= rec.confidence <= 0.85:
        verified = await _tavily_verify(rec.ip_name, tavily)
        if verified:
            rec.confidence = min(0.95, rec.confidence + 0.15)
        else:
            rec.confidence = max(0.4, rec.confidence - 0.2)
            if rec.confidence < 0.5:
                rec.kind = "hybrid"  # 降级为模糊借鉴
    return rec
```

- [ ] **Step 2: Write tests with mock LLM**

```python
# backend/tests/test_ip_recognizer.py
import pytest
from unittest.mock import AsyncMock

from services.ip_recognizer import recognize_ip, IPRecognition


class FakeLLM:
    def __init__(self, text: str):
        self._text = text

    async def stream_with_tools(self, **_kwargs):
        for ch in self._text:
            yield {"type": "text_delta", "text": ch}


@pytest.mark.asyncio
async def test_recognize_known_ip():
    llm = FakeLLM('{"kind":"known_ip","confidence":0.9,"ip_name":"逐玉","ip_type":"tv","one_liner":"古装爱情剧","source_hints":["逐玉 百度百科"]}')
    rec = await recognize_ip("影视剧 逐玉", llm_router=llm)
    assert rec.kind == "known_ip"
    assert rec.ip_name == "逐玉"
    assert rec.ip_type == "tv"


@pytest.mark.asyncio
async def test_recognize_original_returns_original():
    llm = FakeLLM('{"kind":"original","confidence":0.95}')
    rec = await recognize_ip("未来火星上的官僚社会", llm_router=llm)
    assert rec.kind == "original"
    assert rec.ip_name is None


@pytest.mark.asyncio
async def test_recognize_empty_input():
    llm = FakeLLM("")
    rec = await recognize_ip("   ", llm_router=llm)
    assert rec.kind == "original"
    assert rec.confidence == 0.0


@pytest.mark.asyncio
async def test_recognize_llm_garbage_falls_back():
    llm = FakeLLM("not json at all")
    rec = await recognize_ip("X", llm_router=llm)
    assert rec.kind == "original"


@pytest.mark.asyncio
async def test_tavily_verify_promotes_confidence():
    llm = FakeLLM('{"kind":"known_ip","confidence":0.7,"ip_name":"逐玉","ip_type":"tv"}')
    tavily = AsyncMock()
    tavily.search.return_value = [{"title": "逐玉 - 维基百科", "url": "..."}]
    rec = await recognize_ip("逐玉", llm_router=llm, tavily=tavily)
    assert rec.confidence > 0.7  # promoted
```

Run: `cd backend && python -m pytest tests/test_ip_recognizer.py -v`
Expected: 5 PASS

- [ ] **Step 3: Commit**

```bash
git add backend/services/ip_recognizer.py backend/tests/test_ip_recognizer.py
git commit -m "feat(ip-fidelity): add Stage 0 IP recognizer"
```

---

## Task 4：generation_task 两阶段拆分 + Stage 0 集成

**Files:**
- Modify: `backend/services/world_creator_agent_v2.py`（pipeline 入口）
- Modify: `backend/services/generation_task_service.py`（两阶段任务支持）
- Modify: `backend/api/admin.py`（新增 continue 接口）
- Modify: `frontend/lib/admin-sse-events.ts`（新增 IPRecognitionEvent）

> 这一 task 较大，因为两阶段拆分跨多个文件、必须一次完成才能跑通。完成后即可端到端跑：admin 创建 draft → SSE 推 ip_recognition → 前端（暂未实装 UI）手动调 continue → pipeline 继续。

- [ ] **Step 1: Modify generation_task_service to support phased pause**

在 `services/generation_task_service.py` 找到任务执行的主入口（处理 `kind=world` 的方法，通常叫 `run_world_task` 或类似）。在这之前，**通读现有方法**了解事件循环 / DB 提交节奏，然后引入"phase_a only" 模式：

```python
# services/generation_task_service.py 新增辅助常量
PHASE_A_ONLY = "phase_a"  # 仅跑 Stage 0
PHASE_B_ONLY = "phase_b"  # 跳过 Stage 0，跑剩余 stages
```

`request_payload` 现已有 description/genre/era/admin_user_id；新增可选字段 `phase` (默认空 = 跑完整 pipeline 兼容旧逻辑，但我们会在 admin.py 创建任务时显式传 `PHASE_A_ONLY`) 和 `ip_recognition`（phase_b 时携带 Stage 0 结果，避免重跑）。

在 task 主循环中：
```python
phase = task.request_payload.get("phase")
if phase == PHASE_A_ONLY:
    # 跑 Stage 0，保存 ip_recognition 到 intermediate_state，然后 succeed
    rec = await ip_recognizer.recognize_ip(description, llm_router=llm, tavily=tavily)
    await self._record_intermediate(task.id, "ip_recognition", rec.model_dump())
    await self._emit_event(task.id, "progress", {
        "phase": "ip_recognition",
        "code": "completed",
        "meta": rec.model_dump(),
    })
    await self._mark_succeeded(task.id, current_phase="ip_recognition")
    return
elif phase == PHASE_B_ONLY:
    # 用 request_payload["ip_recognition"] + draft.payload["fidelity_mode"] 跑剩余 stages
    # 调用 world_creator_agent_v2 的入口，传入 fidelity_mode 和 ip_recognition
    ...
else:
    # 兼容旧路径：完整 pipeline（短期保留，未来可删）
    ...
```

具体的 `_emit_event` / `_mark_succeeded` / `_record_intermediate` 用现有 helper 名称（grep 已有代码确认实际命名）。

- [ ] **Step 2: Modify world_creator_agent_v2.py to accept skip_stage_0 + ip_recognition**

`services/world_creator_agent_v2.py` 现有 `run()` 入口（约 line 175）。修改签名加可选参数：

```python
async def run(
    self,
    description: str,
    genre: str,
    era: str,
    *,
    skip_ip_recognition: bool = False,   # 新增：phase_b 模式跳过 Stage 0
    pre_recognition: IPRecognition | None = None,  # 新增：phase_b 复用
    fidelity_mode: FidelityMode = "none",  # 新增：strict / loose / none
) -> AsyncIterator[dict]:
    if not skip_ip_recognition:
        # 旧的完整模式：自己跑 Stage 0（短期兼容）
        async for ev in self._run_ip_recognition(description):
            yield ev
        # 当 fidelity_mode 来自调用方时，这里不会用到 (continue 接口走 phase_b)
    # 后续 stages 根据 fidelity_mode 决定是否跑 IP Research
    ...
```

加 `_run_ip_recognition` 方法（包装 services.ip_recognizer）；这一阶段的 SSE 事件已在 task service 中发，agent 内不再重复。

- [ ] **Step 3: Add continue endpoint in admin.py**

```python
# backend/api/admin.py
from schemas.ip_knowledge_pack import FidelityMode  # 顶部 import

class ContinueGenerationRequest(BaseModel):
    fidelity_mode: FidelityMode  # "strict" | "loose" | "none"

@router.post("/world-drafts/{draft_id}/continue-generation")
async def continue_world_draft_generation(
    draft_id: str,
    body: ContinueGenerationRequest,
    admin_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """前端在中介卡片上选择 fidelity_mode 后调用：
    1. 写 fidelity_mode 到 draft.payload
    2. 拉取最近一个 phase_a task 的 ip_recognition 结果
    3. 创建一个新 phase_b task 启动剩余 pipeline
    """
    draft = await db.get(WorldDraft, draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="draft not found")
    payload = dict(draft.payload or {})
    payload["fidelity_mode"] = body.fidelity_mode
    draft.payload = payload
    await db.flush()

    # 拉最近一个该 draft 的 phase_a succeeded task
    last_task = await _load_latest_generation_task(db, draft_id, draft_type="world_draft")
    ip_rec = (last_task.intermediate_state or {}).get("ip_recognition") if last_task else None

    # 创建 phase_b task
    new_task = await _get_generation_task_service().create_task(
        db=db,
        kind="world",
        draft_type="world_draft",
        draft_id=draft_id,
        request_payload={
            "description": payload.get("description", ""),
            "genre": payload.get("genre", ""),
            "era": payload.get("era", ""),
            "admin_user_id": str(admin_user.id),
            "phase": "phase_b",
            "ip_recognition": ip_rec,
            "fidelity_mode": body.fidelity_mode,
        },
    )
    await db.commit()
    await record_admin_action(db, admin_user, action="continue_world_draft_generation",
                              target=f"draft:{draft_id}", meta={"fidelity_mode": body.fidelity_mode})
    return {"code": 0, "data": {"task_id": str(new_task.id)}, "message": "ok"}
```

同时找到现有 `POST /admin/world-drafts/generate`（创建首个 task 的接口），把它的 `request_payload` 加上 `"phase": "phase_a"`。

- [ ] **Step 4: Add SSE event type on frontend**

```ts
// frontend/lib/admin-sse-events.ts (在已有 union 中添加)
export type IPRecognitionEvent = {
  phase: "ip_recognition";
  code: "completed";
  meta: {
    kind: "known_ip" | "hybrid" | "original";
    confidence: number;
    ip_name?: string;
    ip_type?: "tv" | "movie" | "novel" | "anime" | "game" | "other";
    one_liner?: string;
    source_hints?: string[];
  };
};

// 把 IPRecognitionEvent 加入 GenerationProgressEvent union
```

- [ ] **Step 5: Smoke test end-to-end (manual)**

启动 backend / frontend (docker compose 已在跑)。在 admin 工作台创建一个新 draft 输入 `"影视剧 逐玉"`。开浏览器 devtools 看 SSE：应能看到 `phase: ip_recognition, code: completed, meta: { kind: known_ip, ip_name: "逐玉" }`。task 状态变 succeeded。

然后用 curl 验 continue 接口（手动模拟前端尚未实装的卡片）：
```bash
curl -X POST http://localhost:8000/admin/world-drafts/<draft_id>/continue-generation \
  -H 'Content-Type: application/json' \
  --cookie "session=<admin_session>" \
  -d '{"fidelity_mode":"strict"}'
```
应返回 `{"code":0,"data":{"task_id":"..."}}`。新 task 启动，前端 SSE 看到从 world_base 阶段开始（跳过 ip_recognition）。

- [ ] **Step 6: Commit**

```bash
git add backend/services/generation_task_service.py backend/services/world_creator_agent_v2.py backend/api/admin.py frontend/lib/admin-sse-events.ts
git commit -m "feat(ip-fidelity): two-phase generation task with Stage 0 pause point"
```

---

## Task 5：IP Pack Extractors（wikipedia + tavily site:）

**Files:**
- Create: `backend/services/ip_pack_extractors/__init__.py`
- Create: `backend/services/ip_pack_extractors/wikipedia.py`
- Create: `backend/services/ip_pack_extractors/tavily_site.py`
- Create: `backend/tests/test_ip_pack_extractors.py`

- [ ] **Step 1: Implement wikipedia extractor**

```python
# backend/services/ip_pack_extractors/__init__.py
"""IP 多源抓取器。每个 extractor 输出 list[Passage]。"""
```

```python
# backend/services/ip_pack_extractors/wikipedia.py
import uuid
from urllib.parse import quote

import httpx
import structlog

from schemas.research_pack import Passage

logger = structlog.get_logger()

WIKI_BASE = "https://zh.wikipedia.org/wiki/"
USER_AGENT = "TaleAlive-IPResearch/0.1 (admin tool; contact: dev)"


async def fetch_wikipedia(ip_name: str, *, max_chars: int = 2000, timeout: float = 8.0) -> list[Passage]:
    """抓 zh.wikipedia.org/wiki/<ip_name>，返回纯文本前 max_chars 字符切成 ≤2 段。

    失败返回空 list（不抛错）。
    """
    if not ip_name:
        return []
    url = WIKI_BASE + quote(ip_name)
    try:
        async with httpx.AsyncClient(timeout=timeout, headers={"User-Agent": USER_AGENT}) as client:
            resp = await client.get(url, follow_redirects=True)
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
            html = resp.text
    except Exception as exc:  # noqa: BLE001
        logger.warning("wikipedia_fetch_failed", ip_name=ip_name, error=str(exc))
        return []

    # 极简 HTML→文本：去 script/style，用 BeautifulSoup
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        logger.warning("beautifulsoup_not_installed")
        return []

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "table"]):  # table 含信息框，先粗略丢掉
        tag.decompose()
    content = soup.find(id="mw-content-text")
    text = (content.get_text(separator="\n", strip=True) if content else "")[:max_chars * 2]

    # 切两段返回
    passages: list[Passage] = []
    for offset in range(0, min(len(text), max_chars * 2), max_chars):
        chunk = text[offset: offset + max_chars]
        if chunk.strip():
            passages.append(Passage(
                id=f"p_wiki_{uuid.uuid4().hex[:8]}",
                text=chunk,
                tags=[f"source:{url}", f"query:{ip_name}"],
                source="wikipedia",
            ))
    return passages
```

- [ ] **Step 2: Implement tavily site: wrapper**

```python
# backend/services/ip_pack_extractors/tavily_site.py
import uuid
from typing import Any

import structlog

from schemas.research_pack import Passage

logger = structlog.get_logger()

# ip_type → 推荐站点列表
SITE_MAP: dict[str, list[str]] = {
    "tv": ["baike.baidu.com", "douban.com"],
    "movie": ["baike.baidu.com", "douban.com"],
    "novel": ["baike.baidu.com", "jjwxc.net", "qidian.com"],
    "anime": ["baike.baidu.com", "moegirl.icu"],
    "game": ["baike.baidu.com", "gamersky.com"],
    "other": ["baike.baidu.com"],
}


async def fetch_via_tavily_site(
    ip_name: str,
    ip_type: str,
    tavily: Any,
    *,
    max_per_site: int = 3,
    max_chars: int = 2000,
) -> list[Passage]:
    """对每个推荐站点跑 site:xxx <ip_name> 的 Tavily 搜索，合并结果为 Passage list。"""
    if not ip_name or tavily is None:
        return []
    sites = SITE_MAP.get(ip_type, SITE_MAP["other"])
    passages: list[Passage] = []
    for site in sites:
        query = f"site:{site} {ip_name}"
        try:
            results = await tavily.search(query=query, max_results=max_per_site)
        except Exception as exc:  # noqa: BLE001
            logger.warning("tavily_site_failed", site=site, ip_name=ip_name, error=str(exc))
            continue
        for r in results:
            text = (r.get("content") or r.get("snippet") or "").strip()
            if not text:
                continue
            passages.append(Passage(
                id=f"p_site_{uuid.uuid4().hex[:8]}",
                text=text[:max_chars],
                tags=[f"source:{r.get('url', '')}", f"site:{site}", f"query:{ip_name}"],
                source=f"tavily_site:{site}",
            ))
    return passages
```

- [ ] **Step 3: Tests with httpx mock + tavily mock**

```python
# backend/tests/test_ip_pack_extractors.py
import pytest
from unittest.mock import AsyncMock, patch

from services.ip_pack_extractors.wikipedia import fetch_wikipedia
from services.ip_pack_extractors.tavily_site import fetch_via_tavily_site


@pytest.mark.asyncio
async def test_wikipedia_404_returns_empty():
    with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=AsyncMock(status_code=404, raise_for_status=lambda: None))):
        result = await fetch_wikipedia("不存在的IP")
        assert result == []


@pytest.mark.asyncio
async def test_wikipedia_parses_html():
    fake_html = "<html><body><div id='mw-content-text'>这是测试文本，超过若干字符。</div></body></html>"
    fake_resp = AsyncMock()
    fake_resp.status_code = 200
    fake_resp.raise_for_status = lambda: None
    fake_resp.text = fake_html
    with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=fake_resp)):
        result = await fetch_wikipedia("测试IP", max_chars=50)
        assert len(result) >= 1
        assert "测试文本" in result[0].text
        assert result[0].source == "wikipedia"


@pytest.mark.asyncio
async def test_tavily_site_aggregates_multi_sites():
    tavily = AsyncMock()
    tavily.search.side_effect = [
        [{"content": "百度内容", "url": "baike.baidu.com/x"}],
        [{"content": "豆瓣内容", "url": "douban.com/y"}],
    ]
    result = await fetch_via_tavily_site("逐玉", "tv", tavily, max_per_site=1)
    assert len(result) == 2
    assert any("baidu" in p.source for p in result)
    assert any("douban" in p.source for p in result)


@pytest.mark.asyncio
async def test_tavily_site_handles_partial_failure():
    tavily = AsyncMock()
    tavily.search.side_effect = [Exception("network"), [{"content": "ok", "url": "x"}]]
    result = await fetch_via_tavily_site("X", "tv", tavily)
    # 一个失败、一个成功 → 至少 1 条
    assert len(result) >= 1
```

Run: `cd backend && python -m pytest tests/test_ip_pack_extractors.py -v`
Expected: 4 PASS

- [ ] **Step 4: Commit**

```bash
git add backend/services/ip_pack_extractors/ backend/tests/test_ip_pack_extractors.py
git commit -m "feat(ip-fidelity): add wikipedia + tavily-site extractors"
```

---

## Task 6：IP Research Pipeline（多源 + RAG 抽取 + 自检）

**Files:**
- Create: `backend/services/ip_research_pipeline.py`
- Create: `backend/tests/test_ip_research_pipeline.py`

- [ ] **Step 1: Implement pipeline**

```python
# backend/services/ip_research_pipeline.py
"""IP Research Pipeline：多源抓取 → RAG 抽取 IPKnowledgePack → 完整性自检 → 补抓。

前置：Stage 0 已识别出 IPRecognition (kind=known_ip 或 hybrid)。
fidelity_mode=none 时不应调用此 pipeline。
"""
import asyncio
import json
from typing import Any

import structlog

from schemas.ip_knowledge_pack import (
    IPKnowledgePack, IPCharacter, IPPlace, IPFaction, IPObject, IPEvent, FidelityMode,
)
from schemas.research_pack import Passage
from services.ip_pack_extractors.wikipedia import fetch_wikipedia
from services.ip_pack_extractors.tavily_site import fetch_via_tavily_site
from services.ip_recognizer import IPRecognition

logger = structlog.get_logger()

MAX_PASSAGES = 30
MAX_PASSAGE_CHARS = 2000


_EXTRACT_SYSTEM = """你是 IP 知识抽取助手。基于给定的 IP 名 + 多个 passage，输出严格 JSON 的 IPKnowledgePack。

要求：
1. **只从素材中抽取**，禁止凭记忆补充原作里没有出现的内容。
2. characters 至少包含原作的男女主和核心反派，标记 must_have=true；二级配角 must_have=false。
3. places 至少包含原作的核心场景（女主家乡 / 关键战场 / 主要城市等），标记 must_have=true 给那些"在原作中反复出现"的核心地点。
4. 每个条目必须填 source_passage_ids，引用素材里的 passage id。
5. tone_lingo 列出原作风格鲜明的称谓 / 口头禅 / 风格词（如"侯爷""相公""杀猪刀"）。
6. 严格 JSON，无解释文字。

输出 schema:
{
  "summary": "...200~500字...",
  "characters": [{"name":"","role_in_story":"","relation_to_protagonist":"","traits":[],"must_have":true,"source_passage_ids":[]}],
  "places": [{"name":"","description":"","must_have":true,"source_passage_ids":[]}],
  "factions": [{"name":"","description":"","source_passage_ids":[]}],
  "iconic_objects": [{"name":"","description":"","source_passage_ids":[]}],
  "key_events": [{"name":"","description":"","source_passage_ids":[]}],
  "tone_lingo": []
}"""


_MISSING_CHECK_SYSTEM = """你检查角色清单完整性。基于 summary 和已有 character names，列出原作中可能遗漏的、有名有姓的角色。

输出 JSON: {"missing_names": ["角色名1", "角色名2"]}
若清单看起来完整，返回 {"missing_names": []}。"""


async def _collect_text(llm_router: Any, system: str, user: str, max_tokens: int = 4096) -> str:
    parts: list[str] = []
    async for ev in llm_router.stream_with_tools(
        messages=[{"role": "user", "content": user}],
        tools=[],
        system=system,
        max_tokens=max_tokens,
    ):
        if ev.get("type") == "text_delta":
            parts.append(ev.get("text", ""))
    return "".join(parts).strip()


def _extract_json(text: str) -> dict | None:
    candidates = [text]
    if "```json" in text:
        for part in text.split("```json")[1:]:
            candidates.append(part.split("```", 1)[0].strip())
    if "{" in text and "}" in text:
        candidates.append(text[text.find("{"): text.rfind("}") + 1])
    for c in candidates:
        try:
            parsed = json.loads(c)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            continue
    return None


async def _gather_passages(rec: IPRecognition, tavily: Any) -> list[Passage]:
    """并发跑维基 + tavily site:。"""
    ip_name = rec.ip_name or ""
    ip_type = rec.ip_type or "other"
    wiki_coro = fetch_wikipedia(ip_name, max_chars=MAX_PASSAGE_CHARS)
    site_coro = fetch_via_tavily_site(ip_name, ip_type, tavily, max_chars=MAX_PASSAGE_CHARS)
    wiki, site = await asyncio.gather(wiki_coro, site_coro, return_exceptions=False)
    return (list(wiki) + list(site))[:MAX_PASSAGES]


def _passages_as_context(passages: list[Passage]) -> str:
    return "\n\n".join(f"[{p.id}] ({p.source}) {p.text}" for p in passages)


async def _extract_pack(
    rec: IPRecognition,
    passages: list[Passage],
    fidelity_mode: FidelityMode,
    llm_router: Any,
) -> IPKnowledgePack:
    user = (
        f"IP 名：{rec.ip_name}\n"
        f"IP 类型：{rec.ip_type}\n\n"
        f"素材：\n{_passages_as_context(passages)}"
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
        passages=passages,
    )


async def _self_check_missing(pack: IPKnowledgePack, llm_router: Any) -> list[str]:
    if not pack.summary:
        return []
    user = (
        f"summary：{pack.summary}\n"
        f"已有角色：{', '.join(c.name for c in pack.characters)}"
    )
    try:
        text = await _collect_text(llm_router, _MISSING_CHECK_SYSTEM, user, max_tokens=512)
        data = _extract_json(text) or {}
        return [n for n in (data.get("missing_names") or []) if isinstance(n, str)][:5]
    except Exception as exc:  # noqa: BLE001
        logger.warning("missing_check_failed", error=str(exc))
        return []


async def build_ip_knowledge_pack(
    rec: IPRecognition,
    fidelity_mode: FidelityMode,
    llm_router: Any,
    tavily: Any,
) -> IPKnowledgePack:
    """主入口。Stage 0 已识别出 known_ip / hybrid 时调用。"""
    if rec.kind not in ("known_ip", "hybrid") or not rec.ip_name:
        # 防御：调用方不应在此情况下调用
        return IPKnowledgePack(
            ip_name="", ip_type="other", fidelity_mode=fidelity_mode,
            summary="", characters=[], places=[], factions=[],
            iconic_objects=[], key_events=[], tone_lingo=[], passages=[],
        )

    passages = await _gather_passages(rec, tavily)
    if not passages:
        logger.warning("ip_research_no_passages", ip_name=rec.ip_name)
        return IPKnowledgePack(
            ip_name=rec.ip_name, ip_type=rec.ip_type or "other", fidelity_mode=fidelity_mode,
            summary="", characters=[], places=[], factions=[],
            iconic_objects=[], key_events=[], tone_lingo=[], passages=[],
        )

    pack = await _extract_pack(rec, passages, fidelity_mode, llm_router)

    # 完整性自检 + 1 轮补抓
    missing = await _self_check_missing(pack, llm_router)
    if len(missing) >= 2:
        extra_passages: list[Passage] = []
        for name in missing:
            extra = await fetch_via_tavily_site(name, rec.ip_type or "other", tavily, max_per_site=1)
            extra_passages.extend(extra)
        if extra_passages:
            all_passages = (passages + extra_passages)[:MAX_PASSAGES]
            pack = await _extract_pack(rec, all_passages, fidelity_mode, llm_router)

    return pack
```

- [ ] **Step 2: Tests with mock LLM + mock extractors**

```python
# backend/tests/test_ip_research_pipeline.py
import pytest
from unittest.mock import AsyncMock, patch

from schemas.research_pack import Passage
from services.ip_recognizer import IPRecognition
from services.ip_research_pipeline import build_ip_knowledge_pack


class FakeLLM:
    def __init__(self, *texts: str):
        self._texts = list(texts)
        self._idx = 0

    async def stream_with_tools(self, **_kwargs):
        text = self._texts[min(self._idx, len(self._texts) - 1)]
        self._idx += 1
        for ch in text:
            yield {"type": "text_delta", "text": ch}


@pytest.mark.asyncio
async def test_pipeline_returns_empty_when_no_ip_name():
    rec = IPRecognition(kind="original", confidence=0.0)
    pack = await build_ip_knowledge_pack(rec, "strict", llm_router=FakeLLM(""), tavily=AsyncMock())
    assert pack.characters == []
    assert pack.places == []


@pytest.mark.asyncio
async def test_pipeline_extracts_pack_from_passages():
    rec = IPRecognition(kind="known_ip", confidence=0.9, ip_name="逐玉", ip_type="tv")
    extract_json = '{"summary":"S","characters":[{"name":"樊长玉","role_in_story":"女主","relation_to_protagonist":"本人","traits":[],"must_have":true,"source_passage_ids":["p1"]}],"places":[{"name":"临安镇","description":"","must_have":true,"source_passage_ids":["p1"]}],"factions":[],"iconic_objects":[],"key_events":[],"tone_lingo":[]}'
    missing_json = '{"missing_names":[]}'
    llm = FakeLLM(extract_json, missing_json)
    tavily = AsyncMock()
    tavily.search.return_value = [{"content": "樊长玉 谢征 临安镇", "url": "x"}]

    with patch("services.ip_research_pipeline.fetch_wikipedia",
               new=AsyncMock(return_value=[Passage(id="p1", text="...", tags=[], source="wikipedia")])):
        pack = await build_ip_knowledge_pack(rec, "strict", llm_router=llm, tavily=tavily)

    assert pack.ip_name == "逐玉"
    assert pack.fidelity_mode == "strict"
    assert "樊长玉" in pack.must_have_character_names()
    assert "临安镇" in pack.must_have_place_names()


@pytest.mark.asyncio
async def test_pipeline_self_check_triggers_extra_fetch():
    rec = IPRecognition(kind="known_ip", confidence=0.9, ip_name="逐玉", ip_type="tv")
    first_extract = '{"summary":"long enough summary","characters":[{"name":"樊长玉","role_in_story":"女主","relation_to_protagonist":"本人","traits":[],"must_have":true,"source_passage_ids":[]}],"places":[],"factions":[],"iconic_objects":[],"key_events":[],"tone_lingo":[]}'
    missing_json = '{"missing_names":["李怀安","谢征"]}'
    second_extract = '{"summary":"S2","characters":[{"name":"樊长玉","role_in_story":"女主","relation_to_protagonist":"本人","traits":[],"must_have":true,"source_passage_ids":[]},{"name":"李怀安","role_in_story":"配角","relation_to_protagonist":"师兄","traits":[],"must_have":true,"source_passage_ids":[]}],"places":[],"factions":[],"iconic_objects":[],"key_events":[],"tone_lingo":[]}'
    llm = FakeLLM(first_extract, missing_json, second_extract)
    tavily = AsyncMock()
    tavily.search.return_value = [{"content": "李怀安", "url": "x"}]

    with patch("services.ip_research_pipeline.fetch_wikipedia",
               new=AsyncMock(return_value=[Passage(id="p1", text="...", tags=[], source="wikipedia")])):
        pack = await build_ip_knowledge_pack(rec, "strict", llm_router=llm, tavily=tavily)
    assert "李怀安" in [c.name for c in pack.characters]
```

Run: `cd backend && python -m pytest tests/test_ip_research_pipeline.py -v`
Expected: 3 PASS

- [ ] **Step 3: Commit**

```bash
git add backend/services/ip_research_pipeline.py backend/tests/test_ip_research_pipeline.py
git commit -m "feat(ip-fidelity): add multi-source RAG IP research pipeline"
```

---

## Task 7：IP Pack 落表 service + 接入 pipeline

**Files:**
- Create: `backend/services/ip_pack_storage.py`
- Modify: `backend/services/world_creator_agent_v2.py`（在 phase_b 入口调研究 pipeline + 落表）

- [ ] **Step 1: Implement storage service**

```python
# backend/services/ip_pack_storage.py
from sqlalchemy.ext.asyncio import AsyncSession

from models.ip_knowledge_pack import IPKnowledgePack as IPKnowledgePackRow
from schemas.ip_knowledge_pack import IPKnowledgePack


async def save_ip_knowledge_pack(
    db: AsyncSession,
    pack: IPKnowledgePack,
    *,
    draft_id: str,
    world_id: str | None = None,
) -> IPKnowledgePackRow:
    row = IPKnowledgePackRow(
        world_id=world_id,
        draft_id=draft_id,
        ip_name=pack.ip_name,
        fidelity_mode=pack.fidelity_mode,
        pack_json=pack.model_dump(),
    )
    db.add(row)
    await db.flush()
    return row
```

- [ ] **Step 2: Wire into world_creator_agent_v2.py**

在 `world_creator_agent_v2.py` 的 phase_b 入口（基于 Task 4 已加的分支），在 Stage 0 之后、world_base 之前插入 IP Research stage：

```python
# pseudo:
if fidelity_mode in ("strict", "loose") and pre_recognition and pre_recognition.kind in ("known_ip", "hybrid"):
    yield progress_event("ip_research", "started", stage_index=..., total_stages=...)
    pack = await build_ip_knowledge_pack(
        pre_recognition, fidelity_mode, llm_router=self.llm, tavily=self.tavily,
    )
    await save_ip_knowledge_pack(self.db, pack, draft_id=self.draft_id)
    self._last_ip_pack = pack
    yield progress_event("ip_research", "completed",
        characters=len(pack.characters),
        places=len(pack.places),
        must_have_chars=len(pack.must_have_character_names()),
    )
else:
    self._last_ip_pack = None
```

把新 stage `ip_research` 加进 `_STAGE_INDEX`（放在 `world_base` 之前），并更新 `TOTAL_STAGES`。

`self.db` 需要从外层传入；`generation_task_service` 创建 agent 时已有 db session 可借。

- [ ] **Step 3: Manual smoke**

跑一次 phase_b：用 Task 4 的 curl continue 接口启动 phase_b，观察 SSE 出现 `ip_research started → completed` 事件，meta 显示 characters > 0。然后查库：
```bash
docker exec talealive-db-1 psql -U postgres -d talealive -c "SELECT ip_name, fidelity_mode, jsonb_array_length(pack_json->'characters') AS char_n, jsonb_array_length(pack_json->'places') AS place_n FROM ip_knowledge_packs ORDER BY created_at DESC LIMIT 3;"
```
对逐玉这个 draft，预期 char_n ≥ 5、place_n ≥ 3。

- [ ] **Step 4: Commit**

```bash
git add backend/services/ip_pack_storage.py backend/services/world_creator_agent_v2.py
git commit -m "feat(ip-fidelity): persist IP knowledge pack and wire into pipeline"
```

---

## Task 8：下游 prompt 硬约束改造（world_base + character_roster + characters）

**Files:**
- Modify: `backend/services/world_creator_agent_v2.py`（_run_world_base + 调用方 _run_characters）
- Modify: `backend/services/character_roster_builder.py`

> 这一 task 也较大，但三处 prompt 改动是同性质工作（都是把"参考"换成"必须使用"），打包做掉减少切换成本。

- [ ] **Step 1: Update world_base prompt**

定位 `_run_world_base`（约 `services/world_creator_agent_v2.py:355`），修改 prompt 构造逻辑：

```python
# 替换原 line 362-373 区域
ip_pack = self._last_ip_pack  # IPKnowledgePack | None
fidelity = self._fidelity_mode  # "strict" | "loose" | "none"

base_msg = (
    f"世界描述：{description}\n"
    f"题材：{genre or '未指定'}\n"
    f"时代：{era or '未指定'}\n"
)

if ip_pack and fidelity in ("strict", "loose") and ip_pack.summary:
    # 完整 summary 而非 [:400]
    base_msg += f"\n原作摘要：{ip_pack.summary[:1500]}\n"
    if ip_pack.must_have_place_names():
        if fidelity == "strict":
            base_msg += (
                f"\n【强约束】locations 必须从以下原作地点中选用，可微调描述但**禁止新增同类地点**：\n"
                f"{', '.join(ip_pack.must_have_place_names())}\n"
                f"额外可选地点：{', '.join(p.name for p in ip_pack.places if not p.must_have)}\n"
            )
        else:  # loose
            base_msg += (
                f"\n【参考】原作核心地点：{', '.join(ip_pack.must_have_place_names())}\n"
                f"建议优先使用，如需扩展可添加。\n"
            )

# 注意：不再渲染"标志性人名：（无）"这种反向暗示。空就不写。

base_msg += "\n\n请输出世界核心框架（JSON 格式）。"
```

- [ ] **Step 2: Update character_roster prompt**

打开 `services/character_roster_builder.py`，找到 prompt 构造函数（`build_character_roster` 或类似），新增参数 `ip_pack: IPKnowledgePack | None = None` 和 `fidelity_mode: FidelityMode = "none"`：

```python
# 在 user message 拼装时
if ip_pack and fidelity_mode in ("strict", "loose"):
    must_have = ip_pack.must_have_character_names()
    if must_have:
        if fidelity_mode == "strict":
            user += (
                f"\n\n【强约束】角色清单**必须包含以下原作角色，name 字段使用原作名**：\n"
                f"{', '.join(must_have)}\n"
                f"每个角色按原作 traits / relation 设定。可额外添加 ≤ 5 个原创配角。\n"
            )
        else:
            user += (
                f"\n\n【参考】原作核心角色：{', '.join(must_have)}\n"
                f"优先使用原作角色，可扩展。\n"
            )
```

`world_creator_agent_v2.py:_run_character_roster` 调用处把 `ip_pack` / `fidelity_mode` 传进去。

- [ ] **Step 3: Update characters stage**

`_run_characters` 在生成每个 character 详细档案时，如果该 character.name 命中 `ip_pack.characters` 中的某个，把对应 IPCharacter 的 traits/relation/role_in_story 作为 grounding 加进 prompt：

```python
# pseudo, 在 characters builder 内部 per-character loop：
ip_match = next((c for c in ip_pack.characters if c.name == roster_entry.name), None) if ip_pack else None
if ip_match and fidelity_mode in ("strict", "loose"):
    user += (
        f"\n\n【原作设定，必须遵守】\n"
        f"角色：{ip_match.name}（{ip_match.role_in_story}）\n"
        f"关系：{ip_match.relation_to_protagonist}\n"
        f"性格特征：{', '.join(ip_match.traits)}\n"
    )
```

- [ ] **Step 4: Manual end-to-end test**

跑一次完整生成（"影视剧 逐玉" → 选 strict）。看：
1. SSE 序列：ip_recognition → ip_research → world_base → ... → 完成
2. 数据库：
```bash
docker exec talealive-db-1 psql -U postgres -d talealive -c "SELECT name FROM npcs WHERE world_id=(SELECT id FROM worlds ORDER BY created_at DESC LIMIT 1);"
docker exec talealive-db-1 psql -U postgres -d talealive -c "SELECT locations_data FROM worlds ORDER BY created_at DESC LIMIT 1;" | head -3
```
预期：npcs 含樊长玉、谢征、李怀安（至少出现 3 个 must_have 中的 ≥ 2 个）；locations 含临安镇（不应有"雪落镇""黑石关"等自造名）。

- [ ] **Step 5: Commit**

```bash
git add backend/services/world_creator_agent_v2.py backend/services/character_roster_builder.py
git commit -m "feat(ip-fidelity): hard-constraint prompts for world_base/character_roster/characters"
```

---

## Task 9：前端中介卡片组件

**Files:**
- Create: `frontend/components/admin/workshop/IPRecognitionCard.tsx`
- Modify: `frontend/components/admin/editor/DraftEditorShell.tsx`
- Modify: `frontend/lib/api.ts` 或 admin api 封装文件（添加 `continueWorldDraftGeneration`）

- [ ] **Step 1: Add API call**

在前端 admin API 封装文件中（grep `world-drafts/generate` 找到既有的 admin draft API 模块）追加：

```ts
export async function continueWorldDraftGeneration(
  draftId: string,
  fidelityMode: "strict" | "loose" | "none",
): Promise<{ task_id: string }> {
  const res = await apiFetch(`/admin/world-drafts/${draftId}/continue-generation`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ fidelity_mode: fidelityMode }),
  });
  if (res.code !== 0) throw new Error(res.message || "continue failed");
  return res.data;
}
```

- [ ] **Step 2: Implement card component**

```tsx
// frontend/components/admin/workshop/IPRecognitionCard.tsx
"use client";

import { useEffect, useState } from "react";

type Recognition = {
  kind: "known_ip" | "hybrid" | "original";
  confidence: number;
  ip_name?: string;
  ip_type?: string;
  one_liner?: string;
};

type Props = {
  recognition: Recognition;
  onChoose: (mode: "strict" | "loose" | "none") => void;
  autoConfirmMs?: number;  // 默认 8000
};

export function IPRecognitionCard({ recognition, onChoose, autoConfirmMs = 8000 }: Props) {
  const [secondsLeft, setSecondsLeft] = useState(Math.ceil(autoConfirmMs / 1000));
  const [paused, setPaused] = useState(false);

  // 高置信度命中默认 strict；中置信度默认 none
  const defaultMode: "strict" | "loose" | "none" =
    recognition.kind === "known_ip" && recognition.confidence >= 0.85
      ? "strict"
      : "none";

  useEffect(() => {
    if (paused) return;
    if (secondsLeft <= 0) {
      onChoose(defaultMode);
      return;
    }
    const timer = setTimeout(() => setSecondsLeft((s) => s - 1), 1000);
    return () => clearTimeout(timer);
  }, [secondsLeft, paused, defaultMode, onChoose]);

  // original / 低置信度：不渲染卡片，外层应直接默认 none 不展示
  if (recognition.kind === "original" || recognition.confidence < 0.5) {
    useEffect(() => { onChoose("none"); }, []);  // eslint-disable-line
    return null;
  }

  const isHigh = recognition.kind === "known_ip" && recognition.confidence >= 0.85;

  return (
    <div
      className="lv-bg-surface rounded-lg border lv-border p-4 my-3"
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
    >
      <div className="lv-t-h3 mb-1">
        识别到《{recognition.ip_name}》
        {recognition.ip_type && <span className="lv-t-meta opacity-60 ml-2">({recognition.ip_type})</span>}
      </div>
      {recognition.one_liner && <div className="lv-t-body opacity-80 mb-3">{recognition.one_liner}</div>}

      <div className="space-y-2">
        {isHigh ? (
          <>
            <button onClick={() => onChoose("strict")} className="block w-full text-left px-3 py-2 rounded border hover:lv-bg-elevated">
              ① 高复刻原作（推荐）— 复刻关键人物、地点、核心设定
            </button>
            <button onClick={() => onChoose("loose")} className="block w-full text-left px-3 py-2 rounded border hover:lv-bg-elevated">
              ② 借鉴主线，自由创作 — 主线参考原作，人物地点可扩展
            </button>
            <button onClick={() => onChoose("none")} className="block w-full text-left px-3 py-2 rounded border hover:lv-bg-elevated">
              ③ 这不是复刻，按我写的来
            </button>
          </>
        ) : (
          <>
            <button onClick={() => onChoose("loose")} className="block w-full text-left px-3 py-2 rounded border hover:lv-bg-elevated">
              ① 是，参考《{recognition.ip_name}》创作
            </button>
            <button onClick={() => onChoose("none")} className="block w-full text-left px-3 py-2 rounded border hover:lv-bg-elevated">
              ② 不是，按我写的来
            </button>
          </>
        )}
      </div>

      <div className="lv-t-meta opacity-50 mt-3 text-right">
        {paused ? "已暂停自动确认" : `${secondsLeft}s 后自动选择默认项`}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Wire into DraftEditorShell**

在 `frontend/components/admin/editor/DraftEditorShell.tsx` 的 SSE handler 中：
1. 收到 `phase: "ip_recognition", code: "completed"` 事件 → setState 暂存 recognition
2. task succeed 后（current_phase=ip_recognition），渲染 `<IPRecognitionCard>` 取代/嵌入到 GenerationLoadingScreen
3. 用户点选 → 调 `continueWorldDraftGeneration(draftId, mode)` → 隐藏卡片 → 重新启动 SSE 订阅新 task_id

伪代码（实际位置参考现有 SSE state 的 `setStages` 附近）：
```tsx
const [ipRecognition, setIpRecognition] = useState<Recognition | null>(null);

// SSE event handler 内：
if (event.phase === "ip_recognition" && event.code === "completed") {
  setIpRecognition(event.meta as Recognition);
}

// 渲染（在生成进度区域附近）：
{ipRecognition && taskState === "succeeded_phase_a" && (
  <IPRecognitionCard
    recognition={ipRecognition}
    onChoose={async (mode) => {
      setIpRecognition(null);
      const { task_id } = await continueWorldDraftGeneration(draftId, mode);
      // 触发 SSE 订阅新 task_id（复用现有 startSSE 机制）
      startSSE(task_id);
    }}
  />
)}
```

具体集成点用现有 DraftEditorShell 的 task 状态管理代码风格调整。

- [ ] **Step 4: End-to-end manual test**

清掉 docker frontend 缓存重启（`docker compose restart frontend`），打开 admin → 创建新 draft → 输入 `"影视剧 逐玉"` → 点开始生成。预期：
1. SSE 推 ip_recognition completed
2. 中介卡片出现，显示「识别到《逐玉》(tv) — 古装爱情剧」三选项
3. 点 "① 高复刻原作" → 卡片消失 → SSE 重连新 task → 看到 ip_research → world_base → ... 完整流程
4. 不操作 8 秒 → 自动按默认（strict）继续
5. 鼠标悬停在卡片上 → 倒计时显示"已暂停自动确认"

- [ ] **Step 5: Commit**

```bash
git add frontend/components/admin/workshop/IPRecognitionCard.tsx frontend/components/admin/editor/DraftEditorShell.tsx frontend/lib/api.ts
git commit -m "feat(ip-fidelity): add IP recognition card for admin workshop"
```

---

## Task 10：端到端验收 + 逐玉复刻样板

**Files:**
- Create: `docs/_archive/ip-fidelity-phase1-zhuyu-baseline.md`（对比记录）

> 不写新代码，验证 Phase 1 落地效果。

- [ ] **Step 1: Run baseline generation**

清空当前测试 draft（如有），用 admin 重新创建一个 draft 输入 `"影视剧 逐玉"`：
1. Stage 0 应识别为 known_ip, ip_name=逐玉
2. 选 strict
3. 等完整生成（含 IP Research）

完成后查库：
```bash
docker exec talealive-db-1 psql -U postgres -d talealive -c "
SELECT w.id, w.name, w.locations_data,
  (SELECT json_agg(name) FROM npcs WHERE world_id = w.id) AS npcs,
  (SELECT pack_json -> 'characters' FROM ip_knowledge_packs WHERE draft_id = wd.id ORDER BY created_at DESC LIMIT 1) AS pack_chars
FROM worlds w
JOIN world_drafts wd ON wd.world_id = w.id
WHERE w.name LIKE '%逐玉%'
ORDER BY w.created_at DESC LIMIT 1;
"
```

- [ ] **Step 2: Compare with old baseline**

跟 spec 附录 B 的旧版逐玉（`task_id=e1b16f6d-6f82-464b-8b29-bdff3349da11`）对比：

| 维度 | Phase 1 前 | Phase 1 后 | 通过 |
|---|---|---|---|
| 识别为 IP | ❌（probe_ip_canon 全空）| ✅ kind=known_ip | ☐ |
| 樊长玉/谢征 在 NPCs | 无 NPCs 记录 | ✅ 出现 | ☐ |
| 李怀安 在 NPCs | ❌ | ✅ 出现 | ☐ |
| 临安镇 在 locations | ❌（雪落镇）| ✅ 临安镇 | ☐ |
| ip_knowledge_packs 落表 | N/A | ✅ 有 pack | ☐ |

通过标准（Phase 1 验收）：
- 至少 3 项 must_have 角色出现在 npcs 中
- 临安镇出现在 locations
- 不出现明显自造同类地名（如"雪落镇"或编造的关键地点）
- 整体 SSE 流程完整、不报错

- [ ] **Step 3: Document baseline**

写一份简短对比报告 `docs/_archive/ip-fidelity-phase1-zhuyu-baseline.md`，含：
- Phase 1 前后两份 world 的 npcs / locations / pack_json 对比
- Phase 1 识别到的 must_have_characters / must_have_places 命中率
- 已知问题（哪些角色仍漏、哪些地名仍偏）→ 进 Phase 2 待办

- [ ] **Step 4: Commit**

```bash
git add docs/_archive/ip-fidelity-phase1-zhuyu-baseline.md
git commit -m "docs(ip-fidelity): phase 1 zhuyu baseline comparison"
```

---

## Self-Review Checklist

- ✅ Spec 第 3 节 Stage 0 → Task 3 (recognizer) + Task 4 (集成 + UX 暂停机制)
- ✅ Spec 第 4 节 IP Research → Task 5 (extractors) + Task 6 (pipeline) + Task 7 (落表)
- ✅ Spec 第 5 节下游 prompt 改造 → Task 8（限于 world_base / character_roster / characters，其余进 Phase 2）
- ✅ Spec 第 9 节前端中介卡片 → Task 9
- ✅ Spec 验收标准 #1 #6 → Task 10
- ⚠️ Spec 第 6 节 critic 硬卡口 → 明确入 Phase 2（不在 Phase 1 范围）
- ⚠️ Spec 第 7 节 graceful 退化 → Phase 1 内做了基础（kind=original 走 none 模式跳过 IP Research、各 extractor 失败返回空），完整覆盖入 Phase 2
- ⚠️ Spec 第 8 节金标准测试集 → 入 Phase 3
- ⚠️ Spec 第 5 节 lore_dimensions 接 passages → 入 Phase 2
- ✅ 类型一致性：FidelityMode / IPRecognition / IPKnowledgePack 在所有 task 间签名一致
- ✅ 无 TBD / TODO / placeholder
