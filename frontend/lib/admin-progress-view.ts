import type { AdminPhaseEntry } from "./admin-progress-state";

export const MAX_VISIBLE_ADMIN_FEEDBACK = 5;

// PHASE 映射与 backend WorldCreatorAgentV2（services/world_creator_agent_v2.py）对齐。
// v1 名（research / validating 等）保留以兼容历史 generation_task_events。
const PHASE_LABELS: Record<string, string> = {
  boot: "创作会话",
  // v1 + v2 共享
  world_base: "世界框架",
  characters: "人物系统",
  playable: "可玩视角",
  images: "视觉方案",
  critic: "评审打磨",
  validating: "数据校验",
  script_base: "剧本框架",
  events: "事件链",
  endings: "结局设计",
  // v1 兼容
  research: "资料研判",
  // v2 world 新增
  research_pack: "资料研判",
  ip_research: "IP 知识抽取",
  lore_dimensions: "世界维度",
  character_roster: "人物阵容",
  lore_pack: "世界设定",
  shared_events: "共享事件",
  relations_pack: "角色关系",
  events_data: "事件数据",
  visual_brief: "视觉构思",
  // v2 script 新增
  script_visual_brief: "剧本视觉",
  script_images: "剧本配图",
};

// 世界生成 14 阶段权重（v2 _STAGE_INDEX 顺序），总和 100。
const WORLD_PHASE_WEIGHTS: Record<string, number> = {
  boot:             2,
  research_pack:    7,
  world_base:       7,
  lore_dimensions:  5,
  character_roster: 5,
  lore_pack:        9,
  characters:      14,
  shared_events:    7,
  relations_pack:   2,
  events_data:      9,
  playable:         4,
  critic:           8,
  visual_brief:     4,
  images:          14,
  validating:       3,
};

// 剧本生成 8 阶段权重（v2 _SCRIPT_STAGE_INDEX 顺序），总和 100。
const SCRIPT_PHASE_WEIGHTS: Record<string, number> = {
  boot:                3,
  research_pack:       8,
  script_base:        15,
  events:             22,
  endings:            16,
  playable:            6,
  critic:             10,
  script_visual_brief: 6,
  script_images:      14,
};

const WORLD_PHASE_ORDER = [
  "boot",
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
  "visual_brief",
  "images",
  "validating",
];

const SCRIPT_PHASE_ORDER = [
  "boot",
  "research_pack",
  "script_base",
  "events",
  "endings",
  "playable",
  "critic",
  "script_visual_brief",
  "script_images",
];

const PHASE_CODE_PROGRESS: Record<string, Record<string, number>> = {
  boot: {
    task_created: 0.12,
    session_started: 0.32,
    loading_world_context: 0.52,
    world_context_ready: 0.76,
    agent_ready: 1,
  },
  research: {
    analysis_started: 0.08,
    analysis_pulse: 0.16,
    request_ready: 0.3,
    searching: 0.45,
    searching_pulse: 0.6,
    search_completed: 0.76,
    summarizing: 0.86,
    summarizing_pulse: 0.94,
    reference_doc_ready: 1,
    not_needed: 1,
    search_unavailable: 1,
  },
  world_base: {
    brief_started: 0.08,
    brief_pulse: 0.16,
    brief_ready: 0.28,
    started: 0.42,
    drafting_pulse: 0.74,
    completed: 1,
  },
  characters: {
    brief_started: 0.08,
    brief_pulse: 0.16,
    brief_ready: 0.28,
    started: 0.42,
    drafting_pulse: 0.74,
    subtask_completed: 0.85,
    completed: 1,
  },
  research_pack: {
    started: 0.3,
    pulse: 0.5,
    completed: 1,
  },
  lore_dimensions: {
    started: 0.3,
    pulse: 0.5,
    completed: 1,
  },
  character_roster: {
    started: 0.3,
    pulse: 0.5,
    completed: 1,
  },
  lore_pack: {
    started: 0.2,
    subtask_completed: 0.6,
    subtask_failed: 0.6,
    completed: 1,
  },
  shared_events: {
    started: 0.3,
    pulse: 0.5,
    completed: 1,
  },
  relations_pack: {
    started: 0.5,
    completed: 1,
  },
  events_data: {
    started: 0.2,
    subtask_completed: 0.65,
    completed: 1,
  },
  visual_brief: {
    started: 0.4,
    pulse: 0.6,
    completed: 1,
  },
  script_visual_brief: {
    started: 0.4,
    completed: 1,
  },
  script_images: {
    started: 0.3,
    subtask_started: 0.4,
    subtask_completed: 0.7,
    completed: 1,
  },
  script_base: {
    brief_started: 0.08,
    brief_pulse: 0.16,
    brief_ready: 0.28,
    started: 0.42,
    drafting_pulse: 0.74,
    completed: 1,
  },
  events: {
    started: 0.3,
    drafting_pulse: 0.72,
    completed: 1,
  },
  endings: {
    started: 0.3,
    drafting_pulse: 0.72,
    completed: 1,
  },
  playable: {
    brief_started: 0.1,
    brief_pulse: 0.18,
    brief_ready: 0.3,
    started: 0.48,
    drafting_pulse: 0.74,
    completed: 1,
    review_started: 0.62,
    review_pulse: 0.82,
    review_completed: 1,
    review_adjusted: 1,
  },
  images: {
    brief_started: 0.08,
    brief_pulse: 0.16,
    brief_ready: 0.3,
    started: 0.46,
    subtask_started: 0.58,
    subtask_completed: 0.78,
    rendering_pulse: 0.8,
    cover_completed: 0.88,
    completed: 1,
    skipped: 1,
  },
  critic: {
    started: 0.2,
    review_pulse: 0.58,
    completed: 1,
    repair_started: 0.5,
    repair_completed: 1,
    repair_failed: 1,
  },
  validating: {
    started: 0.42,
    completed: 1,
    warnings: 1,
  },
};

function isScriptPhase(phases: AdminPhaseEntry[]): boolean {
  return phases.some((p) => p.phase === "script_base" || p.phase === "events" || p.phase === "endings");
}

/**
 * 根据当前 phases 计算加权进度百分比 (0–99)。
 *
 * 算法：
 * - 对每个已完成的 phase 累加其权重（done / warning）
 * - 对当前正在运行的 phase，按「该 phase 内部 tick 占 1/3」给半程估算
 * - 上限夹在 max_before_complete (99) 以避免 loading 消失前就到 100%
 */
export function computeWeightedProgress(phases: AdminPhaseEntry[]): number {
  if (phases.length === 0) return 2;

  const isScript = isScriptPhase(phases);
  const weights = isScript ? SCRIPT_PHASE_WEIGHTS : WORLD_PHASE_WEIGHTS;
  const order = isScript ? SCRIPT_PHASE_ORDER : WORLD_PHASE_ORDER;

  const totalWeight = order.reduce((sum, p) => sum + (weights[p] ?? 0), 0);
  if (totalWeight === 0) return 2;

  const phaseProgress: Record<string, number> = {};
  for (const entry of phases) {
    const codeProgress = PHASE_CODE_PROGRESS[entry.phase]?.[entry.code];
    const fallbackProgress =
      entry.status === "error"
        ? 0.18
        : entry.status === "warning"
          ? 1
          : entry.status === "done"
            ? 0.82
            : 0.32;
    const nextProgress = Math.max(phaseProgress[entry.phase] ?? 0, codeProgress ?? fallbackProgress);
    phaseProgress[entry.phase] = Math.min(1, nextProgress);
  }

  const weightedProgress = order.reduce((sum, phase) => {
    return sum + (weights[phase] ?? 0) * (phaseProgress[phase] ?? 0);
  }, 0);

  // Normalize to 0-99 range
  const pct = (weightedProgress / totalWeight) * 99;
  return Math.min(99, Math.max(2, Math.round(pct)));
}

export interface AdminLoadingDisplayEntry {
  id: string;
  label: string;
  stackLabel: string;
  headline: string;
  tone: "progress" | "warning" | "error" | "done";
  message: string;
}

export interface AdminLoadingSnapshot {
  history: AdminLoadingDisplayEntry[];
  current: AdminLoadingDisplayEntry | null;
}

function resolvePhaseLabel(entry: AdminPhaseEntry): string {
  if ((entry.phase === "research" || entry.phase === "research_pack") && entry.stageLabel) {
    return `${PHASE_LABELS[entry.phase]} · ${entry.stageLabel}`;
  }
  return PHASE_LABELS[entry.phase] || entry.phase;
}

function resolveStackLabel(entry: AdminPhaseEntry): string {
  if ((entry.phase === "research" || entry.phase === "research_pack") && entry.stageLabel) {
    return entry.stageLabel;
  }
  return PHASE_LABELS[entry.phase] || entry.phase;
}

function resolveTone(entry: AdminPhaseEntry): AdminLoadingDisplayEntry["tone"] {
  if (entry.status === "error") return "error";
  if (entry.status === "warning") return "warning";
  if (entry.status === "done") return "done";
  return "progress";
}

function toDisplayEntry(entry: AdminPhaseEntry): AdminLoadingDisplayEntry {
  return {
    id: entry.id,
    label: resolvePhaseLabel(entry),
    stackLabel: resolveStackLabel(entry),
    headline: entry.message || resolvePhaseLabel(entry),
    tone: resolveTone(entry),
    message: entry.message || resolvePhaseLabel(entry),
  };
}

export function buildAdminLoadingSnapshot(
  phases: AdminPhaseEntry[],
  maxVisible: number = MAX_VISIBLE_ADMIN_FEEDBACK,
): AdminLoadingSnapshot {
  if (phases.length === 0) {
    return {
      history: [],
      current: {
        id: "boot:fallback",
        label: PHASE_LABELS.boot,
        stackLabel: PHASE_LABELS.boot,
        headline: "正在建立生成连接…",
        tone: "progress",
        message: "正在建立生成连接…",
      },
    };
  }

  const visible = phases.slice(-Math.max(1, maxVisible)).map(toDisplayEntry);
  const current = visible.at(-1) || null;
  const rawHistory = visible.slice(0, -1);
  const collapsedHistory: AdminLoadingDisplayEntry[] = [];

  for (const entry of rawHistory) {
    const previous = collapsedHistory.at(-1);
    if (previous?.stackLabel === entry.stackLabel) {
      collapsedHistory[collapsedHistory.length - 1] = entry;
      continue;
    }
    collapsedHistory.push(entry);
  }

  if (current && collapsedHistory.at(-1)?.stackLabel === current.stackLabel) {
    collapsedHistory.pop();
  }

  return {
    history: collapsedHistory.slice(-(Math.max(1, maxVisible) - 1)),
    current,
  };
}
