import pytest

from engine.npc_agent import NPCAgent


class FakeRouter:
    def __init__(self, events):
        self.events = events
        self.calls = []

    async def stream_with_tools(self, messages, tools, system=None):
        self.calls.append({"messages": messages, "tools": tools, "system": system})
        for event in self.events:
            yield event


@pytest.mark.asyncio
async def test_npc_agent_returns_dialogue():
    router = FakeRouter(
        events=[
            {"type": "text_delta", "text": "你最好别多问。"},
            {"type": "text_delta", "text": "这件事很危险。"},
            {"type": "usage", "input_tokens": 20, "output_tokens": 10},
        ]
    )
    agent = NPCAgent(router)

    result = await agent.run(
        npc_name="王福",
        npc_personality="忠厚寡言",
        npc_secret="他知道遗嘱被改过。",
        instruction="试探玩家的来意。",
        recent_messages=[{"role": "user", "content": "你知道什么？"}],
    )

    assert result.npc_name == "王福"
    assert result.dialogue == "你最好别多问。这件事很危险。"
    assert result.usage == {"type": "usage", "input_tokens": 20, "output_tokens": 10}
    assert router.calls[0]["tools"] == []
    assert router.calls[0]["messages"][-1]["content"] == "导演指令：试探玩家的来意。"


@pytest.mark.asyncio
async def test_npc_agent_handles_empty_response():
    router = FakeRouter(events=[])
    agent = NPCAgent(router)

    result = await agent.run(
        npc_name="王福",
        npc_personality="忠厚寡言",
        npc_secret="他知道遗嘱被改过。",
        instruction="试探玩家的来意。",
        recent_messages=[],
    )

    assert result.npc_name == "王福"
    assert result.dialogue == ""
    assert result.usage is None
