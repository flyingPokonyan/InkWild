import type { ChatMessage } from "./types";

export type MessageTone = "narrator" | "player";

export function getMessageTone(role: ChatMessage["role"]): MessageTone {
  return role === "user" ? "player" : "narrator";
}
