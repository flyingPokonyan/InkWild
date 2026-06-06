import type { ChatMessage, GameSessionDetail } from "./types";

function toChatRole(role: string): ChatMessage["role"] {
  return role === "assistant" ? "narrator" : "user";
}

function isInternalOpeningPrompt(role: string, content: string): boolean {
  return role === "user"
    && content.startsWith("游戏开始。玩家扮演")
    && content.includes("请描写开场场景");
}

function toTimestamp(value: string, index: number): number {
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? index : parsed;
}

export function buildHydratedSessionState(detail: GameSessionDetail) {
    return {
      sessionId: detail.session_id,
      gameState: detail.game_state,
    messages: detail.messages
      .filter((message) => !isInternalOpeningPrompt(message.role, message.content))
      .map((message, index) => ({
        id: `history-${index + 1}`,
        role: toChatRole(message.role),
        content: message.content,
        timestamp: toTimestamp(message.created_at, index),
      })),
    quickActions: ["继续观察", "和周围的人聊聊", "检查线索", "四处走走"],
    error: null,
    ending: null,
    characterName: detail.character_name,
    characterDesc: detail.character_description,
    characterAbilities: detail.character_abilities,
    worldName: detail.world_name,
    mode: detail.mode || "script",
    scriptType: detail.script_type || "mystery",
  };
}
