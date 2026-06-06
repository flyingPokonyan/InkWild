import assert from "node:assert/strict";

import type { GameState } from "./types.ts";
import { buildContextSections } from "./context-drawer.ts";

const baseState: GameState = {
  current_time: "第1天·傍晚",
  current_location: "林府庭院",
  player_inventory: ["官府文书", "笔记本"],
  discovered_clues: [
    { id: "c1", content: "袖口沾有暗红泥土", found_at: "第1天·傍晚" },
  ],
  npc_relations: {
    王福: { trust: 2, mood: "紧张", last_interaction: "试图阻拦你靠近偏门" },
  },
  triggered_events: [],
  visited_locations: ["镇口", "林府庭院"],
  round_number: 4,
};

test("clues are structured with content and foundAt", () => {
  const { clues } = buildContextSections(baseState);
  assert.equal(clues.length, 1);
  assert.equal(clues[0].content, "袖口沾有暗红泥土");
  assert.equal(clues[0].foundAt, "第1天·傍晚");
});

test("npc trust is converted to attitude label", () => {
  const { npcs } = buildContextSections(baseState);
  assert.equal(npcs.length, 1);
  assert.equal(npcs[0].name, "王福");
  assert.equal(npcs[0].attitude, "警惕");
});

test("empty state returns empty arrays", () => {
  const { clues, npcs, inventory } = buildContextSections({
    ...baseState,
    player_inventory: [],
    discovered_clues: [],
    npc_relations: {},
  });
  assert.equal(clues.length, 0);
  assert.equal(npcs.length, 0);
  assert.equal(inventory.length, 0);
});

test("locations are no longer included", () => {
  const sections = buildContextSections(baseState);
  assert.equal("locations" in sections, false);
});
