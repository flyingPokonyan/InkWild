from typing import AsyncIterator

import structlog

from engine.content_filter import check_input, check_output
from engine.context_builder import UPDATE_STATE_TOOL, build_messages, build_system_prompt
from engine.ending_system import check_hard_endings, merge_ai_ending_judgment
from engine.event_system import apply_event_effects, check_events
from engine.state_manager import GameState, apply_state_updates
from llm.router import LLMRouter

logger = structlog.get_logger()


class WorldEngine:
    def __init__(self, llm_router: LLMRouter):
        self.llm_router = llm_router

    async def process_action(
        self,
        action_text: str,
        game_state: GameState,
        recent_messages: list[dict],
        context_summary: str | None,
        world_data: dict,
        game_mode: str,
    ) -> AsyncIterator[dict]:
        filter_result = check_input(action_text)
        if not filter_result.is_safe:
            yield {"type": "error", "code": 40001, "message": filter_result.reason}
            return

        system = build_system_prompt(
            base_setting=world_data["base_setting"],
            script_setting=world_data.get("script_setting", ""),
            npc_descriptions=world_data["npc_descriptions"],
            ending_conditions=world_data.get("ending_conditions", ""),
            game_mode=game_mode,
        )
        messages = build_messages(game_state, recent_messages, context_summary, action_text)

        narrative_parts: list[str] = []
        tool_input = None
        usage_data = None

        async for event in self.llm_router.stream_with_tools(
            messages=messages,
            tools=[UPDATE_STATE_TOOL],
            system=system,
        ):
            if event["type"] == "text_delta":
                narrative_parts.append(event["text"])
                yield {"type": "narrative", "text": event["text"]}
            elif event["type"] == "tool_use" and event["name"] == "update_game_state":
                tool_input = event["input"]
            elif event["type"] == "usage":
                usage_data = event

        full_narrative = "".join(narrative_parts)
        output_check = check_output(full_narrative)
        if not output_check.is_safe:
            logger.warning("output_filtered", reason=output_check.reason)

        if tool_input:
            new_state = apply_state_updates(game_state, tool_input)
            quick_actions = tool_input.get("quick_actions", [])

            triggered = check_events(world_data.get("events", []), new_state, game_mode)
            for event in triggered:
                new_state = apply_event_effects(new_state, event)

            ending = None
            hard_ending = check_hard_endings(world_data.get("endings", []), new_state)
            if hard_ending:
                ending = hard_ending
            elif ai_ending := tool_input.get("ending_triggered"):
                ending = merge_ai_ending_judgment(world_data.get("endings", []), ai_ending)

            yield {
                "type": "state_update",
                "game_state": new_state.to_dict(),
                "quick_actions": quick_actions,
                "triggered_events": [event["name"] for event in triggered],
            }

            if ending:
                yield {
                    "type": "ending",
                    "ending_type": ending["ending_type"],
                    "title": ending["title"],
                }

            yield {"type": "done", "new_state": new_state, "usage": usage_data}
        else:
            logger.warning("no_tool_call")
            yield {
                "type": "state_update",
                "game_state": game_state.to_dict(),
                "quick_actions": ["继续探索", "和周围的人聊聊", "查看环境"],
            }
            yield {"type": "done", "new_state": game_state, "usage": usage_data}
