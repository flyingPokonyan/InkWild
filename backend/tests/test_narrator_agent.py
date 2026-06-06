import pytest

from engine.narrator_agent import NarratorAgent


class FakeRouter:
    def __init__(self, events):
        self.events = events
        self.calls = []

    async def stream_with_tools(self, messages, tools, system=None, max_tokens=2048):
        self.calls.append({
            "messages": messages, "tools": tools, "system": system,
            "max_tokens": max_tokens,
        })
        for event in self.events:
            yield event


@pytest.mark.asyncio
async def test_narrator_agent_streams_text_chunks_and_includes_author_note():
    router = FakeRouter(
        events=[
            {"type": "text_delta", "text": "第一段。"},
            {"type": "text_delta", "text": "第二段。"},
            {"type": "usage", "input_tokens": 8, "output_tokens": 4},
        ]
    )
    agent = NarratorAgent(router)

    events = []
    async for event in agent.stream(
        scene_direction="茶摊外起了风。",
        npc_dialogues={"王福": "你最好别多问。"},
        recent_messages=[{"role": "user", "content": "我去茶摊"}],
        authors_note="保持悬疑感。",
    ):
        events.append(event)

    assert events == router.events
    assert "Author's Note" in router.calls[0]["system"]
    assert "保持悬疑感。" in router.calls[0]["system"]
