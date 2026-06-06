import type { CharacterDTO, ScriptDTO, WorldDetail } from "./types";

export type WorldMode = "script" | "free";

export const IMPLICIT_SCRIPT_ID = "__implicit_world_script__";

export interface ScriptCardModel {
  id: string;
  name: string;
  description: string;
  estimatedTime: string;
  difficulty: number;
  isImplicit: boolean;
  coverImage: string | null;
}

export interface WorldExperiencePanelModel {
  eyebrow: string;
  title: string;
  description: string;
  items: string[];
}

export interface CharacterFocusModel {
  label: string;
  items: string[];
}

function toImplicitScript(world: WorldDetail): ScriptCardModel {
  return {
    id: IMPLICIT_SCRIPT_ID,
    name: "当前剧本",
    description: world.description,
    estimatedTime: world.estimated_time,
    difficulty: world.difficulty,
    isImplicit: true,
    coverImage: world.cover_image,
  };
}

export function parseFreeSetting(freeSetting: string | null): string[] {
  if (!freeSetting) {
    return [];
  }

  return freeSetting
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .slice(0, 3);
}

export function buildScriptCards(world: WorldDetail): ScriptCardModel[] {
  if (world.scripts.length > 0) {
    return world.scripts.map((script) => ({
      id: script.id,
      name: script.name,
      description: script.description,
      estimatedTime: script.estimated_time,
      difficulty: script.difficulty,
      isImplicit: false,
      coverImage: script.cover_image,
    }));
  }

  if (world.has_script_mode) {
    return [toImplicitScript(world)];
  }

  return [];
}

/**
 * 解析某剧本下实际可玩的角色集合。
 * 剧本模式 + 名单非空 → 只返回名单内的角色；
 * 自由模式 / 隐式剧本 / 名单为空 / 过滤后为空（异常）→ 放行世界全部可玩角色。
 */
export function resolvePlayableCharacters(
  world: WorldDetail,
  script: ScriptDTO | null,
): CharacterDTO[] {
  const roster = script?.playable_character_ids ?? [];
  if (roster.length === 0) {
    return world.characters;
  }
  const filtered = world.characters.filter((character) => roster.includes(character.id));
  return filtered.length > 0 ? filtered : world.characters;
}

export function getInitialWorldSelection(world: WorldDetail): {
  mode: WorldMode;
  scriptId: string | null;
  characterId: string | null;
} {
  const mode: WorldMode = world.has_script_mode ? "script" : "free";
  const scriptId = mode === "script" ? (buildScriptCards(world)[0]?.id ?? null) : null;
  // 默认角色落在首个剧本的可玩集合里，避免默认选中一个不属于该剧本的角色。
  const firstScript = mode === "script" ? world.scripts.find((s) => s.id === scriptId) ?? null : null;
  const candidates = resolvePlayableCharacters(world, firstScript);

  return {
    mode,
    scriptId,
    characterId: candidates[0]?.id ?? null,
  };
}

export function resolveSelectedScript(
  world: WorldDetail,
  selectedScriptId: string | null,
): ScriptCardModel | null {
  const scriptCards = buildScriptCards(world);
  if (scriptCards.length === 0) {
    return null;
  }

  return scriptCards.find((script) => script.id === selectedScriptId) ?? scriptCards[0] ?? null;
}

export function resolveStartScriptId(
  world: WorldDetail,
  selectedScriptId: string | null,
): string | undefined {
  const script = resolveSelectedScript(world, selectedScriptId);

  if (!script || script.isImplicit) {
    return undefined;
  }

  return script.id;
}

export function buildExperiencePanel(
  world: WorldDetail,
  mode: WorldMode,
  selectedScriptId: string | null,
): WorldExperiencePanelModel {
  if (mode === "free") {
    const highlights = parseFreeSetting(world.free_setting);
    return {
      eyebrow: "当前暗流",
      title: `以你自己的方式进入${world.name}`,
      description: "没有预设终点，世界会持续回应你的选择。",
      items: highlights.length > 0 ? highlights : ["镇上的风声尚未散去，你会从自己的选择里卷入故事。"],
    };
  }

  const script = resolveSelectedScript(world, selectedScriptId);

  if (!script) {
    return {
      eyebrow: "当前体验",
      title: "请选择这次故事线",
      description: "选定一条故事线后，你会看到这次体验的目标和切口。",
      items: [],
    };
  }

  return {
    eyebrow: "当前体验",
    title: script.name,
    description: script.description || "这是一条有目标、有终点的故事线。",
    items: [
      `预计时长：${script.estimatedTime}`,
      `难度：${script.difficulty}`,
      "这是一条有目标、有终点的故事线。",
    ],
  };
}

export function buildCharacterFocus(
  world: WorldDetail,
  character: CharacterDTO,
  mode: WorldMode,
  selectedScriptId: string | null,
): CharacterFocusModel {
  if (mode === "free") {
    const highlights = parseFreeSetting(world.free_setting);
    const items = [`起始地点：${character.starting_location}`];

    if (character.starting_inventory.length > 0) {
      items.push(`随身物品：${character.starting_inventory.join("、")}`);
    }

    if (highlights[0]) {
      items.push(`最近会听到：${highlights[0]}`);
    }

    return {
      label: "你的切入点",
      items,
    };
  }

  const script = resolveSelectedScript(world, selectedScriptId);
  const items = [];

  if (script) {
    items.push(`当前剧本：${script.name}`);
  }

  items.push(`优先切口：从${character.starting_location}开始打探`);

  if (character.abilities[0]) {
    items.push(`最容易发挥：${character.abilities[0]}`);
  }

  return {
    label: "你的任务",
    items,
  };
}

export function buildStartSummary(
  world: WorldDetail,
  mode: WorldMode,
  selectedScriptId: string | null,
  character: CharacterDTO | null,
): string {
  if (!character) {
    return "当前选择：未选择身份";
  }

  if (mode === "free") {
    return `当前选择：自由探索 · ${character.name}`;
  }

  const script = resolveSelectedScript(world, selectedScriptId);
  return `当前选择：${script?.name ?? "未选择剧本"} · ${character.name}`;
}

export function canStartWorldEntry(
  world: WorldDetail,
  mode: WorldMode,
  selectedScriptId: string | null,
  characterId: string | null,
): boolean {
  if (!characterId) {
    return false;
  }

  if (mode === "free") {
    return true;
  }

  if (buildScriptCards(world).length > 1 && !selectedScriptId) {
    return false;
  }

  return resolveSelectedScript(world, selectedScriptId) !== null;
}

export function getScriptSelectionPrompt(
  world: WorldDetail,
  mode: WorldMode,
  selectedScriptId: string | null,
): string | null {
  if (mode !== "script") {
    return null;
  }

  if (buildScriptCards(world).length <= 1) {
    return null;
  }

  if (selectedScriptId) {
    return null;
  }

  return "请选择这次要体验的剧本";
}

export function getScriptCardColumns(scriptCount: number): string {
  if (scriptCount <= 1) {
    return "grid-cols-1";
  }

  if (scriptCount === 2) {
    return "grid-cols-1 md:grid-cols-2";
  }

  return "grid-cols-1 md:grid-cols-2 xl:grid-cols-3";
}

export function isImplicitScript(script: ScriptCardModel | ScriptDTO | null | undefined): boolean {
  return Boolean(script && "id" in script && script.id === IMPLICIT_SCRIPT_ID);
}
