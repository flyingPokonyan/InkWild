import type { AdminProgressEvent } from "./admin-sse-events";
import type { ProgressMeta } from "./admin-sse-events";
import type { AdminGenerationTaskEvent } from "./types";

export type AdminPhaseKind = "progress" | "warning";
export type AdminPhaseStatus = "running" | "done" | "warning" | "error";

export interface AdminPhaseEntry {
  id: string;
  phase: string;
  code: string;
  message: string;
  kind: AdminPhaseKind;
  status: AdminPhaseStatus;
  stageLabel?: string;
}

function stageLabelOf(event: AdminProgressEvent): string | undefined {
  const stageLabel = event.meta?.stage_label;
  return typeof stageLabel === "string" && stageLabel.length > 0 ? stageLabel : undefined;
}

function normalizeMessage(event: AdminProgressEvent): string {
  // Only return user-facing strings here — never the raw code/phase machine
  // identifiers, those leak as e.g. "IP 知识抽取 started" in the headline.
  // Empty string is fine; the view layer falls back to the localized phase
  // label via resolvePhaseLabel().
  return event.message?.trim() ?? "";
}

// phase_a 内部 stage，已通过 IPRecognitionCard 表达，不进 phase_b timeline。
const HIDDEN_PHASES = new Set(["ip_recognition"]);

export function appendAdminPhaseEvent(
  prev: AdminPhaseEntry[],
  event: AdminProgressEvent,
  kind: AdminPhaseKind = "progress",
): AdminPhaseEntry[] {
  if (HIDDEN_PHASES.has(event.phase)) {
    return prev;
  }
  const finalized = prev.map((item) =>
    item.status === "running" ? { ...item, status: "done" as const } : item,
  );

  return [
    ...finalized,
    {
      id:
        typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
          ? crypto.randomUUID()
          : `${event.phase}:${event.code}:${finalized.length}`,
      phase: event.phase,
      code: event.code,
      message: normalizeMessage(event),
      kind,
      status: kind === "warning" ? "warning" : "running",
      stageLabel: stageLabelOf(event),
    },
  ];
}

export function completeAdminPhaseTimeline(prev: AdminPhaseEntry[]): AdminPhaseEntry[] {
  return prev.map((item) =>
    item.status === "running" ? { ...item, status: "done" as const } : item,
  );
}

export function markLatestAdminPhaseAsError(prev: AdminPhaseEntry[]): AdminPhaseEntry[] {
  let marked = false;
  return [...prev].reverse().map((item) => {
    if (!marked && item.status === "running") {
      marked = true;
      return { ...item, status: "error" as const };
    }
    return item;
  }).reverse();
}

export function hydrateAdminPhaseTimeline(events: AdminGenerationTaskEvent[]): AdminPhaseEntry[] {
  let phases: AdminPhaseEntry[] = [];
  for (const event of events) {
    if (event.event === "progress") {
      phases = appendAdminPhaseEvent(phases, {
        phase: String(event.payload.phase || ""),
        code: String(event.payload.code || ""),
        message: String(event.payload.message || ""),
        meta: (event.payload.meta as ProgressMeta | undefined),
      });
      continue;
    }
    if (event.event === "warning") {
      phases = appendAdminPhaseEvent(phases, {
        phase: String(event.payload.phase || ""),
        code: String(event.payload.code || ""),
        message: String(event.payload.message || ""),
        meta: (event.payload.meta as ProgressMeta | undefined),
      }, "warning");
      continue;
    }
    if (event.event === "error") {
      phases = markLatestAdminPhaseAsError(phases);
    }
    if (event.event === "done") {
      phases = completeAdminPhaseTimeline(phases);
    }
  }
  return phases;
}

// ---------- Stage state machine (shared between live SSE and hydrate) ----------

import {
  extractSubtaskItem,
  initStagesMap,
  isStageKey,
  type StageKey,
  type StageState,
} from "./admin-generation-stages";

const COMPLETED_CODES = new Set([
  "completed",
  "repair_completed",
  "review_adjusted",
  "review_completed",
]);

/**
 * Pure reducer: applies one progress/warning event to the stages map, returning a new Map.
 * Pulse events (code === "pulse") do not change stage status — they only drive the headline.
 */
export function applyEventToStages(
  prev: Map<StageKey, StageState>,
  event: AdminProgressEvent,
): Map<StageKey, StageState> {
  if (!event.phase || !isStageKey(event.phase)) return prev;
  if (event.code === "pulse") return prev;

  const phase = event.phase;
  const meta = event.meta;
  const next = new Map(prev);
  const existing: StageState =
    next.get(phase) ?? { status: "pending", recentItems: [] };

  if (event.code === "started") {
    next.set(phase, {
      ...existing,
      status: "running",
      startedAt: existing.startedAt ?? Date.now(),
      subtaskTotal: meta?.subtask_total ?? existing.subtaskTotal,
    });
    return next;
  }

  if (COMPLETED_CODES.has(event.code)) {
    next.set(phase, {
      ...existing,
      status: "completed",
      completedAt: Date.now(),
      payloadSummary: meta?.payload_summary ?? existing.payloadSummary,
      completedMeta: meta ?? existing.completedMeta,
    });
    return next;
  }

  if (event.code === "subtask_started") {
    next.set(phase, {
      ...existing,
      subtaskTotal: meta?.subtask_total ?? existing.subtaskTotal,
    });
    return next;
  }

  if (event.code === "subtask_completed") {
    const prevDone = existing.subtaskDone ?? 0;
    const nextDone =
      meta?.subtask_index !== undefined
        ? Math.max(prevDone, meta.subtask_index + 1)
        : prevDone + 1;
    const item = extractSubtaskItem(phase, meta);
    const nextRecentItems = item
      ? [...existing.recentItems, item].slice(-3)
      : existing.recentItems;
    next.set(phase, {
      ...existing,
      subtaskTotal: meta?.subtask_total ?? existing.subtaskTotal,
      subtaskDone: nextDone,
      recentItems: nextRecentItems,
      payloadSummary: meta?.payload_summary ?? existing.payloadSummary,
    });
    return next;
  }

  return next;
}

/** Marks any currently-running stage as failed (called on error events). */
export function markRunningStagesFailed(
  prev: Map<StageKey, StageState>,
): Map<StageKey, StageState> {
  const next = new Map(prev);
  for (const [key, state] of next) {
    if (state.status === "running") {
      next.set(key, { ...state, status: "failed" });
    }
  }
  return next;
}

/**
 * Replays a historical event list into a fresh stages Map.
 * Mirror of `hydrateAdminPhaseTimeline` for the stages state machine —
 * fixes the "0/12 stuck after refresh" bug.
 */
export function hydrateStagesFromEvents(
  events: AdminGenerationTaskEvent[],
): Map<StageKey, StageState> {
  let map = initStagesMap();
  for (const evt of events) {
    if (evt.event === "progress" || evt.event === "warning") {
      const payload = evt.payload as {
        phase?: string;
        code?: string;
        message?: string;
        meta?: ProgressMeta;
      };
      map = applyEventToStages(map, {
        phase: String(payload.phase || ""),
        code: String(payload.code || ""),
        message: String(payload.message || ""),
        meta: payload.meta,
      });
    } else if (evt.event === "error") {
      map = markRunningStagesFailed(map);
    }
  }
  return map;
}
