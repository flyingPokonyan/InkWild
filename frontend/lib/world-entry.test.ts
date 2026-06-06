import assert from "node:assert/strict";

import type { CharacterDTO, WorldDetail } from "./types.ts";
import {
  buildCharacterFocus,
  buildExperiencePanel,
  buildScriptCards,
  canStartWorldEntry,
  getInitialWorldSelection,
  IMPLICIT_SCRIPT_ID,
  parseFreeSetting,
  resolvePlayableCharacters,
} from "./world-entry.ts";

const sampleWorld: WorldDetail = {
  id: "world-1",
  name: "雾隐镇",
  description: "一个不断有人失踪的民国小镇。",
  genre: "悬疑",
  era: "民国",
  difficulty: 3,
  estimated_time: "30-60分钟",
  cover_image: "",
  has_script_mode: true,
  free_setting: "夜里总有人失踪\n警署内部有人压案\n后山总有人点灯",
  characters: [
    {
      id: "char-1",
      name: "记者",
      description: "善于打探消息。",
      abilities: ["采访", "速记"],
      starting_location: "白教堂",
      starting_inventory: ["旧笔记本"],
    },
  ],
  scripts: [
    {
      id: "script-1",
      name: "失踪案",
      description: "围绕王老爷失踪展开调查。",
      difficulty: 2,
      estimated_time: "30-60分钟",
    },
    {
      id: "script-2",
      name: "古井传说",
      description: "井下异响与旧年祭祀。",
      difficulty: 4,
      estimated_time: "45-75分钟",
    },
  ],
};

test("getInitialWorldSelection defaults to script mode and first script when available", () => {
  const selection = getInitialWorldSelection(sampleWorld);

  assert.equal(selection.mode, "script");
  assert.equal(selection.scriptId, "script-1");
  assert.equal(selection.characterId, "char-1");
});

const twoCharWorld: WorldDetail = {
  ...sampleWorld,
  characters: [
    {
      id: "a",
      name: "甲",
      description: "",
      abilities: [],
      starting_location: "",
      starting_inventory: [],
      avatar: null,
    },
    {
      id: "b",
      name: "乙",
      description: "",
      abilities: [],
      starting_location: "",
      starting_inventory: [],
      avatar: null,
    },
  ],
};

test("resolvePlayableCharacters returns all when roster empty", () => {
  // sampleWorld scripts carry no playable_character_ids → allow-all.
  const result = resolvePlayableCharacters(twoCharWorld, twoCharWorld.scripts[0]);
  assert.equal(result.length, 2);
});

test("resolvePlayableCharacters returns all for free mode (null script)", () => {
  const result = resolvePlayableCharacters(twoCharWorld, null);
  assert.equal(result.length, 2);
});

test("resolvePlayableCharacters filters to roster when non-empty", () => {
  const script = { ...twoCharWorld.scripts[0], playable_character_ids: ["b"] };
  const result = resolvePlayableCharacters(twoCharWorld, script);
  assert.deepEqual(result.map((c) => c.id), ["b"]);
});

test("resolvePlayableCharacters falls back to all when roster matches nothing", () => {
  const script = { ...twoCharWorld.scripts[0], playable_character_ids: ["does-not-exist"] };
  const result = resolvePlayableCharacters(twoCharWorld, script);
  assert.equal(result.length, 2);
});

test("getInitialWorldSelection default character stays inside first script roster", () => {
  const world: WorldDetail = {
    ...twoCharWorld,
    scripts: [
      { ...twoCharWorld.scripts[0], playable_character_ids: ["b"] },
      twoCharWorld.scripts[1],
    ],
  };
  const selection = getInitialWorldSelection(world);
  assert.equal(selection.characterId, "b");
});

test("getInitialWorldSelection falls back to free mode when script mode is unavailable", () => {
  const selection = getInitialWorldSelection({
    ...sampleWorld,
    has_script_mode: false,
    scripts: [],
  });

  assert.equal(selection.mode, "free");
  assert.equal(selection.scriptId, null);
});

test("parseFreeSetting trims lines and keeps the first three highlights", () => {
  assert.deepEqual(
    parseFreeSetting("  夜里总有人失踪 \n\n警署内部有人压案\n后山总有人点灯\n第四条会被忽略"),
    ["夜里总有人失踪", "警署内部有人压案", "后山总有人点灯"],
  );
});

test("buildScriptCards returns a consistent card model for one or many scripts", () => {
  const many = buildScriptCards(sampleWorld);
  const one = buildScriptCards({
    ...sampleWorld,
    scripts: [sampleWorld.scripts[0]],
  });

  assert.equal(many[0].id, "script-1");
  assert.equal(one[0].id, "script-1");
  assert.equal(one[0].estimatedTime, "30-60分钟");
  assert.equal(one[0].difficulty, 2);
});

test("buildScriptCards creates an implicit script card for legacy script worlds", () => {
  const legacy = buildScriptCards({
    ...sampleWorld,
    scripts: [],
  });

  assert.equal(legacy.length, 1);
  assert.equal(legacy[0].id, IMPLICIT_SCRIPT_ID);
  assert.equal(legacy[0].name, "当前剧本");
});

test("buildExperiencePanel returns script-focused content for script mode", () => {
  const panel = buildExperiencePanel(sampleWorld, "script", "script-2");

  assert.equal(panel.eyebrow, "当前体验");
  assert.equal(panel.title, "古井传说");
  assert.ok(panel.items.some((item) => item.includes("45-75分钟")));
});

test("buildCharacterFocus returns free-mode entry details", () => {
  const focus = buildCharacterFocus(
    sampleWorld,
    sampleWorld.characters[0] as CharacterDTO,
    "free",
    null,
  );

  assert.equal(focus.label, "你的切入点");
  assert.ok(focus.items.some((item) => item.includes("起始地点：白教堂")));
  assert.ok(focus.items.some((item) => item.includes("旧笔记本")));
  assert.ok(focus.items.some((item) => item.includes("夜里总有人失踪")));
});

test("canStartWorldEntry blocks script mode without a resolved script selection", () => {
  assert.equal(canStartWorldEntry(sampleWorld, "script", null, "char-1"), false);
  assert.equal(canStartWorldEntry(sampleWorld, "script", "script-1", "char-1"), true);
  assert.equal(canStartWorldEntry(sampleWorld, "free", null, "char-1"), true);
});
