# Image Pipeline Refactor — VisualBrief + 21:9 Hero + Server-cropped 3:2 Cover

> **状态：已完成（2026-05-12）。** PR1（后端 Task 1–12）2026-05-10 落地：visual_brief / image_cropper / image_prompt_builder / Pillow 依赖 / Seedream 21:9·3:2·2:3 ratio mapping / migration `58f13b75b16c_visual_brief_and_drop_poster_image` 全部到位。PR2（前端 Task 13–17）2026-05-12 落地：types.ts / draft-schemas.ts 去 `poster_image` + 改 `banner_image` → `hero_image`；卡片 aspect ratio 16:10 → 3:2（PosterCard / Landing / discover / history×4 / Workshop×2 / admin scripts drafts）；admin 预览 PreviewFrame ratio 类型改 `3/2 | 21/9 | 2/3`；CoverDeck 项简化为 hero+cover 两张；i18n `covers.poster/banner` → `hero/cover`。下方 task checkbox 全部 ✅。

> **For agentic workers (历史)：** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the current 3-prompt + N-portrait image pipeline with a leaner, more cinematic pipeline: 1 LLM-generated `WorldVisualBrief` (English JSON) drives 1 × 21:9 hero + N × 2:3 portraits per world, plus 1 × 3:2 script poster. The 3:2 card cover is server-cropped from the 21:9 hero (zero LLM call). Drop `poster_image` field. Frontend ratio realigns from 16:10 → 3:2 for cards and full-bleed → 21:9 source for heros.

**Architecture:**
- **Stage A (NEW)** `visual_brief` — single text-LLM call produces structured English JSON (`anchor_location`, `key_prop`, `palette`, `lighting_signature`, `camera_grammar`, plus per-character `framing/wardrobe/gesture` blocks). Persisted to `worlds.visual_brief` JSONB.
- **Stage B (CHANGED)** `images` — generates 1 × 21:9 world hero (Seedream 21:9) + N × 2:3 character portraits in parallel. After hero saves, server-side PIL crops a 3:2 region from center → `cover_image`.
- **Script flow** — same shape: `script_visual_brief` LLM call + 1 × 3:2 poster.
- **Image prompt builders** — single-paragraph dense Chinese prompts (with English for cinematographer names + lens specs only). All consume the structured VisualBrief, no longer read raw `base_setting`.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 async, Alembic, Pillow (NEW), structlog, Pydantic. Frontend: Next.js 16, React 19, Tailwind CSS v4.

**Decisions baked in:**
- D1=A: cards are 3:2 (was 16:10)
- D2=A: only generate 21:9 hero, server-crop 3:2 cover
- D3=A: introduce WorldVisualBrief + ScriptVisualBrief
- D4=A: drop `poster_image` field
- D5=A: character avatar generated at 2:3 (was 1:1)
- M1=A: keep field names (`cover_image` redefined as 3:2, `hero_image` redefined as 21:9), drop `poster_image`
- M2=A: don't migrate existing data (test data only)
- M3=A: split into PR 1 (backend) + PR 2 (frontend)

---

## Out of scope

- Existing world/script data regeneration (test data, ignore per M2)
- Image format changes (AVIF/WebP fallbacks per cover-art-spec §3.2 — separate work)
- Avatar circular-thumbnail derivation from portrait (frontend `object-position` + `object-fit` is enough; no separate stored asset)
- LLM router / provider switching for prompt-language variants (current pipeline uses Seedream only; multi-provider prompt selection deferred)

---

# PR 1 — Backend pipeline

## Task 1: Add Pillow dependency

**Files:**
- Modify: `backend/pyproject.toml`

**Why:** Server-side image cropping requires Pillow. Currently not in deps.

- [x] **Step 1.1: Inspect current dependencies**

Run: `grep -A 30 "dependencies" backend/pyproject.toml | head -40`

Expected: list of deps that includes fastapi, sqlalchemy etc but no pillow.

- [x] **Step 1.2: Add Pillow to deps**

Edit `backend/pyproject.toml`. Find the `dependencies = [...]` block. Add `"Pillow>=10.0.0"` keeping alphabetical order (or end-of-list if not sorted).

- [x] **Step 1.3: Install in dev env**

Run: `cd backend && pip install -e ".[dev]"`
Expected: pillow gets installed.

- [x] **Step 1.4: Verify import**

Run: `cd backend && python -c "from PIL import Image; print(Image.__version__)"`
Expected: prints version like `10.x.x` without error.

- [x] **Step 1.5: Commit**

```bash
git add backend/pyproject.toml
git commit -m "feat(deps): add Pillow for server-side image cropping"
```

---

## Task 1.5: Extend Seedream aspect ratio mapping

**Files:**
- Modify: `backend/llm/openai_compatible.py`
- Test: `backend/tests/test_openai_compatible_aspect.py` (NEW)

**Why:** Current `_size_for_aspect_ratio` only handles `1:1 / 16:9 / 3:4 / 4:3`. The new pipeline uses `21:9` (hero), `3:2` (script poster), `2:3` (character portrait). Without these, every new ratio falls through to default 1024×1024 → wrong dimensions on every image. **Critical blocker — must fix before pipeline runs.**

- [x] **Step 1.5.1: Write failing test**

Create `backend/tests/test_openai_compatible_aspect.py`:

```python
"""Aspect ratio → size mapping tests for Seedream-compatible providers."""
from llm.openai_compatible import _size_for_aspect_ratio


def test_legacy_ratios_unchanged():
    assert _size_for_aspect_ratio("1:1") == "1024x1024"
    assert _size_for_aspect_ratio("16:9") == "1536x1024"
    assert _size_for_aspect_ratio("3:4") == "1024x1536"
    assert _size_for_aspect_ratio("4:3") == "1536x1024"


def test_new_ratios_supported():
    # 21:9 super-wide hero — width-dominant
    out = _size_for_aspect_ratio("21:9")
    w, h = (int(x) for x in out.split("x"))
    assert w > h
    assert abs((w / h) - (21 / 9)) < 0.05

    # 3:2 cinematic horizontal card
    out = _size_for_aspect_ratio("3:2")
    w, h = (int(x) for x in out.split("x"))
    assert w > h
    assert abs((w / h) - 1.5) < 0.05

    # 2:3 vertical portrait
    out = _size_for_aspect_ratio("2:3")
    w, h = (int(x) for x in out.split("x"))
    assert h > w
    assert abs((w / h) - (2 / 3)) < 0.05


def test_unknown_falls_back_to_square():
    assert _size_for_aspect_ratio("nonsense") == "1024x1024"
```

- [x] **Step 1.5.2: Run test to verify failure**

Run: `cd backend && python -m pytest tests/test_openai_compatible_aspect.py -v`
Expected: 1 PASS (legacy), 1 FAIL (new ratios), 1 PASS (fallback) — the `test_new_ratios_supported` must fail before fix.

- [x] **Step 1.5.3: Update mapping**

Edit `backend/llm/openai_compatible.py` lines 23-30. Replace `_size_for_aspect_ratio` with:

```python
def _size_for_aspect_ratio(aspect_ratio: str) -> str:
    """Map an aspect-ratio string to a Seedream/DALL·E-style ``WxH`` size.

    The keys here are the only ratios our image pipeline emits. Unknown ratios
    fall back to 1024×1024.
    """
    normalized = (aspect_ratio or "1:1").strip()
    return {
        "1:1": "1024x1024",
        "16:9": "1536x1024",
        "3:4": "1024x1536",
        "4:3": "1536x1024",
        # New (2026-05): cinematic / portrait variants
        "21:9": "1792x768",     # ~21:9 super-wide hero
        "3:2": "1536x1024",     # cinematic horizontal card (alias for 16:9 with intent)
        "2:3": "1024x1536",     # vertical character portrait (alias for 3:4 with intent)
    }.get(normalized, "1024x1024")
```

(Note: 3:2 and 16:9 share `1536x1024` because Seedream's discrete output sizes don't have a true 3:2 — the image LLM honors the `aspect_ratio` extra_body parameter for finer control; the size param is just a hint. Keep both for semantic clarity at call sites.)

- [x] **Step 1.5.4: Run test to verify pass**

Run: `cd backend && python -m pytest tests/test_openai_compatible_aspect.py -v`
Expected: all 3 PASS.

- [x] **Step 1.5.5: Commit**

```bash
git add backend/llm/openai_compatible.py backend/tests/test_openai_compatible_aspect.py
git commit -m "feat(image): add 21:9, 3:2, 2:3 to aspect ratio mapping"
```

---

## Task 2: VisualBrief Pydantic schemas

**Files:**
- Create: `backend/services/visual_brief.py`
- Test: `backend/tests/test_visual_brief_schema.py`

**Why:** Structured output schema for the LLM call. Pydantic models give us validation + the JSON-schema we feed to the LLM as response_format.

- [x] **Step 2.1: Write the failing test**

Create `backend/tests/test_visual_brief_schema.py`:

```python
"""VisualBrief schema validation tests."""
import pytest
from pydantic import ValidationError

from services.visual_brief import (
    CharacterVisualBrief,
    ScriptVisualBrief,
    WorldVisualBrief,
)


def test_world_visual_brief_minimal_valid():
    brief = WorldVisualBrief(
        anchor_location="a stone bridge in river fog",
        key_prop="a brass oil lamp",
        weather="thick river fog at midnight",
        dominant_materials="wet stone and weathered wood",
        palette=["ink-grey", "oxblood red", "amber"],
        lighting_signature="warm lamp against cold fog, 3:1 chiaroscuro",
        camera_grammar="anamorphic 1.85x, 35mm grain, shallow DOF",
        series_signature_line="warm lamp piercing cold river fog",
        characters={},
    )
    assert brief.anchor_location.startswith("a stone")
    assert len(brief.palette) >= 3


def test_world_visual_brief_palette_min_length():
    with pytest.raises(ValidationError):
        WorldVisualBrief(
            anchor_location="x",
            key_prop="x",
            weather="x",
            dominant_materials="x",
            palette=["only-one"],  # too short
            lighting_signature="x",
            camera_grammar="x",
            series_signature_line="x",
            characters={},
        )


def test_world_visual_brief_with_characters():
    brief = WorldVisualBrief(
        anchor_location="x",
        key_prop="x",
        weather="x",
        dominant_materials="x",
        palette=["a", "b", "c"],
        lighting_signature="x",
        camera_grammar="x",
        series_signature_line="x",
        characters={
            "陈茉": CharacterVisualBrief(
                framing="three-quarter rear, eye line upper third",
                wardrobe="indigo qipao, no jewelry",
                gesture="hand on lattice window",
                emotional_register="guarded",
                setting="tea-shop interior at night",
            ),
        },
    )
    assert "陈茉" in brief.characters
    assert brief.characters["陈茉"].emotional_register == "guarded"


def test_script_visual_brief_minimal_valid():
    brief = ScriptVisualBrief(
        dramatic_anchor="an abandoned travel case half-open on wet flagstone",
        accent_color_break="a thread of dried blood-rust on the case lining",
        forbidden_spoiler_elements=["the perpetrator", "the body"],
    )
    assert brief.dramatic_anchor.startswith("an abandoned")
```

- [x] **Step 2.2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_visual_brief_schema.py -v`
Expected: FAIL with `ImportError: cannot import name ... from services.visual_brief`.

- [x] **Step 2.3: Implement the schemas**

Create `backend/services/visual_brief.py`:

```python
"""VisualBrief — structured English visual fingerprint for image generation.

Produced by a single text-LLM call per world (and per script). Consumed by the
image prompt builders. The whole point: one source of truth for visual identity
that all image prompts (hero, cover-by-crop, character portraits, script poster)
share, so the resulting images form a coherent series.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class CharacterVisualBrief(BaseModel):
    """Per-character visual brief — LLM produces one of these for each
    `is_image_target=True` character. All fields English; the image LLM consumes
    these directly via the portrait prompt template.
    """

    framing: str = Field(
        ...,
        description=(
            "How the character is composed in 2:3 vertical frame. Must mention "
            "view angle (three-quarter / profile / rear), framing scale (half-body / "
            "medium environmental), and where the eye line sits (upper third is "
            "required for avatar crop)."
        ),
    )
    wardrobe: str = Field(..., description="Period-accurate clothing in plain prose.")
    gesture: str = Field(..., description="What the character is doing — unposed, mid-action.")
    emotional_register: str = Field(
        ...,
        description=(
            "Emotional posture — derived from personality. SECRETS MUST NOT be "
            "passed verbatim; transform into emotional cues like 'guarded', "
            "'haunted', 'withholding'."
        ),
    )
    setting: str = Field(..., description="Environmental backdrop, suggested not detailed.")


class WorldVisualBrief(BaseModel):
    """World-level visual fingerprint. One per world, persisted to
    `worlds.visual_brief` JSONB column.

    All free-text fields are ENGLISH, regardless of the world's source language.
    The LLM is responsible for translating Chinese world data into English visual
    cues during this generation step.
    """

    anchor_location: str = Field(
        ...,
        description=(
            "The world's signature location, in concrete visual terms. Must read "
            "as a real place a cinematographer could shoot — buildings, materials, "
            "scale. ~30-60 words."
        ),
    )
    key_prop: str = Field(..., description="The single recurring object that anchors the visual identity.")
    weather: str = Field(..., description="Time of day + atmospheric condition.")
    dominant_materials: str = Field(..., description="Primary surface materials visible in the world.")
    palette: list[str] = Field(
        ...,
        min_length=3,
        max_length=5,
        description="3-5 color words. NO neon, NO oversaturated primaries.",
    )
    lighting_signature: str = Field(
        ...,
        description=(
            "The world's signature lighting recipe. Must specify key source, "
            "ambient, contrast ratio, and shadow handling. Reads as instructions "
            "to a DP."
        ),
    )
    camera_grammar: str = Field(
        ...,
        description="Lens character, film stock feel, depth-of-field philosophy.",
    )
    series_signature_line: str = Field(
        ...,
        description=(
            "ONE sentence answering 'if you see this image, you know it's from "
            "this world because ___'. This line gets prepended to every prompt."
        ),
    )

    characters: dict[str, CharacterVisualBrief] = Field(
        default_factory=dict,
        description="Per-character briefs keyed by character name.",
    )


class ScriptVisualBrief(BaseModel):
    """Script-level visual fingerprint for the dramatic poster. Inherits the
    parent world's palette/lighting; adds a story-specific dramatic anchor and
    spoiler safelist.
    """

    dramatic_anchor: str = Field(
        ...,
        description=(
            "The single charged moment / object the poster depicts. NOT the "
            "story's resolution — only the question. ~30-60 words."
        ),
    )
    accent_color_break: str = Field(
        ...,
        description=(
            "ONE element that breaks the parent world's palette to mark this "
            "story's distinct mood. E.g., 'a thread of dried blood-rust' against "
            "an otherwise grey palette."
        ),
    )
    forbidden_spoiler_elements: list[str] = Field(
        default_factory=list,
        description=(
            "Concrete things the poster MUST NOT show — perpetrator's identity, "
            "body, twist object, ending state. Fed into the prompt's avoid list."
        ),
    )
```

- [x] **Step 2.4: Run test to verify pass**

Run: `cd backend && python -m pytest tests/test_visual_brief_schema.py -v`
Expected: 4 PASS.

- [x] **Step 2.5: Commit**

```bash
git add backend/services/visual_brief.py backend/tests/test_visual_brief_schema.py
git commit -m "feat(visual-brief): add Pydantic schemas for world and script briefs"
```

---

## Task 3: VisualBrief LLM generators

**Files:**
- Modify: `backend/services/visual_brief.py` (append tool schemas + generator functions)
- Test: `backend/tests/test_visual_brief_generator.py`

**Why:** The single LLM call that turns Chinese world data into the English structured brief. **Reuses the existing `_collect_tool_output` pattern from `services/generation_strategy_service.py:32`** — same idiom as `build_visual_brief`, `build_world_brief`, etc. (See `generation_strategy_service.py` for reference: it calls `llm.stream_with_tools(...)` with a tool schema and collects the `tool_use` event.) No new LLM Protocol invented.

- [x] **Step 3.1: Write the failing test**

Create `backend/tests/test_visual_brief_generator.py`:

```python
"""VisualBrief LLM generator tests — mocks the LLMRouter's stream_with_tools."""
import json
from typing import AsyncIterator

import pytest

from services.visual_brief import (
    WorldVisualBrief,
    generate_world_visual_brief,
    generate_script_visual_brief,
)


class _FakeLLM:
    """Minimal LLMRouter stand-in: drives a tool_use event into stream_with_tools."""

    def __init__(self, tool_output: dict):
        self.tool_output = tool_output
        self.captured_messages: list[dict] = []
        self.captured_system: str = ""
        self.captured_tools: list[dict] = []

    async def stream_with_tools(
        self, *, messages, tools, system, max_tokens=2048, **kwargs
    ) -> AsyncIterator[dict]:
        self.captured_messages = messages
        self.captured_system = system or ""
        self.captured_tools = tools

        async def gen():
            yield {"type": "tool_use", "input": self.tool_output}

        return gen()


@pytest.mark.asyncio
async def test_generate_world_visual_brief_happy_path():
    fake_payload = {
        "anchor_location": "a stone bridge half-veiled in river fog",
        "key_prop": "a brass oil lamp on wet flagstone",
        "weather": "thick river fog, late autumn, midnight",
        "dominant_materials": "wet stone, weathered wood, oxblood lacquer",
        "palette": ["ink-grey", "oxblood red", "old-paper amber", "cold mist white"],
        "lighting_signature": "single warm lamp against cold fog, 3:1 chiaroscuro",
        "camera_grammar": "anamorphic 1.85x, 35mm grain, shallow DOF",
        "series_signature_line": "warm lamp piercing cold river fog",
        "characters": {
            "陈茉": {
                "framing": "three-quarter rear, eye line upper third",
                "wardrobe": "indigo qipao, no jewelry",
                "gesture": "hand on lattice window",
                "emotional_register": "guarded",
                "setting": "tea-shop interior at night",
            },
        },
    }
    fake_llm = _FakeLLM(fake_payload)

    world_data = {
        "name": "雾隐镇",
        "genre": "悬疑",
        "era": "民国",
        "base_setting": "湘西边陲一座临河小镇...",
        "description": "三个外来人调查失踪案",
    }
    characters = [
        {"name": "陈茉", "personality": "淡漠克制", "secret": "她父亲是凶手"},
    ]

    brief = await generate_world_visual_brief(
        world_data=world_data, characters=characters, llm=fake_llm,
    )

    assert isinstance(brief, WorldVisualBrief)
    assert brief.anchor_location.startswith("a stone bridge")
    assert "陈茉" in brief.characters
    # Crucially: secret content must NOT appear anywhere downstream
    assert "凶手" not in brief.model_dump_json()


@pytest.mark.asyncio
async def test_generate_world_visual_brief_strips_secret_from_llm_input():
    """Verify the LLM is NOT given raw secret text in its input messages."""
    fake_payload = {
        "anchor_location": "x" * 30,
        "key_prop": "x",
        "weather": "x",
        "dominant_materials": "x",
        "palette": ["a", "b", "c"],
        "lighting_signature": "x",
        "camera_grammar": "x",
        "series_signature_line": "x",
        "characters": {},
    }
    fake_llm = _FakeLLM(fake_payload)

    await generate_world_visual_brief(
        world_data={"name": "x", "genre": "x", "era": "x", "base_setting": "x", "description": "x"},
        characters=[
            {"name": "陈茉", "personality": "克制", "secret": "她父亲是凶手"},
        ],
        llm=fake_llm,
    )

    full_input = json.dumps(fake_llm.captured_messages, ensure_ascii=False)
    assert "凶手" not in full_input, "secret content leaked into LLM prompt"


@pytest.mark.asyncio
async def test_generate_script_visual_brief_happy_path():
    fake_payload = {
        "dramatic_anchor": "an abandoned travel case half-open on wet flagstone",
        "accent_color_break": "a thread of dried blood-rust on the case lining",
        "forbidden_spoiler_elements": ["the perpetrator", "the body"],
    }
    fake_llm = _FakeLLM(fake_payload)

    brief = await generate_script_visual_brief(
        script_data={"name": "雾日失踪", "description": "商人雾夜消失", "script_type": "mystery"},
        world_brief={
            "anchor_location": "stone bridge in fog",
            "palette": ["grey", "red", "amber"],
        },
        llm=fake_llm,
    )

    assert brief.dramatic_anchor.startswith("an abandoned")
    assert "the perpetrator" in brief.forbidden_spoiler_elements
```

- [x] **Step 3.2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_visual_brief_generator.py -v`
Expected: FAIL with `ImportError: cannot import name 'generate_world_visual_brief'`.

- [x] **Step 3.3: Implement the generators**

Append to `backend/services/visual_brief.py`:

```python
# ---------------------------------------------------------------------------
# LLM tool schemas + generators (append to file)
# ---------------------------------------------------------------------------

import json as _json
from typing import Any

import structlog

logger = structlog.get_logger()


# Tool schema for the world brief LLM call. Mirrors the structure of
# WorldVisualBrief; the LLM emits a tool_use event whose `input` parses as the
# WorldVisualBrief dict.
WORLD_VISUAL_BRIEF_TOOL = {
    "name": "build_world_visual_brief",
    "description": (
        "为互动叙事世界产出统一的视觉指纹（English JSON）。"
        "下游图像 prompt 将完全从此 brief 派生，要求所有图属于同一摄影师拍下的同一组镜头。"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "anchor_location": {"type": "string"},
            "key_prop": {"type": "string"},
            "weather": {"type": "string"},
            "dominant_materials": {"type": "string"},
            "palette": {
                "type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 5,
            },
            "lighting_signature": {"type": "string"},
            "camera_grammar": {"type": "string"},
            "series_signature_line": {"type": "string"},
            "characters": {
                "type": "object",
                "additionalProperties": {
                    "type": "object",
                    "properties": {
                        "framing": {"type": "string"},
                        "wardrobe": {"type": "string"},
                        "gesture": {"type": "string"},
                        "emotional_register": {"type": "string"},
                        "setting": {"type": "string"},
                    },
                    "required": ["framing", "wardrobe", "gesture", "emotional_register", "setting"],
                },
            },
        },
        "required": [
            "anchor_location", "key_prop", "weather", "dominant_materials",
            "palette", "lighting_signature", "camera_grammar",
            "series_signature_line", "characters",
        ],
    },
}


SCRIPT_VISUAL_BRIEF_TOOL = {
    "name": "build_script_visual_brief",
    "description": (
        "为剧本（同一世界下的一条剧情线）产出戏剧性海报的视觉策略。"
        "继承世界 brief 的 palette/lighting，只引入 ONE accent color break。"
        "明确列出禁止出现的剧透元素。"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "dramatic_anchor": {"type": "string"},
            "accent_color_break": {"type": "string"},
            "forbidden_spoiler_elements": {
                "type": "array", "items": {"type": "string"},
            },
        },
        "required": ["dramatic_anchor", "accent_color_break", "forbidden_spoiler_elements"],
    },
}


_WORLD_BRIEF_SYSTEM = (
    "你是为互动叙事世界制定视觉策略的电影摄影师 / production designer。"
    "你的产出是结构化 JSON（通过 build_world_visual_brief tool），全部字段使用英文，"
    "无论输入语言为何，都需把中文文化 / 时代 / 场景词转译成西方摄影师能直接拍摄的具体英文视觉词汇——"
    "材质、光向、天候、尺度。"
    "\n\n"
    "视觉风格固定为：photographic realism, 35mm film aesthetic, anamorphic lens character, "
    "dramatic chiaroscuro, restraint — vocabulary of Roger Deakins and Gregory Crewdson。"
    "绝不出现 anime / manga / cartoon / 水墨 / 工笔 / flat illustration / neon / HDR。"
    "\n\n"
    "对于每个角色：把 secret/隐藏特质转化为情绪姿态（guarded、haunted、withholding、evasive），"
    "绝不在 brief 里复述 secret 内容。"
    "竖版 2:3 portrait 中眼线必须落在画面上三分位横线上——上区将自动裁为圆形头像。"
)


_SCRIPT_BRIEF_SYSTEM = (
    "你是为既有世界中的某条剧本（剧情线）制定海报视觉的电影摄影师。"
    "世界 brief 已给定，你的任务：识别一个 charged dramatic moment 作为海报锚点。"
    "通过 build_script_visual_brief tool 输出英文 JSON。"
    "\n\n"
    "约束："
    "\n- 必须 INHERIT 世界 brief 的 palette 与 lighting，不要发明新风格"
    "\n- 加入 ONE accent color break，标记本剧本独特氛围（一处细节，不是重设计）"
    "\n- 列出 forbidden_spoiler_elements：海报禁止画的具体元素（凶手身份、尸体、关键 twist 道具、结局状态）"
    "\n- dramatic_anchor 只描绘故事的 QUESTION，绝不描绘 ANSWER"
)


def _build_world_brief_user_message(
    world_data: dict[str, Any], characters: list[dict[str, Any]]
) -> str:
    """Crucially: `secret` is stripped at the boundary. LLM never sees it."""
    char_inputs = [
        {
            "name": c.get("name", ""),
            "role_tag": c.get("role_tag", ""),
            "personality": c.get("personality", ""),
            "playable": c.get("playable", False),
        }
        for c in characters
    ]
    payload = {
        "world": {
            "name": world_data.get("name", ""),
            "genre": world_data.get("genre", ""),
            "era": world_data.get("era", ""),
            "base_setting": world_data.get("base_setting", ""),
            "description": world_data.get("description", ""),
        },
        "characters_to_visualize": char_inputs,
        "instruction": (
            "Produce WorldVisualBrief via the build_world_visual_brief tool. "
            "For each listed character emit a `characters[name]` entry. "
            "All free-text fields English."
        ),
    }
    return _json.dumps(payload, ensure_ascii=False, indent=2)


async def _collect_tool_output(llm, *, messages, tools, system, max_tokens=2048):
    """Drain ``stream_with_tools`` and return the first ``tool_use`` payload.

    Mirrors the local helper in ``services/generation_strategy_service.py`` —
    duplicated here so this module doesn't depend on the strategy module.
    """
    text_parts: list[str] = []
    tool_output: dict | None = None
    async for event in llm.stream_with_tools(
        messages=messages, tools=tools, system=system, max_tokens=max_tokens,
    ):
        etype = event.get("type")
        if etype == "tool_use":
            tool_output = event.get("input") or {}
        elif etype == "text_delta":
            text_parts.append(event.get("text", ""))
    if tool_output:
        return tool_output
    # Last-ditch: try to parse JSON from accumulated text
    text = "".join(text_parts).strip()
    if "{" in text and "}" in text:
        try:
            return _json.loads(text[text.find("{"):text.rfind("}") + 1])
        except _json.JSONDecodeError:
            pass
    return None


async def generate_world_visual_brief(
    *,
    world_data: dict[str, Any],
    characters: list[dict[str, Any]],
    llm,
) -> WorldVisualBrief:
    """Single LLM call: world data + characters → English structured brief.

    `llm` must be an LLMRouter (or anything implementing
    ``async stream_with_tools(messages, tools, system, max_tokens) -> AsyncIterator[dict]``
    that yields ``{"type": "tool_use", "input": {...}}`` for tool invocations).
    """
    user_msg = _build_world_brief_user_message(world_data, characters)
    raw = await _collect_tool_output(
        llm,
        messages=[{"role": "user", "content": user_msg}],
        tools=[WORLD_VISUAL_BRIEF_TOOL],
        system=_WORLD_BRIEF_SYSTEM,
        max_tokens=2048,
    )
    if raw is None:
        raise RuntimeError("LLM returned no structured world visual brief")
    try:
        return WorldVisualBrief.model_validate(raw)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "world_visual_brief_parse_failed",
            error=str(exc),
            raw_keys=list(raw.keys()),
        )
        raise


async def generate_script_visual_brief(
    *,
    script_data: dict[str, Any],
    world_brief: dict[str, Any] | WorldVisualBrief,
    llm,
) -> ScriptVisualBrief:
    """Single LLM call: script data + parent world brief → script brief."""
    if isinstance(world_brief, WorldVisualBrief):
        world_brief_dict = world_brief.model_dump()
    else:
        world_brief_dict = world_brief

    payload = {
        "world_brief": world_brief_dict,
        "script": {
            "name": script_data.get("name", ""),
            "description": script_data.get("description", ""),
            "script_type": script_data.get("script_type", "mystery"),
        },
        "instruction": "Produce ScriptVisualBrief via the build_script_visual_brief tool.",
    }
    user_msg = _json.dumps(payload, ensure_ascii=False, indent=2)

    raw = await _collect_tool_output(
        llm,
        messages=[{"role": "user", "content": user_msg}],
        tools=[SCRIPT_VISUAL_BRIEF_TOOL],
        system=_SCRIPT_BRIEF_SYSTEM,
        max_tokens=1536,
    )
    if raw is None:
        raise RuntimeError("LLM returned no structured script visual brief")
    try:
        return ScriptVisualBrief.model_validate(raw)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "script_visual_brief_parse_failed",
            error=str(exc),
            raw_keys=list(raw.keys()),
        )
        raise
```

- [x] **Step 3.4: Run test to verify pass**

Run: `cd backend && python -m pytest tests/test_visual_brief_generator.py -v`
Expected: 3 PASS.

- [x] **Step 3.5: Verify the existing schema test still passes**

Run: `cd backend && python -m pytest tests/test_visual_brief_schema.py tests/test_visual_brief_generator.py -v`
Expected: 7 PASS total.

- [x] **Step 3.6: Commit**

```bash
git add backend/services/visual_brief.py backend/tests/test_visual_brief_generator.py
git commit -m "feat(visual-brief): add LLM generator for world + script briefs"
```

---

## Task 4: Image cropper utility

**Files:**
- Create: `backend/services/image_cropper.py`
- Test: `backend/tests/test_image_cropper.py`

**Why:** Server-side center-crop of 21:9 hero → 3:2 cover. Pure utility, no I/O. Returns bytes for image_storage to save.

- [x] **Step 4.1: Write the failing test**

Create `backend/tests/test_image_cropper.py`:

```python
"""Image cropper utility tests."""
import io
from PIL import Image
import pytest

from services.image_cropper import crop_to_aspect_ratio, materialize_image_bytes
from llm.base import ImageResult


def _make_test_image_bytes(width: int, height: int, color: tuple = (50, 50, 50), fmt: str = "JPEG") -> bytes:
    img = Image.new("RGB", (width, height), color)
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


def test_crop_21_9_to_3_2_horizontal():
    """21:9 source (2880x1234) cropped to 3:2 should remove width, keep height."""
    src = _make_test_image_bytes(2880, 1234)
    out = crop_to_aspect_ratio(src, target_w=3, target_h=2)
    out_img = Image.open(io.BytesIO(out))
    assert out_img.height == 1234
    # 1234 * 3/2 = 1851
    assert out_img.width == 1851
    # ratio close to 3:2
    assert abs((out_img.width / out_img.height) - 1.5) < 0.01


def test_crop_already_target_ratio_passthrough():
    """If source is already exactly the target ratio, output dimensions match input."""
    src = _make_test_image_bytes(1500, 1000)  # 3:2
    out = crop_to_aspect_ratio(src, target_w=3, target_h=2)
    out_img = Image.open(io.BytesIO(out))
    assert out_img.width == 1500
    assert out_img.height == 1000


def test_crop_preserves_format_jpeg():
    src = _make_test_image_bytes(2000, 1000, fmt="JPEG")
    out = crop_to_aspect_ratio(src, target_w=3, target_h=2)
    out_img = Image.open(io.BytesIO(out))
    assert out_img.format == "JPEG"


def test_crop_preserves_format_png():
    src = _make_test_image_bytes(2000, 1000, fmt="PNG")
    out = crop_to_aspect_ratio(src, target_w=3, target_h=2)
    out_img = Image.open(io.BytesIO(out))
    assert out_img.format == "PNG"


def test_crop_taller_than_target_crops_vertically():
    """3:4 source cropped to 3:2 should remove height."""
    src = _make_test_image_bytes(900, 1200)  # 3:4 ratio
    out = crop_to_aspect_ratio(src, target_w=3, target_h=2)
    out_img = Image.open(io.BytesIO(out))
    assert out_img.width == 900
    # 900 * 2/3 = 600
    assert out_img.height == 600


@pytest.mark.asyncio
async def test_materialize_image_bytes_from_base64():
    """ImageResult with base64_data → returns the raw bytes."""
    raw = _make_test_image_bytes(100, 100)
    result = ImageResult(base64_data=raw, format="jpeg")
    out = await materialize_image_bytes(result)
    assert out == raw
```

- [x] **Step 4.2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_image_cropper.py -v`
Expected: FAIL with `ImportError: cannot import name 'crop_to_aspect_ratio'`.

- [x] **Step 4.3: Implement the cropper**

Create `backend/services/image_cropper.py`:

```python
"""Image cropping utilities — center crop bytes to a target aspect ratio.

Used by the world creator pipeline to derive a 3:2 browse-card cover from the
21:9 cinematic hero (single LLM call → two output images, guaranteed visual
consistency).
"""
from __future__ import annotations

import io

import httpx
from PIL import Image

from llm.base import ImageResult


def crop_to_aspect_ratio(image_bytes: bytes, *, target_w: int, target_h: int) -> bytes:
    """Center-crop input bytes to target_w:target_h aspect ratio.

    Preserves the source format (JPEG / PNG / WEBP). Returns new bytes.
    """
    src = Image.open(io.BytesIO(image_bytes))
    src_format = src.format or "JPEG"
    w, h = src.size
    target_ratio = target_w / target_h
    src_ratio = w / h

    if abs(src_ratio - target_ratio) < 1e-3:
        # already the right ratio — re-encode to drop any input-side metadata
        new_w, new_h, left, top = w, h, 0, 0
    elif src_ratio > target_ratio:
        # source is wider than target → crop horizontally
        new_w = int(round(h * target_ratio))
        new_h = h
        left = (w - new_w) // 2
        top = 0
    else:
        # source is taller than target → crop vertically
        new_w = w
        new_h = int(round(w / target_ratio))
        left = 0
        top = (h - new_h) // 2

    cropped = src.crop((left, top, left + new_w, top + new_h))
    out = io.BytesIO()
    save_kwargs: dict = {}
    if src_format == "JPEG":
        save_kwargs["quality"] = 92
        save_kwargs["optimize"] = True
        # JPEG can't encode RGBA — drop alpha if present
        if cropped.mode in ("RGBA", "P"):
            cropped = cropped.convert("RGB")
    cropped.save(out, format=src_format, **save_kwargs)
    return out.getvalue()


async def materialize_image_bytes(result: ImageResult) -> bytes:
    """Get raw bytes from an ImageResult regardless of url/base64 form.

    For url-form results, fetches the image. For base64-form, returns directly.
    """
    if result.has_data:
        return result.base64_data
    if result.has_url:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(result.url)
            resp.raise_for_status()
            return resp.content
    raise ValueError("ImageResult has neither url nor base64_data")
```

- [x] **Step 4.4: Run test to verify pass**

Run: `cd backend && python -m pytest tests/test_image_cropper.py -v`
Expected: 6 PASS.

- [x] **Step 4.5: Commit**

```bash
git add backend/services/image_cropper.py backend/tests/test_image_cropper.py
git commit -m "feat(image-cropper): add center-crop utility + bytes materializer"
```

---

## Task 5: Rewrite image_prompt_builder

**Files:**
- Modify (full rewrite): `backend/services/image_prompt_builder.py`
- Modify: `backend/tests/test_image_prompt_builder.py` (rewrite)

**Why:** New builders consume `WorldVisualBrief` / `ScriptVisualBrief`, output single-paragraph dense Chinese prompts (no empty lines), keep English only for cinematographer names + lens specs. Three builders only: `build_world_still_prompt`, `build_script_poster_prompt`, `build_character_portrait_prompt`. The old `build_cover_prompt` / `build_poster_prompt` / `build_hero_prompt` go away — there is no separate cover prompt (server-cropped from still).

- [x] **Step 5.1: Inspect existing test file (so we know what to rip out)**

Run: `head -100 backend/tests/test_image_prompt_builder.py`

Mental note: existing tests assert phrases like "rule-of-thirds" and "16:9". They will all need replacement. We rewrite this file from scratch.

- [x] **Step 5.2: Write the new failing tests**

Replace `backend/tests/test_image_prompt_builder.py` entirely with:

```python
"""Image prompt builder tests — Chinese single-paragraph prompts driven by VisualBrief."""
import pytest

from services.visual_brief import (
    CharacterVisualBrief,
    ScriptVisualBrief,
    WorldVisualBrief,
)
from services.image_prompt_builder import (
    build_world_still_prompt,
    build_script_poster_prompt,
    build_character_portrait_prompt,
)


@pytest.fixture
def world_brief() -> WorldVisualBrief:
    return WorldVisualBrief(
        anchor_location="a stone bridge half-veiled in river fog at the edge of a riverside town",
        key_prop="a brass oil lamp on wet flagstone, flame leaning",
        weather="thick river fog, late autumn midnight",
        dominant_materials="wet stone, weathered wood, oxblood lacquer",
        palette=["ink-grey", "oxblood red", "old-paper amber", "cold mist white"],
        lighting_signature="single warm low-kelvin lamp source against cold fog ambient, 3:1 chiaroscuro, no fill",
        camera_grammar="anamorphic 1.85x, 35mm film grain, shallow DOF on lamp",
        series_signature_line="warm lamp piercing cold river fog, oxblood lacquer against wet grey stone",
        characters={
            "陈茉": CharacterVisualBrief(
                framing="half-body environmental medium shot, three-quarter rear view, eye line on upper third of 2:3 frame",
                wardrobe="long ankle-length indigo cotton qipao, high collar, faded cuffs, single jade ear stud",
                gesture="hand resting on carved wooden lattice of a tea-shop window, half-turned away",
                emotional_register="guarded, contained, holding something she cannot say",
                setting="interior of an old riverside tea shop at night, paper lantern blurred behind",
            ),
        },
    )


@pytest.fixture
def script_brief() -> ScriptVisualBrief:
    return ScriptVisualBrief(
        dramatic_anchor="an abandoned leather travel case half-open on wet flagstone, one corner sinking into a fog-condensed puddle, a single water-filled shoe print beside it",
        accent_color_break="a thread of dried blood-rust on the case lining, faint enough to register as wrongness rather than gore",
        forbidden_spoiler_elements=["the perpetrator's face", "the victim's body", "the murder weapon"],
    )


# ---- world still ----

def test_world_still_prompt_contains_aspect_ratio(world_brief):
    p = build_world_still_prompt(world_brief)
    assert "21:9" in p


def test_world_still_prompt_uses_brief_anchor(world_brief):
    p = build_world_still_prompt(world_brief)
    assert "stone bridge" in p
    assert "river fog" in p


def test_world_still_prompt_includes_palette(world_brief):
    p = build_world_still_prompt(world_brief)
    for color in world_brief.palette:
        assert color in p


def test_world_still_prompt_includes_series_signature(world_brief):
    p = build_world_still_prompt(world_brief)
    assert world_brief.series_signature_line in p


def test_world_still_prompt_negative_includes_no_text(world_brief):
    p = build_world_still_prompt(world_brief)
    # Must explicitly forbid in-image text rendering
    assert "无文字" in p or "no text" in p
    # Must forbid Chinese ink-wash / gongbi style
    assert "水墨" in p
    assert "工笔" in p


def test_world_still_prompt_no_empty_lines(world_brief):
    """User wanted no blank lines; densify."""
    p = build_world_still_prompt(world_brief)
    # Allow at most ONE consecutive newline; no '\n\n'
    assert "\n\n" not in p


def test_world_still_prompt_under_1500_chars(world_brief):
    """Hard cap to fit Seedream / 即梦 prompt window."""
    p = build_world_still_prompt(world_brief)
    assert len(p) <= 1500, f"Prompt is {len(p)} chars, must be <=1500"


def test_world_still_prompt_subject_at_upper_third(world_brief):
    """The hero composition must place the subject in the upper third
    (not lower — the world detail page docks text at the bottom)."""
    p = build_world_still_prompt(world_brief)
    assert "上 1/3" in p or "上三分位" in p or "upper third" in p


# ---- script poster ----

def test_script_poster_prompt_aspect_ratio(world_brief, script_brief):
    p = build_script_poster_prompt(world_brief, script_brief)
    assert "3:2" in p


def test_script_poster_inherits_world_palette(world_brief, script_brief):
    p = build_script_poster_prompt(world_brief, script_brief)
    for color in world_brief.palette:
        assert color in p


def test_script_poster_includes_dramatic_anchor(world_brief, script_brief):
    p = build_script_poster_prompt(world_brief, script_brief)
    assert "travel case" in p


def test_script_poster_forbids_spoilers(world_brief, script_brief):
    p = build_script_poster_prompt(world_brief, script_brief)
    for forbidden in script_brief.forbidden_spoiler_elements:
        assert forbidden in p


def test_script_poster_under_1500_chars(world_brief, script_brief):
    p = build_script_poster_prompt(world_brief, script_brief)
    assert len(p) <= 1500


# ---- character portrait ----

def test_character_portrait_aspect_ratio(world_brief):
    p = build_character_portrait_prompt(world_brief, character_name="陈茉")
    assert "2:3" in p


def test_character_portrait_uses_per_character_brief(world_brief):
    p = build_character_portrait_prompt(world_brief, character_name="陈茉")
    assert "qipao" in p
    assert "lattice" in p
    assert "guarded" in p


def test_character_portrait_eye_line_upper_third(world_brief):
    """Critical: avatar circle crop depends on eye line being on upper third."""
    p = build_character_portrait_prompt(world_brief, character_name="陈茉")
    assert "upper third" in p or "上三分位" in p or "上 1/3" in p


def test_character_portrait_inherits_world_lighting(world_brief):
    p = build_character_portrait_prompt(world_brief, character_name="陈茉")
    # Must reference the parent world's series signature
    assert world_brief.series_signature_line in p


def test_character_portrait_unknown_character_raises(world_brief):
    with pytest.raises(KeyError):
        build_character_portrait_prompt(world_brief, character_name="UnknownCharacter")


def test_character_portrait_under_1500_chars(world_brief):
    p = build_character_portrait_prompt(world_brief, character_name="陈茉")
    assert len(p) <= 1500


def test_character_portrait_no_secret_leakage(world_brief):
    """Even though this builder doesn't take secrets directly, sanity check
    that 'secret' or similar concepts don't bleed in via accident."""
    p = build_character_portrait_prompt(world_brief, character_name="陈茉")
    assert "secret" not in p.lower()
```

- [x] **Step 5.3: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_image_prompt_builder.py -v`
Expected: import errors / many FAIL (the new function names don't exist yet).

- [x] **Step 5.4: Replace image_prompt_builder.py with new implementation**

Replace `backend/services/image_prompt_builder.py` entirely with:

```python
"""Image prompt builder — single-paragraph dense Chinese prompts driven by VisualBrief.

Three builders only:
- build_world_still_prompt(brief) → 21:9 cinematic establishing still (the source of truth;
  3:2 browse-card cover is server-cropped from this image, no separate prompt)
- build_script_poster_prompt(world_brief, script_brief) → 3:2 dramatic close-up
- build_character_portrait_prompt(world_brief, character_name) → 2:3 environmental portrait

Style anchored to:
- Roger Deakins / Gregory Crewdson photographic realism
- 35mm film grain, anamorphic 1.85x lens character
- Single-paragraph dense prose (no blank lines — they waste prompt budget on Seedream/即梦)
- Chinese as primary language; English reserved for cinematographer names + lens/film specs

Hard cap: 1500 chars per prompt to fit 即梦 prompt window with margin.
"""
from __future__ import annotations

from services.visual_brief import (
    CharacterVisualBrief,
    ScriptVisualBrief,
    WorldVisualBrief,
)


_NEG_BASE = (
    "禁：画面里任何文字、中文字符、logo、水印；"
    "二次元、漫画、卡通、插画、矢量扁平、水墨、工笔；"
    "霓虹、过饱和、HDR 光晕；"
    "塑料感皮肤、AI 美图脸、磨皮、多余手指、畸形脸；"
    "影棚轮廓光、明星脸、品牌 logo"
)


def _palette_str(palette: list[str]) -> str:
    return "、".join(palette)


def build_world_still_prompt(brief: WorldVisualBrief) -> str:
    """21:9 ultra-wide establishing still. Subject at upper third, lower 60%
    is text-safe negative space (the world detail page docks H1/CTA at bottom).
    The central 3:2 region of this image is auto-cropped to produce
    `world.cover_image` — composition must keep the anchor inside that region.
    """
    p = (
        f"21:9 电影宽幅 establishing shot。"
        f"场景：{brief.anchor_location}；"
        f"天候：{brief.weather}；"
        f"三层景深，前景近景物 / 中景主体 / 远景融入大气透视。"
        f"主体落画面上 1/3 三分位：{brief.key_prop}；"
        f"任何人影必须背身或剪影、绝不正面、绝不抢主体。"
        f"下 60% 画面留作 text-safe 纯负空间——同色调的雾、水、暗地，无任何竞争元素。"
        f"光线：{brief.lighting_signature}；深阴影保留 #0a0d12 不抬灰。"
        f"色板：{_palette_str(brief.palette)}；明显去饱和。"
        f"质感：{brief.camera_grammar}；材质真实——{brief.dominant_materials}。"
        f"摄影语言对标 Roger Deakins、Gregory Crewdson。"
        f"构图：21:9 宽幅，画面正中 3:2 区域必须独立成立（将自动裁为浏览墙卡片），"
        f"9:16 中心裁切仍保留主体。"
        f"画内绝对无文字、无 logo、无水印。"
        f"Series 一致性：{brief.series_signature_line}。"
        f"{_NEG_BASE}。"
    )
    return p


def build_script_poster_prompt(
    world_brief: WorldVisualBrief, script_brief: ScriptVisualBrief
) -> str:
    """3:2 dramatic close-up. Inherits world palette + lighting; adds the
    script's dramatic anchor and a single accent color break. Forbids any
    spoiler element by name.
    """
    spoilers = "、".join(script_brief.forbidden_spoiler_elements)
    spoiler_clause = f"严禁出现：{spoilers}" if spoilers else ""

    p = (
        f"3:2 电影戏剧特写剧照。"
        f"场景延续世界视觉指纹：{world_brief.anchor_location}；"
        f"天候：{world_brief.weather}。"
        f"主体紧景特写：{script_brief.dramatic_anchor}。"
        f"画面构图为静帧戏剧——是这个故事的视觉问题，不是答案。"
        f"光线沿用世界主图同款：{world_brief.lighting_signature}；3:1 反差。"
        f"色板：{_palette_str(world_brief.palette)}，"
        f"加一道剧本破调——{script_brief.accent_color_break}（弱到读作不对劲而非冒犯）。"
        f"质感：{world_brief.camera_grammar}；材质真实——{world_brief.dominant_materials}。"
        f"Series 一致性：与世界主图同一夜、同一地点、同一摄影师，"
        f"是更紧景别的同夜剪影。{world_brief.series_signature_line}。"
        f"画内无文字、无 logo、无水印。"
        f"{spoiler_clause}。"
        f"{_NEG_BASE}；graphic blood、gore、谋杀场面、任何剧透元素。"
    )
    return p


def build_character_portrait_prompt(
    world_brief: WorldVisualBrief, *, character_name: str
) -> str:
    """2:3 vertical environmental portrait. Eye line on upper third (critical
    for the auto-cropped circular avatar). Inherits world lighting + palette.
    """
    if character_name not in world_brief.characters:
        raise KeyError(f"character {character_name!r} not in world_brief.characters")

    cb: CharacterVisualBrief = world_brief.characters[character_name]

    p = (
        f"2:3 竖幅电影环境肖像，{character_name}。"
        f"Framing：{cb.framing}；"
        f"眼线必须严格落在画面上三分位横线上（upper third — 此区将自动裁为圆形小头像，"
        f"脸必须居于该裁切中心）；非正面、非 model pose、非看镜头。"
        f"服装：{cb.wardrobe}（period-accurate，非戏服）。"
        f"姿态：{cb.gesture}（像刚从手里活儿停顿下来，不是摆姿势）。"
        f"情绪：{cb.emotional_register}。"
        f"环境：{cb.setting}；环境只暗示，焦点在她。"
        f"光线沿用世界主图同款：{world_brief.lighting_signature}；"
        f"侧光主导，背光面深落影几乎无补光，发缘细 rim 接 key 暖光。"
        f"质感是全部：真实人皮——可见毛孔、眼角细纹、肤色微差，"
        f"严禁磨皮、严禁数字塑料感；发丝独立有重量；布料看得到经纬与自然褶皱。"
        f"{world_brief.camera_grammar}。对标 Roger Deakins 诚实光与 Gregory Crewdson 静态戏剧。"
        f"色板：{_palette_str(world_brief.palette)}；肤色诚实，不美颜。"
        f"构图：2:3 竖幅，主体压左三分位竖线，眼线压上三分位横线。"
        f"画内无文字、无标签。"
        f"Series 一致性：{world_brief.series_signature_line}；"
        f"她应该看起来'那夜在那个场景里被拍下'，不是单独委约的肖像。"
        f"{_NEG_BASE}；正面 model 姿势、看镜头微笑、商业影棚肖像、"
        f"鲜艳口红、古装剧戏服感、网红脸、AI glamour、stock 名人照。"
    )
    return p
```

- [x] **Step 5.5: Run tests to verify pass**

Run: `cd backend && python -m pytest tests/test_image_prompt_builder.py -v`
Expected: all tests PASS. If any fail on length (>1500 chars), trim the relevant builder; if any fail on missing keyword, add the keyword.

- [x] **Step 5.6: Commit**

```bash
git add backend/services/image_prompt_builder.py backend/tests/test_image_prompt_builder.py
git commit -m "feat(image-prompt): rewrite builders to consume VisualBrief, dense Chinese single-paragraph"
```

---

## Task 6: Alembic migration — add visual_brief, drop poster_image

**Files:**
- Create: `backend/migrations/versions/<rev>_visual_brief_and_drop_poster.py`
- Modify: `backend/models/world.py` — add `visual_brief` JSONB column, remove `poster_image`
- Modify: `backend/models/script.py` — add `visual_brief` JSONB column

**Why:** Schema needs a place to persist the brief, and the dropped `poster_image` field must come out of the World model.

- [x] **Step 6.1: Update model files**

Modify `backend/models/world.py`. Inside `class World`, replace lines 24-26:

```python
    cover_image: Mapped[str] = mapped_column(String(500), default="")
    poster_image: Mapped[str] = mapped_column(String(500), default="")
    hero_image: Mapped[str] = mapped_column(String(500), default="")
```

with:

```python
    cover_image: Mapped[str] = mapped_column(String(500), default="")  # 3:2, server-cropped from hero_image
    hero_image: Mapped[str] = mapped_column(String(500), default="")  # 21:9, source-of-truth
    visual_brief: Mapped[dict | None] = mapped_column(_JSONB, nullable=True, default=None)
```

Modify `backend/models/script.py`. Inside `class Script`, after `cover_image` line, add:

```python
    visual_brief: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)
```

- [x] **Step 6.2: Generate Alembic migration**

Run: `cd backend && alembic revision --autogenerate -m "visual_brief and drop poster_image"`
Expected: a new file under `backend/migrations/versions/<hash>_visual_brief_and_drop_poster.py` is generated.

- [x] **Step 6.3: Verify the autogen migration**

Open the generated file. Confirm it contains:
- `op.add_column('worlds', sa.Column('visual_brief', ...))`
- `op.add_column('scripts', sa.Column('visual_brief', ...))`
- `op.drop_column('worlds', 'poster_image')`

If autogen missed the drop (rare), manually add:
```python
op.drop_column('worlds', 'poster_image')
```
to the `upgrade()` function and the corresponding `op.add_column('worlds', sa.Column('poster_image', sa.String(500), ...))` in `downgrade()`.

- [x] **Step 6.4: Run migration**

Run: `cd backend && alembic upgrade head`
Expected: migration applies cleanly.

- [x] **Step 6.5: Verify schema in DB**

Run: `cd backend && python -c "
import asyncio
from sqlalchemy import text
from database import async_session
async def check():
    async with async_session() as s:
        for table in ['worlds', 'scripts']:
            r = await s.execute(text(f\"SELECT column_name FROM information_schema.columns WHERE table_name='{table}'\"))
            cols = [row[0] for row in r]
            print(table, ':', sorted(cols))
asyncio.run(check())
"`

Expected output: `worlds` includes `visual_brief`, no longer includes `poster_image`. `scripts` includes `visual_brief`.

- [x] **Step 6.6: Commit**

```bash
git add backend/models/world.py backend/models/script.py backend/migrations/versions/
git commit -m "feat(db): add visual_brief column, drop poster_image"
```

---

## Task 7: Strip poster_image references from backend code

**Files (search-and-fix):** Anywhere in backend that reads/writes `poster_image`.

**Why:** Migration removed the column. Any remaining code references will throw at runtime.

- [x] **Step 7.1: Find all references**

Run: `cd backend && grep -rn "poster_image" --include="*.py" .`

Triage by file:
- `services/world_image_fields.py` — drop poster handling entirely
- `services/world_creator_agent_v2.py` — drop poster from image_tasks (will be properly handled in Task 8)
- `services/world_creator_agent.py` (legacy v1) — drop poster
- `schemas/world.py` — drop poster_image from response
- `api/worlds.py`, `api/admin.py` — drop from serializers / responses
- `tests/` — drop poster expectations (will redo in Task 9)

- [x] **Step 7.2: Fix `services/world_image_fields.py`**

Replace the entire file with:

```python
from __future__ import annotations


def _clean_image_url(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def resolve_world_image_fields(
    *,
    cover_image: object = "",
    hero_image: object = "",
) -> dict[str, str]:
    cover = _clean_image_url(cover_image)
    hero = _clean_image_url(hero_image)

    if not hero:
        hero = cover
    if not cover:
        cover = hero

    return {"cover_image": cover, "hero_image": hero}


def resolve_world_image_fields_from_mapping(data: dict | None) -> dict[str, str]:
    payload = data or {}
    return resolve_world_image_fields(
        cover_image=payload.get("cover_image"),
        hero_image=payload.get("hero_image"),
    )


def resolve_world_image_fields_from_model(world: object) -> dict[str, str]:
    return resolve_world_image_fields(
        cover_image=getattr(world, "cover_image", ""),
        hero_image=getattr(world, "hero_image", ""),
    )
```

- [x] **Step 7.3: Fix `schemas/world.py`**

Run: `grep -n "poster_image" backend/schemas/world.py`
For each hit, remove the line. Keep `cover_image` and `hero_image`.

- [x] **Step 7.4: Fix `api/worlds.py` and `api/admin.py`**

Run: `grep -n "poster_image" backend/api/worlds.py backend/api/admin.py`
For each hit, remove that line of serialization. (No replacement needed — frontend will be updated in PR 2 to stop reading the field.)

- [x] **Step 7.5: Fix `services/world_creator_agent.py` (legacy v1)**

Run: `grep -n "poster_image\|poster" backend/services/world_creator_agent.py`
Remove poster generation and field assignment. If the legacy agent isn't used (admin only routes through v2), this is dead code — leave a `# TODO: remove legacy agent` comment but strip poster_image references.

- [x] **Step 7.6: Run tests + check for runtime references**

Run: `cd backend && python -m pytest tests/test_visual_brief_schema.py tests/test_visual_brief_generator.py tests/test_image_cropper.py tests/test_image_prompt_builder.py -v`

Then: `cd backend && grep -rn "poster_image" --include="*.py" .` — expected output: only test files we'll fix in Task 9, or zero hits.

- [x] **Step 7.7: Commit**

```bash
git add backend/services/world_image_fields.py backend/services/world_creator_agent.py \
        backend/schemas/world.py backend/api/worlds.py backend/api/admin.py
git commit -m "refactor: drop poster_image from world serializers and helpers"
```

---

## Task 8: Wire visual_brief + new images stage into world_creator_agent_v2

**Files:**
- Modify: `backend/services/world_creator_agent_v2.py`

**Why:** This is the heart of the refactor — the world creation pipeline gains a `visual_brief` stage and the `images` stage now generates 1 hero + N portraits + server-crops a cover.

- [x] **Step 8.1: Inspect current stage layout**

Run: `cd backend && grep -n "_STAGE_INDEX\|_SCRIPT_STAGE_INDEX\|TOTAL_STAGES\|_SCRIPT_TOTAL_STAGES" services/world_creator_agent_v2.py | head -20`

Note the current world stages list. We're inserting `visual_brief` before `images`.

- [x] **Step 8.2: Add visual_brief stage to the world pipeline stage map**

Find the `_STAGE_INDEX` dict (the world creator stage indices). Before the `"images"` entry, insert `"visual_brief"`. Renumber `"images"` and any later entries. Update `TOTAL_STAGES` accordingly.

Example (pattern only — match existing dict shape exactly):

```python
_STAGE_INDEX = {
    "research": 0,
    "world_skeleton": 1,
    # ... existing intermediate stages ...
    "visual_brief": N,
    "images": N + 1,
    # ... shift later entries by +1 ...
}
TOTAL_STAGES = len(_STAGE_INDEX)
```

- [x] **Step 8.3: Add `_run_visual_brief_stage` method**

Locate the `_run_images_stage` method (the existing image generator yielded around line 1000). Immediately before it, add a new async generator method:

```python
async def _run_visual_brief_stage(
    self,
    *,
    payload: dict,
    characters,  # list[Character]
):
    """Stage: produce the WorldVisualBrief via one LLM call.

    Stores the brief on `payload["visual_brief"]` (dict form).
    On failure, logs a warning and yields an empty brief — pipeline continues
    with degraded prompts (English fallback in the prompt template).
    """
    import time

    from services.visual_brief import generate_world_visual_brief

    start = time.monotonic()
    yield progress_event(
        "visual_brief", "started",
        stage_index=_STAGE_INDEX["visual_brief"],
        total_stages=TOTAL_STAGES,
    )

    target_chars = [c for c in characters if c.is_image_target]
    char_inputs = [
        {
            "name": c.name,
            "role_tag": getattr(c, "role_tag", ""),
            "personality": getattr(c, "personality", ""),
            "playable": getattr(c, "playable", False),
        }
        for c in target_chars
    ]

    try:
        brief = await generate_world_visual_brief(
            world_data=payload,
            characters=char_inputs,
            llm=self.llm,
        )
        payload["visual_brief"] = brief.model_dump()
        ok = True
    except Exception as exc:  # noqa: BLE001
        logger.warning("visual_brief_failed", error=str(exc))
        payload["visual_brief"] = None
        ok = False

    yield progress_event(
        "visual_brief", "completed",
        stage_index=_STAGE_INDEX["visual_brief"],
        total_stages=TOTAL_STAGES,
        duration_ms=int((time.monotonic() - start) * 1000),
        payload_summary={"ok": ok, "characters": len(char_inputs)},
    )
```

- [x] **Step 8.4: (Skipped — self.llm already exists and is the LLMRouter)**

The constructor already wires `self.llm` (an `LLMRouter`). The new `generate_world_visual_brief` accepts the LLMRouter directly and uses the same `_collect_tool_output` pattern as the existing strategy service. **No new attribute or adapter needed.**

- [x] **Step 8.5: Replace the body of `_run_images_stage`**

Find the existing `_run_images_stage` body. Replace the section from `from services.image_prompt_builder import (...)` down through the placement of `payload["cover_image"]`, `payload["hero_image"]`, `payload["poster_image"]` with this:

```python
from services.image_prompt_builder import (
    build_world_still_prompt,
    build_character_portrait_prompt,
)
from services.image_cropper import crop_to_aspect_ratio, materialize_image_bytes
from services.visual_brief import WorldVisualBrief

# Reconstruct typed brief from payload (or fall back to None — handled below)
brief_dict = payload.get("visual_brief") or {}
try:
    brief = WorldVisualBrief.model_validate(brief_dict) if brief_dict else None
except Exception as exc:  # noqa: BLE001
    logger.warning("visual_brief_invalid_skipping_images", error=str(exc))
    brief = None

if brief is None:
    # No brief → no cinematic prompts → fall back to placeholders.
    # (Pipeline still completes; admin can manually trigger re-gen.)
    payload["cover_image"] = IMAGE_PLACEHOLDER_URL
    payload["hero_image"] = IMAGE_PLACEHOLDER_URL
    payload["character_images"] = {c.name: IMAGE_PLACEHOLDER_URL for c in target_chars}
    yield progress_event(
        "images", "completed",
        stage_index=_STAGE_INDEX["images"],
        total_stages=TOTAL_STAGES,
        duration_ms=int((time.monotonic() - start) * 1000),
        payload_summary={"npc_avatars": len(target_chars), "skipped": True, "reason": "no_brief"},
    )
    return

# Build prompts — 1 hero + N portraits.
hero_prompt = build_world_still_prompt(brief)
hero_task = ("hero", hero_prompt, "21:9", "worlds/hero")
portrait_tasks = []
for char in target_chars:
    if char.name not in brief.characters:
        # No per-character brief — skip this portrait, fallback to placeholder.
        portrait_tasks.append(("npc:" + char.name, None, None, None))
        continue
    prompt = build_character_portrait_prompt(brief, character_name=char.name)
    portrait_tasks.append((f"npc:{char.name}", prompt, "2:3", "characters"))

image_storage = get_image_storage()
semaphore = asyncio.Semaphore(6)

async def gen_image(key, prompt, aspect_ratio, category):
    if prompt is None:
        return key, IMAGE_PLACEHOLDER_URL, None
    async with semaphore:
        try:
            result = await self.image_gen.generate_image(prompt, aspect_ratio=aspect_ratio)
            storage_name = world_name if not key.startswith("npc:") else key[4:]
            storage_key = make_image_key(category, storage_name)
            url = await save_generated_image_result(image_storage, result, storage_key)
            # Return the ImageResult so the caller can reuse bytes for cropping
            return key, url or IMAGE_PLACEHOLDER_URL, result
        except Exception as exc:  # noqa: BLE001
            logger.warning("image_gen_failed", key=key, error=str(exc))
            return key, IMAGE_PLACEHOLDER_URL, None

# Run all in parallel.
all_tasks = [hero_task] + portrait_tasks
total = len(all_tasks)
yield progress_event(
    "images", "subtask_started",
    subtask_key="batch_kickoff",
    subtask_total=total,
    subtask_index=0,
)

coros = [gen_image(k, p, ar, cat) for k, p, ar, cat in all_tasks]
raw = await asyncio.gather(*coros, return_exceptions=True)

results: dict[str, tuple[str, object | None]] = {}  # key -> (url, ImageResult|None)
for idx, item in enumerate(raw):
    if isinstance(item, BaseException):
        logger.warning("image_task_exception", index=idx, error=str(item))
        key = all_tasks[idx][0]
        results[key] = (IMAGE_PLACEHOLDER_URL, None)
    else:
        key, url, result = item
        results[key] = (url, result)
    yield progress_event(
        "images", "subtask_completed",
        subtask_key=all_tasks[idx][0],
        subtask_index=idx + 1,
        subtask_total=total,
    )

hero_url, hero_result = results.get("hero", (IMAGE_PLACEHOLDER_URL, None))
payload["hero_image"] = hero_url

# Server-crop hero → cover (3:2). Skip if hero is placeholder.
cover_url = IMAGE_PLACEHOLDER_URL
if hero_result is not None and hero_url != IMAGE_PLACEHOLDER_URL:
    try:
        hero_bytes = await materialize_image_bytes(hero_result)
        cover_bytes = crop_to_aspect_ratio(hero_bytes, target_w=3, target_h=2)
        cover_key = make_image_key("worlds/cover", world_name, ext="jpg")
        cover_url = await image_storage.save(cover_bytes, cover_key)
    except Exception as exc:  # noqa: BLE001
        logger.warning("cover_crop_failed", error=str(exc))
        cover_url = hero_url  # last-ditch fallback: use hero in card slot too
payload["cover_image"] = cover_url

payload["character_images"] = {
    c.name: results.get(f"npc:{c.name}", (IMAGE_PLACEHOLDER_URL, None))[0]
    for c in target_chars
}

placeholder_count = sum(1 for k, (u, _) in results.items() if u == IMAGE_PLACEHOLDER_URL)
yield progress_event(
    "images", "completed",
    stage_index=_STAGE_INDEX["images"],
    total_stages=TOTAL_STAGES,
    duration_ms=int((time.monotonic() - start) * 1000),
    payload_summary={
        "hero": "real" if hero_url != IMAGE_PLACEHOLDER_URL else "placeholder",
        "cover": "cropped" if cover_url not in (IMAGE_PLACEHOLDER_URL, hero_url) else "fallback",
        "npc_avatars": len(target_chars),
        "placeholder_count": placeholder_count,
    },
)
```

- [x] **Step 8.6: Insert visual_brief stage call in the world creator main loop**

Find where `_run_images_stage` is awaited in the agent's `create_world` method. Immediately before that `async for ... in self._run_images_stage(...)` block, add:

```python
async for evt in self._run_visual_brief_stage(payload=payload, characters=characters):
    yield evt
```

- [x] **Step 8.7: Run pipeline tests (will partially fail; we'll fix tests in Task 9)**

Run: `cd backend && python -m pytest tests/test_world_creator_v2_pipeline.py -v -x 2>&1 | head -60`

Note any failures — they likely reference `poster_image` or stage index counts. We fix in Task 9.

- [x] **Step 8.8: Commit (WIP — tests fail, fixed in next task)**

```bash
git add backend/services/world_creator_agent_v2.py
git commit -m "feat(world-creator): add visual_brief stage; images stage outputs hero + cropped cover"
```

---

## Task 9: Update pipeline tests

**Files:**
- Modify: `backend/tests/test_world_creator_v2_pipeline.py`
- Modify: `backend/tests/test_world_creator_v2_script.py`
- Modify: `backend/tests/test_world_creator_agent_dynamic.py`
- (Possibly) Modify: `backend/tests/test_admin_api.py`, `backend/tests/test_world_api.py` — anything that asserts `poster_image`

**Why:** Existing tests assume the old `cover/hero/poster` triple + 1:1 portraits. They need updating to match the new pipeline shape.

- [x] **Step 9.1: List all failing tests**

Run: `cd backend && python -m pytest tests/test_world_creator_v2_pipeline.py tests/test_world_creator_v2_script.py tests/test_admin_api.py tests/test_world_api.py -v 2>&1 | grep -E "FAIL|ERROR" | head -30`

- [x] **Step 9.2: Fix `test_world_creator_v2_pipeline.py` — image stage assertions**

Search for assertions on `cover_image / hero_image / poster_image / character_images / 1:1`. For each:
- Drop `poster_image` checks entirely
- Change `aspect_ratio == "16:9"` (old hero) to `"21:9"`
- Change `aspect_ratio == "16:10"` or `"3:4"` (old cover/poster) — these no longer correspond to LLM calls; assert that **only 1 hero call + N portrait calls happen** (hero+cover are not two LLM calls)
- Change portrait `1:1` to `2:3`
- Add a check: `payload.get("visual_brief")` is non-None after the brief stage runs

Pattern to add for image-call counting:
```python
# new shape: 1 hero call + N portrait calls (cover is server-cropped, not LLM)
assert image_gen_call_count == 1 + len([c for c in characters if c.is_image_target])
```

- [x] **Step 9.3: Fix `test_world_creator_v2_script.py`**

Search for `cover_image` and adjust ratio assertion: script poster is `3:2` (was `16:9`).

- [x] **Step 9.4: Add a new visual_brief integration test in `test_world_creator_v2_pipeline.py`**

Add at the bottom of the file:

```python
@pytest.mark.asyncio
async def test_visual_brief_stage_persists_brief_to_payload(monkeypatch):
    """Verify the new visual_brief stage runs and writes to payload."""
    # Use the existing test agent fixture pattern in this file.
    # (Adapt to whatever fixture/helper the file already uses.)
    # Mock self.json_llm.complete_json to return a valid WorldVisualBrief dict.
    # Run pipeline, assert payload["visual_brief"] is non-empty.
    pass  # IMPLEMENTATION: copy the closest existing pipeline-stage test pattern in this file and adapt
```

(Note: the executing engineer should look at how other stages are tested in this file and pattern-match. The existing tests use a specific fixture style — preserve it.)

- [x] **Step 9.5: Fix `test_admin_api.py` and `test_world_api.py` if needed**

Run: `cd backend && grep -n "poster_image" tests/test_admin_api.py tests/test_world_api.py`
For each hit, remove the assertion or expectation.

- [x] **Step 9.6: Run all backend tests**

Run: `cd backend && python -m pytest tests/ -v 2>&1 | tail -30`
Expected: all PASS, or only unrelated failures (note any unrelated failure for follow-up).

- [x] **Step 9.7: Commit**

```bash
git add backend/tests/
git commit -m "test: update pipeline tests for visual_brief + 21:9 hero + 2:3 portraits"
```

---

## Task 10: Wire script visual_brief stage

**Files:**
- Modify: `backend/services/world_creator_agent_v2.py` (script creation flow, around line 1480)

**Why:** Same shape as world flow, simpler — 1 LLM brief call + 1 image call.

- [x] **Step 10.1: Add `_run_script_visual_brief_stage` method**

In `world_creator_agent_v2.py`, locate the script creation flow (`create_script` method or equivalent — search for `_SCRIPT_STAGE_INDEX` and the `script_images` stage). Add a new method before `script_images`:

```python
async def _run_script_visual_brief_stage(
    self, *, script_payload: dict, world_data: dict
):
    import time
    from services.visual_brief import generate_script_visual_brief

    start = time.monotonic()
    yield progress_event(
        "script_visual_brief", "started",
        stage_index=_SCRIPT_STAGE_INDEX["script_visual_brief"],
        total_stages=_SCRIPT_TOTAL_STAGES,
    )

    world_brief = world_data.get("visual_brief") or {}
    if not world_brief:
        logger.warning("script_visual_brief_no_world_brief")
        script_payload["visual_brief"] = None
        yield progress_event(
            "script_visual_brief", "completed",
            stage_index=_SCRIPT_STAGE_INDEX["script_visual_brief"],
            total_stages=_SCRIPT_TOTAL_STAGES,
            duration_ms=int((time.monotonic() - start) * 1000),
            payload_summary={"ok": False, "reason": "no_world_brief"},
        )
        return

    try:
        brief = await generate_script_visual_brief(
            script_data=script_payload,
            world_brief=world_brief,
            llm=self.llm,
        )
        script_payload["visual_brief"] = brief.model_dump()
        ok = True
    except Exception as exc:  # noqa: BLE001
        logger.warning("script_visual_brief_failed", error=str(exc))
        script_payload["visual_brief"] = None
        ok = False

    yield progress_event(
        "script_visual_brief", "completed",
        stage_index=_SCRIPT_STAGE_INDEX["script_visual_brief"],
        total_stages=_SCRIPT_TOTAL_STAGES,
        duration_ms=int((time.monotonic() - start) * 1000),
        payload_summary={"ok": ok},
    )
```

- [x] **Step 10.2: Add to `_SCRIPT_STAGE_INDEX` and bump `_SCRIPT_TOTAL_STAGES`**

Find `_SCRIPT_STAGE_INDEX`. Insert `"script_visual_brief"` BEFORE `"script_images"`. Renumber subsequent entries.

- [x] **Step 10.3: Replace the body of script_images stage**

Find the existing script_images stage body (around line 1485 in current code). Replace from `from services.image_prompt_builder import build_script_cover_prompt` through end of stage with:

```python
from services.image_prompt_builder import build_script_poster_prompt
from services.visual_brief import WorldVisualBrief, ScriptVisualBrief

script_cover_url = IMAGE_PLACEHOLDER_URL

world_brief_dict = world_data.get("visual_brief") or {}
script_brief_dict = working_payload.get("visual_brief") or {}

if not (self.image_gen and world_brief_dict and script_brief_dict):
    reason = (
        "no_image_gen" if not self.image_gen
        else "no_world_brief" if not world_brief_dict
        else "no_script_brief"
    )
    logger.info("script_image_skipped", reason=reason)
else:
    try:
        world_brief = WorldVisualBrief.model_validate(world_brief_dict)
        script_brief = ScriptVisualBrief.model_validate(script_brief_dict)
        prompt = build_script_poster_prompt(world_brief, script_brief)
        result = await self.image_gen.generate_image(prompt, aspect_ratio="3:2")
        storage = get_image_storage()
        storage_key = make_image_key("scripts/cover", script_base.get("name", "script"))
        saved = await save_generated_image_result(storage, result, storage_key)
        script_cover_url = saved or IMAGE_PLACEHOLDER_URL
    except Exception as exc:  # noqa: BLE001
        logger.warning("script_cover_failed", error=str(exc))

yield progress_event(
    "script_images", "completed",
    stage_index=_SCRIPT_STAGE_INDEX["script_images"],
    total_stages=_SCRIPT_TOTAL_STAGES,
    payload_summary={
        "cover": "real" if script_cover_url != IMAGE_PLACEHOLDER_URL else "placeholder",
    },
)
```

- [x] **Step 10.4: Wire script_visual_brief into create_script main loop**

Find the line in `create_script` (or equivalent) where `script_images` is yielded. Immediately before it, add:

```python
async for evt in self._run_script_visual_brief_stage(
    script_payload=working_payload, world_data=world_data,
):
    yield evt
```

- [x] **Step 10.5: Update `final_payload` for script result**

Find the `final_payload` dict (around line 1516). Add:
```python
"visual_brief": working_payload.get("visual_brief"),
```

- [x] **Step 10.6: Run script tests**

Run: `cd backend && python -m pytest tests/test_world_creator_v2_script.py -v`
Fix any new test failures (likely stage-count assertions).

- [x] **Step 10.7: Commit**

```bash
git add backend/services/world_creator_agent_v2.py backend/tests/test_world_creator_v2_script.py
git commit -m "feat(script-creator): add script_visual_brief stage; script poster at 3:2"
```

---

## Task 11: Update draft → published persistence

**Files:**
- Modify: `backend/api/admin.py` (publish endpoints — find functions that copy draft.payload → World/Script rows)

**Why:** When publishing a draft to `worlds` / `scripts`, the new `visual_brief` field needs to be carried over (and `poster_image` must NOT be carried since the column is gone).

- [x] **Step 11.1: Find publish handlers**

Run: `cd backend && grep -n "def publish\|World(.*=\|Script(.*=" api/admin.py | head -20`

Identify the function(s) that materialize a draft into a World or Script row.

- [x] **Step 11.2: Add visual_brief to constructors, drop poster_image**

For the World construction call, add:
```python
visual_brief=payload.get("visual_brief"),
```
And remove `poster_image=...` if present.

For the Script construction call, add:
```python
visual_brief=payload.get("visual_brief"),
```

- [x] **Step 11.3: Run admin tests**

Run: `cd backend && python -m pytest tests/test_admin_api.py -v`
Expected: PASS.

- [x] **Step 11.4: Commit**

```bash
git add backend/api/admin.py
git commit -m "feat(admin): persist visual_brief on world/script publish"
```

---

## Task 12: PR1 Smoke test

**Why:** Real end-to-end run with a small test world to confirm the new pipeline works against a real LLM + real Seedream.

- [x] **Step 12.1: Start backend dev server**

Run in separate terminal: `cd backend && uvicorn main:app --reload --port 8000`

- [x] **Step 12.2: Trigger a small world creation via admin workshop**

Use the admin UI at `http://localhost:3000/admin/generate/world` (assuming frontend dev server is also running) — but for backend-only smoke, call the SSE endpoint directly:

Run:
```bash
curl -N -X POST http://localhost:8000/api/admin/generate/world/start \
  -H "Content-Type: application/json" \
  -H "Cookie: <your admin session cookie>" \
  -d '{
    "name": "测试雾隐镇",
    "genre": "悬疑",
    "era": "民国",
    "base_setting": "湘西边陲临河小镇，秋冬常年浓雾。镇口石桥连接两岸。"
  }'
```

(Adapt to whatever the actual admin generate endpoint is — see `api/admin.py`.)

Watch the SSE event stream:
- ✅ Should see `progress_event` for stage `visual_brief` (started → completed)
- ✅ Should see `progress_event` for stage `images` with `subtask_total = 1 + N` (hero + portraits, no cover/poster)
- ✅ Final result should have `cover_image` (3:2), `hero_image` (21:9), `character_images` map
- ✅ Should NOT have `poster_image`
- ✅ Should have `visual_brief` dict

- [x] **Step 12.3: Inspect generated image dimensions**

Open the URLs from the SSE result in a browser:
- `hero_image` URL — verify ~21:9 wide
- `cover_image` URL — verify ~3:2 (should be a center crop of the hero)
- A `character_images[name]` URL — verify ~2:3 vertical

- [x] **Step 12.4: Eyeball quality check**

Compare the three images. Pass criteria:
- ✅ All three feel like the **same scene / same lighting / same world** (series_signature is working)
- ✅ Hero subject sits in the upper third, not the center or bottom
- ✅ Character eye line is on the upper third (visually)
- ✅ Style is photographic realism, NOT anime / illustration / cyberpunk neon
- ✅ No Chinese text in any image
- ✅ Cover is a sensible center-crop of hero (subject is preserved)

If any fail: open `services/image_prompt_builder.py`, adjust the offending prompt, re-run.

- [x] **Step 12.5: PR 1 ready**

If smoke passes, PR 1 is complete. If you've been committing along the way, push the branch:

```bash
git push -u origin <branch-name>
```

Then open a PR with title `feat: image pipeline refactor — VisualBrief + 21:9 hero + cropped 3:2 cover` and description summarizing the 5 decisions baked in.

---

# PR 2 — Frontend ratio alignment

## Task 13: Drop poster_image from frontend types

**Files:**
- Modify: `frontend/lib/types.ts`
- Modify: `frontend/lib/draft-schemas.ts` (if it references poster_image)
- Modify: `frontend/components/admin/editor/preview/WorldPreviewPane.tsx` (line 40 currently reads `poster_image`)

**Why:** Backend no longer returns this field. Frontend consumers must stop reading it.

- [x] **Step 13.1: Find all references**

Run: `cd frontend && grep -rn "poster_image" --include="*.ts" --include="*.tsx" src app components lib 2>/dev/null`

(Adjust paths to actual frontend layout.)

- [x] **Step 13.2: Remove from types.ts**

Open `frontend/lib/types.ts`. Remove every line containing `poster_image` (it appears ~3 times based on earlier scan: lines ~209, ~245, others).

- [x] **Step 13.3: Remove from draft-schemas.ts if present**

Run: `cd frontend && grep -n "poster_image" lib/draft-schemas.ts`
For each hit, delete the line / Zod field.

- [x] **Step 13.4: Update WorldPreviewPane to use cover_image**

`frontend/components/admin/editor/preview/WorldPreviewPane.tsx` line ~40:

Change:
```tsx
src={payload.poster_image ?? payload.cover_image}
```
to:
```tsx
src={payload.cover_image}
```

- [x] **Step 13.5: Run typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors. Fix any remaining `poster_image` references it surfaces.

- [x] **Step 13.6: Commit**

```bash
git add frontend/lib/types.ts frontend/lib/draft-schemas.ts \
        frontend/components/admin/editor/preview/WorldPreviewPane.tsx
git commit -m "refactor(types): drop poster_image — backend no longer returns it"
```

---

## Task 14: Update card aspect ratio 16:10 → 3:2

**Files:**
- Modify: `frontend/components/ui/PosterCard.tsx` (line 58)
- Modify: `frontend/components/landing/LandingExperience.tsx` (line 307)
- Modify: `frontend/app/discover/page.tsx` (line 199, skeleton)
- Modify: `frontend/app/history/page.tsx` (lines 315, 430, 528, 562)

**Why:** D1 = A. Cards are now 3:2.

- [x] **Step 14.1: Update PosterCard**

`frontend/components/ui/PosterCard.tsx` line 58:

Change:
```tsx
aspectRatio: "16 / 10",
```
to:
```tsx
aspectRatio: "3 / 2",
```

Also update the JSDoc comment on the file (line ~15 and line ~28) referencing 16:10 — change to 3:2.

- [x] **Step 14.2: Update Landing**

`frontend/components/landing/LandingExperience.tsx` line 307:

Change:
```tsx
aspectRatio: "16 / 10",
```
to:
```tsx
aspectRatio: "3 / 2",
```

- [x] **Step 14.3: Update Discover skeleton**

`frontend/app/discover/page.tsx` line 199:

Change:
```tsx
aspectRatio: "16 / 10",
```
to:
```tsx
aspectRatio: "3 / 2",
```

- [x] **Step 14.4: Update History (4 places)**

`frontend/app/history/page.tsx` — find each occurrence of `aspectRatio: "16 / 10"` (4 total at lines 315, 430, 528, 562 per earlier scan). Replace each with `aspectRatio: "3 / 2"`.

Run: `cd frontend && grep -n '"16 / 10"' app/history/page.tsx` — should return 0 hits after edits.

- [x] **Step 14.5: Fix world detail hero source**

`frontend/app/worlds/[id]/page.tsx` line 80 currently reads:

```tsx
const cover = world.banner_image || world.cover_image;
```

`world.banner_image` does not exist on the backend (never has). The intended hero source is `hero_image` (21:9 from new pipeline). Change to:

```tsx
const cover = world.hero_image || world.cover_image;
```

- [x] **Step 14.6: Visual smoke test in browser**

Run: `cd frontend && npm run dev`
Open `http://localhost:3000/discover`. Visual check:
- ✅ Cards are visibly slightly wider/squatter than before (16:10 = 1.6, 3:2 = 1.5 — small but perceptible)
- ✅ Images fill the card cleanly, no letterboxing
- ✅ Skeleton loaders match the live cards

Open `http://localhost:3000/` (landing). Same check on the featured 4 grid.

Open `http://localhost:3000/history`. Same check on history cards.

Open `http://localhost:3000/worlds/<some-id>`. The hero should now use `hero_image` (21:9) as the full-bleed background.

- [x] **Step 14.7: Commit**

```bash
git add frontend/components/ui/PosterCard.tsx \
        frontend/components/landing/LandingExperience.tsx \
        frontend/app/discover/page.tsx \
        frontend/app/history/page.tsx \
        frontend/app/worlds/\[id\]/page.tsx
git commit -m "feat(ui): card aspect ratio 16:10 → 3:2; fix world hero to use hero_image"
```

---

## Task 15: Update admin preview frame ratios

**Files:**
- Modify: `frontend/components/admin/editor/preview/PreviewFrame.tsx`
- Modify: `frontend/components/admin/editor/preview/WorldPreviewPane.tsx` (banner section line ~83)
- Modify: `frontend/components/admin/editor/preview/ScriptPreviewPane.tsx` (line 49)

**Why:** Admin preview should match production ratios. World card = 3:2; world hero/banner = 21:9 (was 21:9, keep but rename mental model); script card = 3:2.

- [x] **Step 15.1: Update PreviewFrame supported ratios**

`frontend/components/admin/editor/preview/PreviewFrame.tsx` line 40-45:

Change:
```tsx
ratio: "16/10" | "3/4" | "21/9";
// ...
const aspect = ratio === "16/10" ? "16 / 10" : ratio === "3/4" ? "3 / 4" : "21 / 9";
```
to:
```tsx
ratio: "3/2" | "21/9" | "2/3";
// ...
const aspect =
  ratio === "3/2" ? "3 / 2"
  : ratio === "21/9" ? "21 / 9"
  : "2 / 3";
```

(Now supports: 3/2 for cards, 21/9 for heros/banners, 2/3 for portraits.)

- [x] **Step 15.2: Update WorldPreviewPane card section (line ~40)**

Already updated in Task 13.4 to use `cover_image`. Now also change the ratio:

Change:
```tsx
<PreviewCover src={payload.cover_image} ratio="3/4" alt={...} />
```
(or whatever `ratio="..."` value it currently passes) to:
```tsx
<PreviewCover src={payload.cover_image} ratio="3/2" alt={...} />
```

- [x] **Step 15.3: Update WorldPreviewPane banner section (line ~83)**

Around line 83, the banner uses `ratio="21/9"` already with `payload.banner_image ?? payload.cover_image`. Change to:
```tsx
<PreviewCover src={payload.hero_image ?? payload.cover_image} ratio="21/9" alt={...} />
```
(Switch from non-existent `banner_image` to actual `hero_image`.)

- [x] **Step 15.4: Update ScriptPreviewPane (line 49)**

`frontend/components/admin/editor/preview/ScriptPreviewPane.tsx` line 49:

Change:
```tsx
<PreviewCover src={payload.cover_image} ratio="16/10" alt={...} />
```
to:
```tsx
<PreviewCover src={payload.cover_image} ratio="3/2" alt={...} />
```

- [x] **Step 15.5: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors.

- [x] **Step 15.6: Visual smoke test**

Open `http://localhost:3000/admin/worlds/drafts/<some-draft-id>` (or `/dev/editor-preview` if it's a sandbox page). Verify the 3 preview tiles render correctly:
- World card preview: 3:2
- World banner preview: 21:9
- Script card preview: 3:2

- [x] **Step 15.7: Commit**

```bash
git add frontend/components/admin/editor/preview/PreviewFrame.tsx \
        frontend/components/admin/editor/preview/WorldPreviewPane.tsx \
        frontend/components/admin/editor/preview/ScriptPreviewPane.tsx
git commit -m "feat(admin-preview): align preview ratios with production (3:2 cards, 21:9 hero)"
```

---

## Task 16: Confirm CharacterCard already 2:3

**Files:**
- Inspect: `frontend/components/CharacterCard.tsx` (no changes expected)

**Why:** CharacterCard is `minWidth: 240, minHeight: 360` = 2:3. The avatar image is set as `position: absolute, inset: 0, objectFit: cover` — meaning a 2:3 source image fills perfectly. A 1:1 avatar from the old pipeline would be cropped/stretched. Now that the new pipeline outputs 2:3, this card will look correct without changes.

- [x] **Step 16.1: Read CharacterCard.tsx and confirm**

Run: `cd frontend && head -100 components/CharacterCard.tsx`
Confirm: `minWidth: 240, minHeight: 360` and avatar `objectFit: cover` are both present.

No code change. But add a comment to mark intent:

Find the line `width: "100%", maxWidth: 320,` (around line 44). Above the `<img ... src={character.avatar!}` block, add a one-line comment:

```tsx
// avatar is generated at 2:3 vertical (matches this card's minHeight:minWidth ratio)
```

- [x] **Step 16.2: Visual check**

Start a game from the worlds detail page → role selection. Verify character cards display correctly with portrait images filling the card cleanly.

- [x] **Step 16.3: Commit (if comment added)**

```bash
git add frontend/components/CharacterCard.tsx
git commit -m "docs(character-card): note 2:3 avatar ratio matches card minHeight:minWidth"
```

---

## Task 17: PR 2 smoke test

**Why:** Full end-to-end visual confirmation before merge.

- [x] **Step 17.1: Run full create flow**

With backend (PR 1 merged or running against PR 1 branch) and frontend (PR 2 branch) both running, log in as admin and create a new world via the workshop. Watch the SSE stream complete.

- [x] **Step 17.2: Verify each surface**

Walk the surfaces and verify visual quality:
- ✅ Discover (`/discover`) — newly created world appears as 3:2 card with cinematic image
- ✅ Landing (`/`) — featured card shows cinematic image
- ✅ World detail (`/worlds/<id>`) — full-bleed hero (21:9 source, fills viewport on desktop)
- ✅ Start page (`/worlds/<id>/start`) — blurred background uses cover, foreground role cards show 2:3 portraits
- ✅ History (`/history`) — after starting a game, the history card shows 3:2 image
- ✅ Admin preview (`/admin/worlds/drafts/<id>`) — 3 preview tiles correct

- [x] **Step 17.3: Check at mobile viewport**

In Chrome DevTools, switch to iPhone SE (375px). Re-walk the surfaces. Especially:
- ✅ World detail hero is composed for 21:9 source → mobile center-crops to roughly 9:19, subject still visible
- ✅ Cards stack to 1-2 columns and remain 3:2

- [x] **Step 17.4: PR 2 ready**

Push and open PR 2 with title `feat(ui): align card ratios to 3:2 + drop poster_image references`.

---

# Self-review

**1. Spec coverage:**
- D1 (cards 3:2) → Task 14 ✅
- D2 (hero 21:9 + cover crop) → Tasks 4, 8 ✅
- D3 (VisualBrief) → Tasks 2, 3, 8, 10 ✅
- D4 (drop poster_image) → Tasks 6, 7, 11, 13 ✅
- D5 (avatar 2:3) → Tasks 5 (prompt), 8 (pipeline aspect_ratio="2:3"), 16 (FE confirmation) ✅
- M1 (keep cover_image / hero_image names) → Tasks 6, 7, 13 ✅
- M2 (skip data migration) → not implemented intentionally; documented in plan header
- M3 (two PRs) → PR 1 is Tasks 1-12, PR 2 is Tasks 13-17 ✅

**2. Placeholder scan:** One placeholder remains — Task 9.4 says "copy the closest existing pipeline-stage test pattern in this file and adapt". This is intentional because the pattern depends on existing fixtures we don't want to invent in the plan. Worker should pattern-match.

**3. Type consistency:**
- `WorldVisualBrief` / `CharacterVisualBrief` / `ScriptVisualBrief` — names consistent throughout
- `generate_world_visual_brief` / `generate_script_visual_brief` — consistent
- `crop_to_aspect_ratio(image_bytes, *, target_w, target_h)` — same signature in cropper file and pipeline call site
- `materialize_image_bytes(result)` — same signature
- `build_world_still_prompt(brief)` / `build_script_poster_prompt(world_brief, script_brief)` / `build_character_portrait_prompt(world_brief, *, character_name)` — consistent

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-10-image-pipeline-refactor.md`.

Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — I execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
