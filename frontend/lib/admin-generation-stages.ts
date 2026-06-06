import type { ProgressMeta } from "./admin-sse-events";

// Stage key union, ordered to match backend services/world_creator_agent_v2.py _STAGE_INDEX
// (visual_brief is folded into the images entry visually; validating is post-process and not shown).
export type StageKey =
  | "research_pack"
  | "world_base"
  | "lore_dimensions"
  | "character_roster"
  | "lore_pack"
  | "characters"
  | "shared_events"
  | "relations_pack"
  | "events_data"
  | "playable"
  | "critic"
  | "images";

export type StageStatus = "pending" | "running" | "completed" | "failed";

export interface StageState {
  status: StageStatus;
  startedAt?: number;
  completedAt?: number;
  subtaskTotal?: number;
  subtaskDone?: number;
  payloadSummary?: ProgressMeta["payload_summary"];
  /** Last completed-event meta carried for richer summaries. */
  completedMeta?: ProgressMeta;
  /** Recent subtask item labels, FIFO, keep last 3. */
  recentItems: string[];
}

export const STAGE_LIST: Array<{ key: StageKey; label: string }> = [
  { key: "research_pack", label: "收集研究素材" },
  { key: "world_base", label: "构建世界基础" },
  { key: "lore_dimensions", label: "扩展世界维度" },
  { key: "character_roster", label: "规划角色阵容" },
  { key: "lore_pack", label: "生成世界设定" },
  { key: "characters", label: "创建角色档案" },
  { key: "shared_events", label: "设计共享事件" },
  { key: "relations_pack", label: "构建角色关系" },
  { key: "events_data", label: "生成事件数据" },
  { key: "playable", label: "可玩性校验" },
  { key: "critic", label: "品质审核" },
  { key: "images", label: "生成配图" },
];

export const STAGE_LABELS: Record<StageKey, string> = STAGE_LIST.reduce(
  (acc, { key, label }) => {
    acc[key] = label;
    return acc;
  },
  {} as Record<StageKey, string>,
);

export const STAGE_KEYS: ReadonlyArray<StageKey> = STAGE_LIST.map((s) => s.key);

export function initStagesMap(): Map<StageKey, StageState> {
  return new Map(
    STAGE_LIST.map(({ key }) => [key, { status: "pending" as const, recentItems: [] }]),
  );
}

export function isStageKey(value: string): value is StageKey {
  return (STAGE_KEYS as readonly string[]).includes(value);
}

/**
 * Extracts a single display-ready item label from a subtask_completed event's meta.
 * Stage → field mapping (see backend services/world_creator_agent_v2.py):
 * - characters: payload_summary.name (+ optional · role_tag)
 * - lore_pack: payload_summary.dim_label
 * - events_data: payload_summary.title
 * - images: payload_summary.label
 */
export function extractSubtaskItem(
  stage: StageKey,
  meta: ProgressMeta | undefined,
): string | null {
  const summary = meta?.payload_summary as Record<string, unknown> | undefined;
  if (!summary) return null;

  switch (stage) {
    case "characters": {
      const name = typeof summary.name === "string" ? summary.name : null;
      const role =
        typeof summary.role_tag === "string" && summary.role_tag.length > 0
          ? summary.role_tag
          : null;
      if (!name) return null;
      return role ? `${name}·${role}` : name;
    }
    case "lore_pack":
      return typeof summary.dim_label === "string" ? summary.dim_label : null;
    case "events_data":
      return typeof summary.title === "string" ? summary.title : null;
    case "images":
      return typeof summary.label === "string" ? summary.label : null;
    default:
      return null;
  }
}

// ---------- Per-stage display formatter ----------

const RUNNING_LINES: Partial<Record<StageKey, (state: StageState) => string | undefined>> = {
  characters: (s) =>
    s.recentItems.length > 0
      ? `刚生成：${s.recentItems.slice(-2).join("、")}`
      : "正在创建角色档案…",
  lore_pack: (s) =>
    s.recentItems.length > 0
      ? `刚补完：${s.recentItems.slice(-2).join("、")}`
      : "正在补全世界设定…",
  events_data: (s) =>
    s.recentItems.length > 0
      ? `刚设计事件：${s.recentItems.slice(-2).join("、")}`
      : "正在编排事件链…",
  images: (s) =>
    s.recentItems.length > 0
      ? `刚画完：${s.recentItems.slice(-2).join("、")}`
      : "正在生成配图…",
  // research_pack / world_base / lore_dimensions / character_roster /
  // shared_events / relations_pack / playable / critic intentionally return
  // undefined here — their narrative is carried by pulse events in the headline.
};

function readSample(meta: ProgressMeta): string {
  return Array.isArray(meta.sample)
    ? meta.sample.filter((s) => typeof s === "string" && s.length > 0).join("、")
    : "";
}

function readNum(meta: ProgressMeta, key: keyof ProgressMeta | string): number | undefined {
  const summary = meta.payload_summary as Record<string, unknown> | undefined;
  const fromTop = (meta as unknown as Record<string, unknown>)[key as string];
  const candidate = summary?.[key as string] ?? fromTop;
  return typeof candidate === "number" ? candidate : undefined;
}

function readStr(meta: ProgressMeta, key: keyof ProgressMeta | string): string | undefined {
  const summary = meta.payload_summary as Record<string, unknown> | undefined;
  const fromTop = (meta as unknown as Record<string, unknown>)[key as string];
  const candidate = summary?.[key as string] ?? fromTop;
  return typeof candidate === "string" ? candidate : undefined;
}

const COMPLETED_LINES: Partial<Record<StageKey, (meta: ProgressMeta) => string | undefined>> = {
  research_pack: (m) => {
    const n = readNum(m, "artifact_count");
    const sample = readSample(m);
    if (n === undefined && !sample) return undefined;
    return [n !== undefined ? `${n} 条素材` : null, sample || null]
      .filter(Boolean)
      .join(" · ");
  },
  world_base: (m) => {
    const name = readStr(m, "world_name");
    const n = readNum(m, "location_count");
    const sample = readSample(m);
    const head = name ?? "世界";
    if (n === undefined && !sample) return head;
    const tail = sample
      ? `${sample}${n !== undefined && n > 3 ? ` 等 ${n} 地` : ""}`
      : `${n} 地`;
    return `${head} · ${tail}`;
  },
  lore_dimensions: (m) => {
    const n = readNum(m, "dimension_count");
    const sample = readSample(m);
    if (n === undefined && !sample) return undefined;
    return [n !== undefined ? `${n} 维度` : null, sample || null]
      .filter(Boolean)
      .join(" · ");
  },
  character_roster: (m) => {
    const n = readNum(m, "role_count");
    const sample = readSample(m);
    if (n === undefined && !sample) return undefined;
    return [n !== undefined ? `${n} 位身份` : null, sample || null]
      .filter(Boolean)
      .join(" · ");
  },
  lore_pack: (m) => {
    const n = readNum(m, "dimension_count");
    const sample = readSample(m);
    if (n === undefined && !sample) return undefined;
    return [n !== undefined ? `${n} 维度补全` : null, sample || null]
      .filter(Boolean)
      .join(" · ");
  },
  characters: (m) => {
    const n = readNum(m, "character_count");
    const sample = readSample(m);
    if (n === undefined) return undefined;
    return sample ? `${n} 位 · ${sample} 等` : `${n} 位`;
  },
  shared_events: (m) => {
    const n = readNum(m, "event_count");
    const sample = readSample(m);
    if (n === undefined && !sample) return undefined;
    return [n !== undefined ? `${n} 段历史` : null, sample || null]
      .filter(Boolean)
      .join(" · ");
  },
  relations_pack: (m) => {
    const npcs = readNum(m, "npc_count");
    const edges = readNum(m, "edge_count");
    if (npcs === undefined) return undefined;
    return edges !== undefined
      ? `${npcs} 位角色 · 共 ${edges} 条关系`
      : `${npcs} 位角色`;
  },
  events_data: (m) => {
    const n = readNum(m, "event_count");
    const clues = readNum(m, "clue_count");
    const sample = readSample(m);
    if (n === undefined) return undefined;
    return [
      `${n} 事件`,
      clues !== undefined ? `${clues} 线索` : null,
      sample || null,
    ]
      .filter(Boolean)
      .join(" · ");
  },
  playable: (m) => {
    const n = readNum(m, "playable_count");
    const sample = readSample(m);
    if (n === undefined && !sample) return undefined;
    if (sample) {
      const total = n ?? sample.split("、").length;
      return `选定 ${total} 位 · ${sample}`;
    }
    return `选定 ${n} 位`;
  },
  critic: (m) => {
    const repair = readNum(m, "repair_count");
    if (repair !== undefined && repair > 0) return `修正 ${repair} 处`;
    return "通过";
  },
  images: (m) => {
    const cover = readNum(m, "cover_count");
    const avatar = readNum(m, "avatar_count");
    const total = readNum(m, "image_count");
    if (cover !== undefined || avatar !== undefined) {
      return [
        cover !== undefined ? `${cover} 主图` : null,
        avatar !== undefined ? `${avatar} 头像` : null,
      ]
        .filter(Boolean)
        .join(" · ");
    }
    return total !== undefined ? `${total} 张` : undefined;
  },
};

export function formatStageLine(
  stage: StageKey,
  state: StageState,
): { running?: string; completed?: string } {
  if (state.status === "running") {
    return { running: RUNNING_LINES[stage]?.(state) };
  }
  if (state.status === "completed") {
    const meta = state.completedMeta;
    if (!meta) return {};
    return { completed: COMPLETED_LINES[stage]?.(meta) };
  }
  return {};
}
