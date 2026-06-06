import assert from "node:assert/strict";

import {
  STAGE_LIST,
  STAGE_LABELS,
  initStagesMap,
  type StageKey,
} from "./admin-generation-stages.ts";

test("STAGE_LIST is in backend _STAGE_INDEX order (excluding visual_brief and validating)", () => {
  const expected: StageKey[] = [
    "research_pack",
    "world_base",
    "lore_dimensions",
    "character_roster",
    "lore_pack",
    "characters",
    "shared_events",
    "relations_pack",
    "events_data",
    "playable",
    "critic",
    "images",
  ];
  assert.deepEqual(
    STAGE_LIST.map((s) => s.key),
    expected,
  );
});

test("STAGE_LABELS covers every stage key", () => {
  for (const { key } of STAGE_LIST) {
    assert.equal(typeof STAGE_LABELS[key], "string");
    assert.ok(STAGE_LABELS[key].length > 0);
  }
});

test("initStagesMap returns Map with every stage in pending state and empty recentItems", () => {
  const map = initStagesMap();
  assert.equal(map.size, STAGE_LIST.length);
  for (const { key } of STAGE_LIST) {
    const state = map.get(key);
    assert.ok(state);
    assert.equal(state.status, "pending");
    assert.deepEqual(state.recentItems, []);
  }
});

import { formatStageLine } from "./admin-generation-stages.ts";

test("formatStageLine returns empty object for pending stage", () => {
  const result = formatStageLine("characters", { status: "pending", recentItems: [] });
  assert.deepEqual(result, {});
});

test("formatStageLine.running uses recentItems for subtask stages", () => {
  const result = formatStageLine("characters", {
    status: "running",
    recentItems: ["李白·诗人", "杜甫·诗人"],
  });
  assert.equal(result.running, "刚生成：李白·诗人、杜甫·诗人");
});

test("formatStageLine.running fallback when recentItems is empty (subtask stages)", () => {
  const result = formatStageLine("characters", { status: "running", recentItems: [] });
  assert.equal(result.running, "正在创建角色档案…");
});

test("formatStageLine.running returns undefined for stages driven by pulse (no recentItems)", () => {
  const result = formatStageLine("shared_events", { status: "running", recentItems: [] });
  assert.equal(result.running, undefined);
});

test("formatStageLine.completed renders characters summary with sample + total", () => {
  const result = formatStageLine("characters", {
    status: "completed",
    recentItems: [],
    completedMeta: {
      payload_summary: { character_count: 12 },
      sample: ["李白", "杜甫", "王维"],
    },
  });
  assert.equal(result.completed, "12 位 · 李白、杜甫、王维 等");
});

test("formatStageLine.completed renders events_data summary with clues", () => {
  const result = formatStageLine("events_data", {
    status: "completed",
    recentItems: [],
    completedMeta: {
      payload_summary: { event_count: 8 },
      clue_count: 12,
      sample: ["朱雀街刺杀案", "月夜会客厅"],
    },
  });
  assert.equal(result.completed, "8 事件 · 12 线索 · 朱雀街刺杀案、月夜会客厅");
});

test("formatStageLine.completed renders images split", () => {
  const result = formatStageLine("images", {
    status: "completed",
    recentItems: [],
    completedMeta: {
      cover_count: 1,
      avatar_count: 13,
    },
  });
  assert.equal(result.completed, "1 主图 · 13 头像");
});

test("formatStageLine.completed renders critic pass vs repair", () => {
  const pass = formatStageLine("critic", {
    status: "completed",
    recentItems: [],
    completedMeta: { payload_summary: {} },
  });
  assert.equal(pass.completed, "通过");

  const repair = formatStageLine("critic", {
    status: "completed",
    recentItems: [],
    completedMeta: { repair_count: 3 },
  });
  assert.equal(repair.completed, "修正 3 处");
});

test("formatStageLine.completed gracefully degrades when meta is missing", () => {
  const result = formatStageLine("characters", {
    status: "completed",
    recentItems: [],
  });
  assert.equal(result.completed, undefined);
});
