import assert from "node:assert/strict";

import { buildHydratedSessionState } from "./session-detail.ts";

test("buildHydratedSessionState restores messages and metadata from session detail", () => {
  const state = buildHydratedSessionState({
    session_id: "sess-1",
    status: "playing",
    world_name: "雾隐镇",
    character_name: "外来调查员",
    character_description: "善于推理",
    character_abilities: ["观察"],
    game_state: {
      current_time: "第1天·下午",
      current_location: "茶摊",
      player_inventory: [],
      discovered_clues: [],
      npc_relations: {},
      triggered_events: [],
      visited_locations: ["镇口", "茶摊"],
    },
    messages: [
      {
        role: "user",
        content: "我去茶摊",
        created_at: "2026-04-08T06:00:00",
      },
      {
        role: "assistant",
        content: "你看见茶摊边有人低声交谈。",
        created_at: "2026-04-08T06:00:01",
      },
    ],
  });

  assert.equal(state.sessionId, "sess-1");
  assert.equal(state.worldName, "雾隐镇");
  assert.equal(state.characterName, "外来调查员");
  assert.deepEqual(state.characterAbilities, ["观察"]);
  assert.equal(state.messages.length, 2);
  assert.equal(state.messages[0].role, "user");
  assert.equal(state.messages[1].role, "narrator");
  assert.equal(state.messages[1].content, "你看见茶摊边有人低声交谈。");
});

test("buildHydratedSessionState hides internal opening prompts from history", () => {
  const state = buildHydratedSessionState({
    session_id: "sess-2",
    status: "playing",
    world_name: "雾隐镇",
    character_name: "外来调查员",
    character_description: "善于推理",
    character_abilities: ["观察"],
    game_state: {
      current_time: "第1天·上午",
      current_location: "镇口茶摊",
      player_inventory: [],
      discovered_clues: [],
      npc_relations: {},
      triggered_events: [],
      visited_locations: ["镇口茶摊"],
    },
    messages: [
      {
        role: "user",
        content: "游戏开始。玩家扮演外来调查员（善于推理），刚刚抵达镇口茶摊。请描写开场场景，营造氛围，介绍周围环境和可见的NPC。",
        created_at: "2026-04-08T06:00:00",
      },
      {
        role: "assistant",
        content: "浓雾从镇口漫过来。",
        created_at: "2026-04-08T06:00:01",
      },
    ],
  });

  assert.equal(state.messages.length, 1);
  assert.equal(state.messages[0].role, "narrator");
  assert.equal(state.messages[0].content, "浓雾从镇口漫过来。");
});
