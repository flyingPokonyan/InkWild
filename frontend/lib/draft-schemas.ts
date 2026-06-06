import { z } from "zod";

import type {
  EndingDraft,
  EventDraft,
  LocationDraft,
  ScriptDraftPayload,
  WorldCharacterDraft,
  WorldDraftPayload,
} from "./types";

export const TIME_SLOTS = ["上午", "下午", "傍晚", "夜晚", "深夜"] as const;
export type TimeSlot = (typeof TIME_SLOTS)[number];

export const TRIGGER_TYPES = [
  "time",
  "clue",
  "location",
  "clue_count",
  "rounds_without_progress",
] as const;
export type TriggerType = (typeof TRIGGER_TYPES)[number];

export const ENDING_TYPES = ["good", "normal", "bad", "hidden", "timeout"] as const;
export type EndingType = (typeof ENDING_TYPES)[number];

export const KNOWN_EFFECT_KEYS = [
  "give_clue",
  "move_npc",
  "unlock_location",
  "set_flag",
] as const;
export type EffectKey = (typeof KNOWN_EFFECT_KEYS)[number];

const jsonRecord = z.record(z.string(), z.unknown());

const locationSchema: z.ZodType<LocationDraft> = z.object({
  name: z.string(),
  description: z.string(),
});

const worldCharacterSchema: z.ZodType<WorldCharacterDraft> = z.object({
  name: z.string(),
  personality: z.string(),
  secret: z.string().nullable().optional(),
  knowledge: z.array(z.string()),
  schedule: z.record(z.string(), z.string()),
  initial_location: z.string(),
  playable: z.boolean(),
  description: z.string().nullable().optional(),
  abilities: z.array(z.string()),
  starting_inventory: z.array(z.string()),
  avatar: z.string().nullable().optional(),
});

export const worldDraftSchema: z.ZodType<WorldDraftPayload> = z.object({
  name: z.string(),
  description: z.string(),
  genre: z.string(),
  era: z.string(),
  difficulty: z.number().int().min(1).max(5),
  estimated_time: z.string(),
  base_setting: z.string(),
  free_setting: z.string(),
  locations: z.array(locationSchema),
  world_characters: z.array(worldCharacterSchema),
  cover_image: z.string().nullable().optional(),
  hero_image: z.string().nullable().optional(),
});

const eventSchema: z.ZodType<EventDraft> = z.object({
  name: z.string(),
  trigger_type: z.string(),
  trigger_condition: jsonRecord,
  description: z.string(),
  effects: jsonRecord,
  priority: z.number().int().optional(),
});

const endingSchema: z.ZodType<EndingDraft> = z.object({
  ending_type: z.string(),
  title: z.string(),
  description: z.string(),
  hard_conditions: jsonRecord.nullable().optional(),
  soft_conditions: z.string().nullable().optional(),
  priority: z.number().int().optional(),
});

export const scriptDraftSchema: z.ZodType<ScriptDraftPayload> = z.object({
  name: z.string(),
  description: z.string(),
  difficulty: z.number().int().min(1).max(5),
  estimated_time: z.string(),
  script_setting: z.string(),
  events: z.array(eventSchema),
  clues: jsonRecord,
  endings: z.array(endingSchema),
  cover_image: z.string().nullable().optional(),
  playable_character_ids: z.array(z.string()).default([]),
});

// ------ defaults / factories ------

export function emptyLocation(): LocationDraft {
  return { name: "", description: "" };
}

export function emptyNpc(): WorldCharacterDraft {
  return {
    name: "",
    personality: "",
    secret: "",
    knowledge: [],
    schedule: {},
    initial_location: "",
    playable: false,
    description: null,
    abilities: [],
    starting_inventory: [],
    avatar: null,
  };
}

export function emptyPlayable(): WorldCharacterDraft {
  return {
    name: "",
    personality: "",
    secret: null,
    knowledge: [],
    schedule: {},
    initial_location: "",
    playable: true,
    description: "",
    abilities: [],
    starting_inventory: [],
    avatar: null,
  };
}

export function emptyEvent(): EventDraft {
  return {
    name: "",
    trigger_type: "time",
    trigger_condition: {},
    description: "",
    effects: {},
    priority: 0,
  };
}

export function emptyEnding(): EndingDraft {
  return {
    ending_type: "normal",
    title: "",
    description: "",
    hard_conditions: null,
    soft_conditions: "",
    priority: 0,
  };
}

// ------ trigger condition helpers ------
// Each known trigger_type has a canonical shape. The structured form uses these
// to render dedicated UI; trigger_condition itself stays a free-form record so
// older payloads keep working.

export function defaultTriggerCondition(type: string): Record<string, unknown> {
  switch (type as TriggerType) {
    case "time":
      return { day: 1, slot: TIME_SLOTS[0] };
    case "clue":
      return { clue_id: "" };
    case "location":
      return { location: "" };
    case "clue_count":
      return { count: 1 };
    case "rounds_without_progress":
      return { rounds: 3 };
    default:
      return {};
  }
}

export function isKnownTriggerType(value: string): value is TriggerType {
  return (TRIGGER_TYPES as readonly string[]).includes(value);
}

export function isKnownEndingType(value: string): value is EndingType {
  return (ENDING_TYPES as readonly string[]).includes(value);
}
