import type { ScriptDraftPayload, WorldDraftPayload } from "./types";

export function linesToArray(value: string): string[] {
  return value
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean);
}

export function arrayToLines(items: string[]): string {
  return items.join("\n");
}

export function parseJsonInput<T>(value: string, fallback: T): T {
  const trimmed = value.trim();
  if (!trimmed) return fallback;
  try {
    return JSON.parse(trimmed) as T;
  } catch {
    return fallback;
  }
}

export function formatJsonInput(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

export function createEmptyWorldPayload(): WorldDraftPayload {
  return {
    name: "",
    description: "",
    genre: "",
    era: "",
    difficulty: 3,
    estimated_time: "30-60 min",
    base_setting: "",
    free_setting: "",
    locations: [],
    world_characters: [],
  };
}

export function createEmptyScriptPayload(): ScriptDraftPayload {
  return {
    name: "",
    description: "",
    difficulty: 3,
    estimated_time: "30-60 min",
    script_setting: "",
    events: [],
    clues: {},
    endings: [],
    playable_character_ids: [],
  };
}
