import asyncio
import json

import pytest

from llm.router import LLMRouter
from schemas.generation_strategy import ResearchArtifact
from services.world_creator_agent import WORLD_BASE_TOOL, WorldCreatorAgent, _collect_tool_output

pytestmark = pytest.mark.no_db


class DummyImageStorage:
    async def save(self, data: bytes, key: str) -> str:
        return f"/dummy/{key}"

    async def save_from_url(self, source_url: str, key: str) -> str:
        return f"/dummy/{key}"

    async def delete(self, key: str) -> None:
        return None


class DummyImageResult:
    def __init__(self, url: str = "https://example.com/image.png"):
        self.url = url
        self.has_url = True


class DummyImageGenerator:
    async def generate_image(self, prompt: str, aspect_ratio: str = "1:1") -> DummyImageResult:
        return DummyImageResult()


class FakeProvider:
    async def stream_with_tools(self, messages, tools, system=None, max_tokens=2048):
        tool_name = tools[0]["name"] if tools else ""
        content = messages[0]["content"] if messages else ""
        yield {"type": "tool_use", "name": tool_name, "input": self._payload(tool_name, content)}

    def _payload(self, tool_name: str, content: str) -> dict:
        if tool_name == "build_search_plan":
            return {"needs_search": True, "queries": ["测试查询"], "focuses": ["背景"]}
        if tool_name == "build_world_brief":
            return {"location_count_target": 5, "tension_count_target": 3, "npc_count_target": 6, "tone": "悬疑"}
        if tool_name == "build_character_brief":
            return {"count_target": 6, "relationship_density": "高", "faction_count": 2}
        if tool_name == "build_playable_brief":
            return {"playable_count_target": 5, "recommended_count_target": 1, "viewpoint_mix": ["调查者", "局内人"]}
        if tool_name == "build_script_brief":
            return {"event_count_target": 6, "ending_count_target": 3, "ending_mix": ["good", "bad", "timeout"]}
        if tool_name == "build_visual_brief":
            return {"cover_subject": "misty london", "style_tags": ["cinematic"], "negative_tags": ["text"]}
        if tool_name == "create_world_base":
            return {
                "name": "雾都",
                "description": "测试世界",
                "genre": "悬疑",
                "era": "1888年",
                "difficulty": 3,
                "estimated_time": "30-60分钟",
                "base_setting": "维多利亚时代的伦敦。",
                "free_setting": "暗流一\n暗流二",
                "locations": [{"name": "白教堂", "description": "雾气弥漫"}, {"name": "贝克街", "description": "侦探住所"}],
            }
        if tool_name == "create_characters":
            return {
                "world_characters": [
                    {"name": "福尔摩斯", "personality": "冷静敏锐", "secret": "已锁定嫌疑人", "knowledge": ["懂案情"], "schedule": {"上午": "贝克街"}, "initial_location": "贝克街"},
                    {"name": "记者", "personality": "消息灵通", "secret": "藏着录音", "knowledge": ["见过嫌疑人"], "schedule": {"夜晚": "白教堂"}, "initial_location": "白教堂"},
                ]
            }
        if tool_name == "select_playable":
            return {
                "playable_characters": [
                    {"name": "福尔摩斯", "description": "侦探", "abilities": ["推理"], "starting_inventory": ["手杖"]},
                    {"name": "记者", "description": "记者", "abilities": ["采访"], "starting_inventory": ["笔记本"]},
                ]
            }
        if tool_name == "create_script_base":
            return {
                "name": "白教堂疑案",
                "description": "调查连环杀人案",
                "script_setting": "凶手藏在警署内部。",
                "difficulty": 3,
                "estimated_time": "30-60分钟",
            }
        if tool_name == "create_events":
            return {
                "events": [
                    {
                        "name": "命案重现",
                        "trigger_type": "time",
                        "trigger_condition": {"time": "第1天·夜晚"},
                        "description": "新的命案发生",
                        "effects": {"new_clues": ["新的尸检线索"]},
                        "priority": 1,
                    }
                ],
                "clues": {"blood_note": "留有特殊墨水痕迹"},
            }
        if tool_name == "create_endings":
            return {
                "endings": [
                    {"ending_type": "good", "title": "抓住真凶", "description": "你揭开了谜团", "priority": 2},
                    {"ending_type": "bad", "title": "误判", "description": "真凶逃脱", "priority": 1},
                ]
            }
        if tool_name == "select_script_playable":
            return {
                "playable_characters": [
                    {"name": "福尔摩斯", "description": "侦探", "abilities": ["推理"], "starting_inventory": ["手杖"]}
                ]
            }
        if tool_name == "review_script_playable":
            return {
                "playable_characters": [
                    {"name": "福尔摩斯", "description": "侦探", "abilities": ["推理"], "starting_inventory": ["手杖"]}
                ],
                "adjusted": False,
                "reason": "",
            }
        return {}


class RetryJSONProvider:
    def __init__(self):
        self.calls: list[dict] = []

    async def stream_with_tools(self, messages, tools, system=None, max_tokens=2048):
        self.calls.append({"messages": messages, "tools": tools})
        if tools:
            return
        yield {
            "type": "text_delta",
            "text": json.dumps(
                {
                    "name": "雾都",
                    "description": "测试世界",
                    "genre": "悬疑",
                    "era": "1888年",
                    "difficulty": 3,
                    "estimated_time": "30-60分钟",
                    "base_setting": "维多利亚时代的伦敦。",
                    "free_setting": "暗流一\n暗流二",
                    "locations": [{"name": "白教堂", "description": "雾气弥漫"}],
                },
                ensure_ascii=False,
            ),
        }


class RecordingProvider(FakeProvider):
    def __init__(self):
        self.calls: list[dict] = []

    async def stream_with_tools(self, messages, tools, system=None, max_tokens=2048):
        self.calls.append(
            {
                "messages": messages,
                "tools": tools,
                "system": system,
            }
        )
        async for event in super().stream_with_tools(messages, tools, system=system, max_tokens=max_tokens):
            yield event


@pytest.mark.asyncio
async def test_create_world_uses_research_in_multiple_stages():
    router = LLMRouter(providers={"fake": FakeProvider()}, fallback_chain=["fake"])
    agent = WorldCreatorAgent(router, image_storage=DummyImageStorage())

    seen_stages: list[str] = []

    async def fake_collect(request):
        seen_stages.append(request.stage)
        return [
            ResearchArtifact(
                artifact_id=f"{request.stage}-1",
                query="测试查询",
                source="test",
                summary=f"{request.stage} artifact",
            )
        ]

    async def fake_summarize(request, artifacts):
        return f"{request.stage} summary"

    agent.research_broker.collect_artifacts = fake_collect
    agent.research_broker.summarize = fake_summarize

    events = [event async for event in agent.create_world("维多利亚伦敦", genre="悬疑", era="1888年")]

    assert "world_base" in seen_stages
    assert "characters" in seen_stages
    progress_codes = {(event["phase"], event["code"]) for event in events if event["type"] == "progress"}
    assert ("research", "searching") in progress_codes
    assert ("world_base", "brief_started") in progress_codes
    assert ("world_base", "brief_ready") in progress_codes
    assert any(event["type"] == "progress" and "message" in event for event in events)
    result = next(event for event in events if event["type"] == "result")
    assert result["name"] == "雾都"
    assert "hero_image" in result
    assert sum(1 for char in result["world_characters"] if char["playable"]) == 1


@pytest.mark.asyncio
async def test_create_script_uses_research_in_multiple_stages():
    router = LLMRouter(providers={"fake": FakeProvider()}, fallback_chain=["fake"])
    agent = WorldCreatorAgent(router, image_storage=DummyImageStorage())

    seen_stages: list[str] = []

    async def fake_collect(request):
        seen_stages.append(request.stage)
        return [
            ResearchArtifact(
                artifact_id=f"{request.stage}-1",
                query="测试查询",
                source="test",
                summary=f"{request.stage} artifact",
            )
        ]

    async def fake_summarize(request, artifacts):
        return f"{request.stage} summary"

    agent.research_broker.collect_artifacts = fake_collect
    agent.research_broker.summarize = fake_summarize

    world_data = {
        "name": "雾都",
        "base_setting": "维多利亚时代的伦敦。",
        "locations": [{"name": "白教堂", "description": "雾气弥漫"}],
        "world_characters": [{"name": "福尔摩斯", "personality": "冷静敏锐", "secret": "已锁定嫌疑人", "initial_location": "白教堂"}],
    }

    events = [event async for event in agent.create_script(world_data, "白教堂连环杀人案")]

    assert "script_base" in seen_stages
    assert "events" in seen_stages
    progress_codes = {(event["phase"], event["code"]) for event in events if event["type"] == "progress"}
    assert ("research", "summarizing") in progress_codes
    assert ("script_base", "brief_started") in progress_codes
    assert ("script_base", "brief_ready") in progress_codes
    assert ("playable", "brief_started") in progress_codes
    result = next(event for event in events if event["type"] == "result")
    assert result["name"] == "白教堂疑案"


@pytest.mark.asyncio
async def test_create_script_includes_existing_script_references_in_prompts():
    provider = RecordingProvider()
    router = LLMRouter(providers={"fake": provider}, fallback_chain=["fake"])
    agent = WorldCreatorAgent(router, image_storage=DummyImageStorage())

    world_data = {
        "name": "雾都",
        "description": "被煤烟、雾和传闻吞没的伦敦街区。",
        "genre": "悬疑",
        "era": "1888年",
        "base_setting": "维多利亚时代的伦敦。",
        "locations": [{"name": "白教堂", "description": "雾气弥漫"}],
        "world_characters": [{"name": "福尔摩斯", "personality": "冷静敏锐", "secret": "已锁定嫌疑人", "initial_location": "白教堂"}],
        "existing_scripts": [
            {
                "name": "白教堂疑案",
                "description": "围绕连环杀人案展开调查",
                "script_setting": "真凶躲在警署内部。",
                "event_names": ["命案重现", "河岸追踪"],
                "ending_types": ["good", "bad"],
            }
        ],
    }

    _ = [event async for event in agent.create_script(world_data, "新的雨夜谋杀案")]

    script_base_prompt = next(
        call["messages"][0]["content"]
        for call in provider.calls
        if call["tools"] and call["tools"][0]["name"] == "create_script_base"
    )
    events_prompt = next(
        call["messages"][0]["content"]
        for call in provider.calls
        if call["tools"] and call["tools"][0]["name"] == "create_events"
    )
    endings_prompt = next(
        call["messages"][0]["content"]
        for call in provider.calls
        if call["tools"] and call["tools"][0]["name"] == "create_endings"
    )

    for prompt in (script_base_prompt, events_prompt, endings_prompt):
        assert "白教堂疑案" in prompt
        assert "避免重复" in prompt


@pytest.mark.asyncio
async def test_create_script_runs_playable_branch_in_parallel_with_events_branch():
    router = LLMRouter(providers={"fake": FakeProvider()}, fallback_chain=["fake"])
    agent = WorldCreatorAgent(router, image_storage=DummyImageStorage())

    class NoSearchPlan:
        needs_search = False
        queries: list[str] = []
        focuses: list[str] = []
        source_bias = "balanced"
        reference_mode = "balanced"
        freshness_sensitive = False

    async def no_search_plan(**kwargs):
        return NoSearchPlan()

    async def script_brief(*args, **kwargs):
        return FakeProvider()._payload("build_script_brief", "")

    async def script_base(*args, **kwargs):
        return FakeProvider()._payload("create_script_base", "")

    async def slow_events(*args, **kwargs):
        await asyncio.sleep(0.05)
        return FakeProvider()._payload("create_events", "")

    async def slow_endings(*args, **kwargs):
        await asyncio.sleep(0.05)
        return FakeProvider()._payload("create_endings", "")

    async def fast_playable_brief(*args, **kwargs):
        await asyncio.sleep(0.005)
        return FakeProvider()._payload("build_playable_brief", "")

    async def fast_select_script_playable(*args, **kwargs):
        await asyncio.sleep(0.005)
        return FakeProvider()._payload("select_script_playable", "")["playable_characters"]

    async def review_script_playable(*args, **kwargs):
        return FakeProvider()._payload("review_script_playable", "")["playable_characters"], False

    agent.strategy_service.build_search_plan = no_search_plan
    agent.strategy_service.build_script_brief = script_brief
    agent._generate_script_base = script_base
    agent._generate_events = slow_events
    agent._generate_endings = slow_endings
    agent.strategy_service.build_playable_brief = fast_playable_brief
    agent._select_script_playable = fast_select_script_playable
    agent._review_script_playable = review_script_playable

    world_data = {
        "name": "雾都",
        "description": "被煤烟、雾和传闻吞没的伦敦街区。",
        "genre": "悬疑",
        "era": "1888年",
        "base_setting": "维多利亚时代的伦敦。",
        "locations": [{"name": "白教堂", "description": "雾气弥漫"}],
        "world_characters": [{"name": "福尔摩斯", "personality": "冷静敏锐", "secret": "已锁定嫌疑人", "initial_location": "白教堂"}],
    }

    events = [event async for event in agent.create_script(world_data, "新的雨夜谋杀案")]
    progress_codes = [
        (event["phase"], event["code"])
        for event in events
        if event["type"] == "progress"
    ]

    assert ("playable", "started") in progress_codes
    assert ("endings", "completed") in progress_codes
    assert progress_codes.index(("playable", "started")) < progress_codes.index(("endings", "completed"))


@pytest.mark.asyncio
async def test_create_world_research_policy_skips_playable_but_keeps_external_stages_when_signals_exist():
    router = LLMRouter(providers={"fake": FakeProvider()}, fallback_chain=["fake"])
    agent = WorldCreatorAgent(
        router,
        image_generator=DummyImageGenerator(),
        image_storage=DummyImageStorage(),
    )

    class NoSearchPlan:
        needs_search = False
        queries: list[str] = []
        focuses: list[str] = []
        source_bias = "balanced"
        reference_mode = "balanced"
        freshness_sensitive = False

    seen_stages: list[str] = []

    async def record_search_plan(stage: str, goal: str, context: str):
        seen_stages.append(stage)
        return NoSearchPlan()

    agent.strategy_service.build_search_plan = record_search_plan

    _ = [
        event
        async for event in agent.create_world(
            "参考《黑镜》气质的近未来都市实验场",
            genre="科幻",
            era="2049年",
        )
    ]

    assert "world_base" in seen_stages
    assert "characters" in seen_stages
    assert "images" in seen_stages
    assert "playable" not in seen_stages


@pytest.mark.asyncio
async def test_create_script_research_policy_skips_playable_and_endings_without_consequence_signals():
    router = LLMRouter(providers={"fake": FakeProvider()}, fallback_chain=["fake"])
    agent = WorldCreatorAgent(router, image_storage=DummyImageStorage())

    class NoSearchPlan:
        needs_search = False
        queries: list[str] = []
        focuses: list[str] = []
        source_bias = "balanced"
        reference_mode = "balanced"
        freshness_sensitive = False

    seen_stages: list[str] = []

    async def record_search_plan(stage: str, goal: str, context: str):
        seen_stages.append(stage)
        return NoSearchPlan()

    agent.strategy_service.build_search_plan = record_search_plan

    world_data = {
        "name": "雾都",
        "description": "近未来港城。",
        "genre": "科幻",
        "era": "2049年",
        "base_setting": "一座由记忆取证系统维持秩序的架空都市。",
        "locations": [{"name": "白教堂", "description": "雾气弥漫"}],
        "world_characters": [{"name": "福尔摩斯", "personality": "冷静敏锐", "secret": "已锁定嫌疑人", "initial_location": "白教堂"}],
    }

    _ = [event async for event in agent.create_script(world_data, "参考《黑镜》气质的脑机接口谋杀案")]

    assert "script_base" in seen_stages
    assert "events" in seen_stages
    assert "endings" not in seen_stages
    assert "playable" not in seen_stages


@pytest.mark.asyncio
async def test_create_script_cancels_playable_branch_after_fatal_events_failure():
    router = LLMRouter(providers={"fake": FakeProvider()}, fallback_chain=["fake"])
    agent = WorldCreatorAgent(router, image_storage=DummyImageStorage())

    class NoSearchPlan:
        needs_search = False
        queries: list[str] = []
        focuses: list[str] = []
        source_bias = "balanced"
        reference_mode = "balanced"
        freshness_sensitive = False

    async def no_search_plan(**kwargs):
        return NoSearchPlan()

    async def script_brief(*args, **kwargs):
        return FakeProvider()._payload("build_script_brief", "")

    async def script_base(*args, **kwargs):
        return FakeProvider()._payload("create_script_base", "")

    async def failing_events(*args, **kwargs):
        await asyncio.sleep(0.01)
        raise RuntimeError("events boom")

    async def fast_playable_brief(*args, **kwargs):
        return FakeProvider()._payload("build_playable_brief", "")

    async def slow_select_script_playable(*args, **kwargs):
        await asyncio.sleep(0.2)
        return FakeProvider()._payload("select_script_playable", "")["playable_characters"]

    agent.strategy_service.build_search_plan = no_search_plan
    agent.strategy_service.build_script_brief = script_brief
    agent._generate_script_base = script_base
    agent._generate_events = failing_events
    agent.strategy_service.build_playable_brief = fast_playable_brief
    agent._select_script_playable = slow_select_script_playable

    world_data = {
        "name": "雾都",
        "description": "被煤烟、雾和传闻吞没的伦敦街区。",
        "genre": "悬疑",
        "era": "1888年",
        "base_setting": "维多利亚时代的伦敦。",
        "locations": [{"name": "白教堂", "description": "雾气弥漫"}],
        "world_characters": [{"name": "福尔摩斯", "personality": "冷静敏锐", "secret": "已锁定嫌疑人", "initial_location": "白教堂"}],
    }

    started = asyncio.get_running_loop().time()
    events = [event async for event in agent.create_script(world_data, "新的雨夜谋杀案")]
    elapsed = asyncio.get_running_loop().time() - started

    result = next(event for event in events if event["type"] == "result")
    progress_codes = [
        (event["phase"], event["code"])
        for event in events
        if event["type"] == "progress"
    ]
    assert result["partial"] is True
    assert elapsed < 0.12
    assert ("playable", "completed") not in progress_codes


@pytest.mark.asyncio
async def test_create_world_runs_image_prep_in_parallel_with_playable():
    router = LLMRouter(providers={"fake": FakeProvider()}, fallback_chain=["fake"])
    agent = WorldCreatorAgent(
        router,
        image_generator=DummyImageGenerator(),
        image_storage=DummyImageStorage(),
    )

    class NoSearchPlan:
        needs_search = False
        queries: list[str] = []
        focuses: list[str] = []
        source_bias = "balanced"
        reference_mode = "balanced"
        freshness_sensitive = False

    async def no_search_plan(**kwargs):
        return NoSearchPlan()

    async def slow_visual_brief(*args, **kwargs):
        await asyncio.sleep(0.05)
        return FakeProvider()._payload("build_visual_brief", "")

    async def slow_select_playable(*args, **kwargs):
        await asyncio.sleep(0.05)
        return FakeProvider()._payload("select_playable", "")["playable_characters"]

    async def immediate_world_images(*args, **kwargs):
        return {"cover": "", "poster": "", "hero": "", "avatars": {}}

    agent.strategy_service.build_search_plan = no_search_plan
    agent.strategy_service.build_world_brief = lambda *args, **kwargs: asyncio.sleep(0, result=FakeProvider()._payload("build_world_brief", ""))
    agent._generate_world_base = lambda *args, **kwargs: asyncio.sleep(0, result=FakeProvider()._payload("create_world_base", ""))
    agent.strategy_service.build_character_brief = lambda *args, **kwargs: asyncio.sleep(0, result=FakeProvider()._payload("build_character_brief", ""))
    agent._generate_characters = lambda *args, **kwargs: asyncio.sleep(0, result=FakeProvider()._payload("create_characters", "")["world_characters"])
    agent.strategy_service.build_playable_brief = lambda *args, **kwargs: asyncio.sleep(0, result=FakeProvider()._payload("build_playable_brief", ""))
    agent._select_playable = slow_select_playable
    agent.strategy_service.build_visual_brief = slow_visual_brief
    agent._generate_world_images = immediate_world_images

    started = asyncio.get_running_loop().time()
    events = [event async for event in agent.create_world("架空迷雾港城", genre="悬疑", era="")]
    elapsed = asyncio.get_running_loop().time() - started

    progress_codes = [
        (event["phase"], event["code"])
        for event in events
        if event["type"] == "progress"
    ]

    assert ("images", "brief_started") in progress_codes
    assert ("playable", "completed") in progress_codes
    assert progress_codes.index(("images", "brief_started")) < progress_codes.index(("playable", "completed"))
    assert elapsed < 0.1


@pytest.mark.asyncio
async def test_create_world_critic_gate_repairs_playable_before_images():
    router = LLMRouter(providers={"fake": FakeProvider()}, fallback_chain=["fake"])
    agent = WorldCreatorAgent(
        router,
        image_generator=DummyImageGenerator(),
        image_storage=DummyImageStorage(),
    )

    class NoSearchPlan:
        needs_search = False
        queries: list[str] = []
        focuses: list[str] = []
        source_bias = "balanced"
        reference_mode = "balanced"
        freshness_sensitive = False

    playable_calls = 0

    async def no_search_plan(**kwargs):
        return NoSearchPlan()

    async def select_playable(*args, **kwargs):
        nonlocal playable_calls
        playable_calls += 1
        if playable_calls == 1:
            return [
                {"name": "福尔摩斯", "description": "侦探", "abilities": ["推理"], "starting_inventory": ["手杖"]},
            ]
        return [
            {"name": "福尔摩斯", "description": "侦探", "abilities": ["推理"], "starting_inventory": ["手杖"]},
            {"name": "记者", "description": "记者", "abilities": ["采访"], "starting_inventory": ["笔记本"]},
        ]

    async def review_world_generation(*args, **kwargs):
        return {
            "passed": False,
            "overall_score": 62,
            "issues": ["可玩视角过少，体验差异不足"],
            "repair_targets": ["playable"],
            "repair_brief": "补一个与侦探视角信息差明显不同的第二核心角色。",
        }

    async def immediate_world_images(*args, **kwargs):
        return {"cover": "", "poster": "", "hero": "", "avatars": {}}

    agent.strategy_service.build_search_plan = no_search_plan
    agent.strategy_service.build_world_brief = lambda *args, **kwargs: asyncio.sleep(0, result=FakeProvider()._payload("build_world_brief", ""))
    agent._generate_world_base = lambda *args, **kwargs: asyncio.sleep(0, result=FakeProvider()._payload("create_world_base", ""))
    agent.strategy_service.build_character_brief = lambda *args, **kwargs: asyncio.sleep(0, result=FakeProvider()._payload("build_character_brief", ""))
    agent._generate_characters = lambda *args, **kwargs: asyncio.sleep(0, result=FakeProvider()._payload("create_characters", "")["world_characters"])
    agent.strategy_service.build_playable_brief = lambda *args, **kwargs: asyncio.sleep(0, result=FakeProvider()._payload("build_playable_brief", ""))
    agent._select_playable = select_playable
    agent._review_world_generation = review_world_generation
    agent.strategy_service.build_visual_brief = lambda *args, **kwargs: asyncio.sleep(0, result=FakeProvider()._payload("build_visual_brief", ""))
    agent._generate_world_images = immediate_world_images

    events = [event async for event in agent.create_world("架空迷雾港城", genre="悬疑", era="")]
    result = next(event for event in events if event["type"] == "result")
    progress_codes = [
        (event["phase"], event["code"])
        for event in events
        if event["type"] == "progress"
    ]

    assert playable_calls == 2
    assert [char["name"] for char in result["world_characters"] if char["playable"]] == ["福尔摩斯", "记者"]
    assert ("critic", "started") in progress_codes
    assert ("critic", "repair_started") in progress_codes


@pytest.mark.asyncio
async def test_create_script_critic_gate_repairs_endings_without_rerunning_whole_script():
    router = LLMRouter(providers={"fake": FakeProvider()}, fallback_chain=["fake"])
    agent = WorldCreatorAgent(router, image_storage=DummyImageStorage())

    class NoSearchPlan:
        needs_search = False
        queries: list[str] = []
        focuses: list[str] = []
        source_bias = "balanced"
        reference_mode = "balanced"
        freshness_sensitive = False

    script_base_calls = 0
    events_calls = 0
    endings_calls = 0

    async def no_search_plan(**kwargs):
        return NoSearchPlan()

    async def script_brief(*args, **kwargs):
        return FakeProvider()._payload("build_script_brief", "")

    async def script_base(*args, **kwargs):
        nonlocal script_base_calls
        script_base_calls += 1
        return FakeProvider()._payload("create_script_base", "")

    async def generate_events(*args, **kwargs):
        nonlocal events_calls
        events_calls += 1
        return FakeProvider()._payload("create_events", "")

    async def generate_endings(*args, **kwargs):
        nonlocal endings_calls
        endings_calls += 1
        if endings_calls == 1:
            return {
                "endings": [
                    {"ending_type": "good", "title": "抓住真凶", "description": "你揭开了谜团", "priority": 2},
                ]
            }
        return FakeProvider()._payload("create_endings", "")

    async def review_script_generation(*args, **kwargs):
        return {
            "passed": False,
            "overall_score": 58,
            "issues": ["结局过少，收束差异不足"],
            "repair_targets": ["endings"],
            "repair_brief": "补一个失败结局，并与成功结局形成明显的收束差异。",
        }

    async def review_script_playable(*args, **kwargs):
        return FakeProvider()._payload("review_script_playable", "")["playable_characters"], False

    agent.strategy_service.build_search_plan = no_search_plan
    agent.strategy_service.build_script_brief = script_brief
    agent._generate_script_base = script_base
    agent._generate_events = generate_events
    agent._generate_endings = generate_endings
    agent.strategy_service.build_playable_brief = lambda *args, **kwargs: asyncio.sleep(0, result=FakeProvider()._payload("build_playable_brief", ""))
    agent._select_script_playable = lambda *args, **kwargs: asyncio.sleep(0, result=FakeProvider()._payload("select_script_playable", "")["playable_characters"])
    agent._review_script_playable = review_script_playable
    agent._review_script_generation = review_script_generation

    world_data = {
        "name": "雾都",
        "description": "被煤烟、雾和传闻吞没的伦敦街区。",
        "genre": "悬疑",
        "era": "1888年",
        "base_setting": "维多利亚时代的伦敦。",
        "locations": [{"name": "白教堂", "description": "雾气弥漫"}],
        "world_characters": [{"name": "福尔摩斯", "personality": "冷静敏锐", "secret": "已锁定嫌疑人", "initial_location": "白教堂"}],
    }

    events = [event async for event in agent.create_script(world_data, "新的雨夜谋杀案")]
    result = next(event for event in events if event["type"] == "result")
    progress_codes = [
        (event["phase"], event["code"])
        for event in events
        if event["type"] == "progress"
    ]

    assert script_base_calls == 1
    assert events_calls == 1
    assert endings_calls == 2
    assert len(result["endings"]) == 2
    assert ("critic", "started") in progress_codes
    assert ("critic", "repair_started") in progress_codes


@pytest.mark.asyncio
async def test_collect_tool_output_retries_with_plain_json_when_tool_call_is_empty():
    provider = RetryJSONProvider()
    router = LLMRouter(providers={"fake": provider}, fallback_chain=["fake"])

    result = await _collect_tool_output(
        router,
        messages=[{"role": "user", "content": "生成世界框架"}],
        tools=[WORLD_BASE_TOOL],
        system="你必须返回结构化数据。",
        max_tokens=1024,
    )

    assert result is not None
    assert result["name"] == "雾都"
    assert [bool(call["tools"]) for call in provider.calls] == [True, False]


@pytest.mark.asyncio
async def test_create_world_emits_progress_pulses_for_slow_steps():
    router = LLMRouter(providers={"fake": FakeProvider()}, fallback_chain=["fake"])
    agent = WorldCreatorAgent(router, image_storage=DummyImageStorage())
    agent.progress_pulse_delay = 0.01

    class SlowPlan:
        needs_search = True
        queries = ["测试查询"]
        focuses = ["背景"]
        source_bias = "balanced"
        reference_mode = "balanced"
        freshness_sensitive = False

    async def slow_search_plan(**kwargs):
        await asyncio.sleep(0.02)
        return SlowPlan()

    async def fake_collect(request):
        await asyncio.sleep(0.02)
        return [
            ResearchArtifact(
                artifact_id=f"{request.stage}-1",
                query="测试查询",
                source="test",
                summary=f"{request.stage} artifact",
            )
        ]

    async def slow_summarize(request, artifacts):
        await asyncio.sleep(0.02)
        return f"{request.stage} summary"

    async def slow_world_brief(*args, **kwargs):
        await asyncio.sleep(0.02)
        return FakeProvider()._payload("build_world_brief", "")

    async def slow_world_base(*args, **kwargs):
        await asyncio.sleep(0.02)
        return FakeProvider()._payload("create_world_base", "")

    agent.strategy_service.build_search_plan = slow_search_plan
    agent.research_broker.collect_artifacts = fake_collect
    agent.research_broker.summarize = slow_summarize
    agent.strategy_service.build_world_brief = slow_world_brief
    agent._generate_world_base = slow_world_base
    agent.strategy_service.build_character_brief = lambda *args, **kwargs: asyncio.sleep(0, result=FakeProvider()._payload("build_character_brief", ""))
    agent._generate_characters = lambda *args, **kwargs: asyncio.sleep(0, result=FakeProvider()._payload("create_characters", "")["world_characters"])
    agent.strategy_service.build_playable_brief = lambda *args, **kwargs: asyncio.sleep(0, result=FakeProvider()._payload("build_playable_brief", ""))
    agent._select_playable = lambda *args, **kwargs: asyncio.sleep(0, result=FakeProvider()._payload("select_playable", "")["playable_characters"])

    events = [event async for event in agent.create_world("维多利亚伦敦", genre="悬疑", era="1888年")]
    progress_codes = {(event["phase"], event["code"]) for event in events if event["type"] == "progress"}

    assert ("research", "analysis_pulse") in progress_codes
    assert ("research", "searching_pulse") in progress_codes
    assert ("research", "summarizing_pulse") in progress_codes
    assert ("world_base", "brief_pulse") in progress_codes
    assert ("world_base", "drafting_pulse") in progress_codes
