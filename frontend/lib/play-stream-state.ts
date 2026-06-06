import type { PlayStreamPhase, ProcessingEventPayload } from "./types";

export interface PlayStreamStateSnapshot {
  phase: PlayStreamPhase;
  processing: ProcessingEventPayload | null;
}

const DEFAULT_PROCESSING_PHASE = "thinking";
const GENERIC_ENVIRONMENT_FLAVOR = "周围一时安静下来，像是在等你下一步动作";

function cleanFocusNpcs(focusNpcs: string[] | undefined): string[] {
  if (!Array.isArray(focusNpcs)) {
    return [];
  }

  const names: string[] = [];
  for (const npcName of focusNpcs) {
    const cleaned = String(npcName).trim();
    if (!cleaned || names.includes(cleaned)) {
      continue;
    }
    names.push(cleaned);
  }

  return names;
}

export function createIdlePlayStreamState(): PlayStreamStateSnapshot {
  return {
    phase: "idle",
    processing: null,
  };
}

export function startPlayStream(): PlayStreamStateSnapshot {
  return {
    phase: "processing",
    processing: null,
  };
}

export function isActivePlayStreamPhase(phase: PlayStreamPhase): boolean {
  return phase === "processing" || phase === "streaming";
}

export function resolveProcessingFlavor(
  payload: Partial<ProcessingEventPayload> | null | undefined,
  currentLocation?: string | null,
): string {
  const explicitFlavor = typeof payload?.flavor === "string" ? payload.flavor.trim() : "";
  if (explicitFlavor) {
    return explicitFlavor;
  }

  const focusNpcs = cleanFocusNpcs(payload?.focus_npcs);
  if (focusNpcs.length === 1) {
    return `${focusNpcs[0]}像是想起了什么`;
  }
  if (focusNpcs.length === 2) {
    return `${focusNpcs[0]}和${focusNpcs[1]}似乎在交换眼神`;
  }

  const location = currentLocation?.trim();
  if (location) {
    return `${location}里一时安静下来，像是在等你看清局势`;
  }

  return GENERIC_ENVIRONMENT_FLAVOR;
}

export function normalizeProcessingEvent(
  payload: Partial<ProcessingEventPayload> | null | undefined,
  currentLocation?: string | null,
): ProcessingEventPayload {
  return {
    phase:
      typeof payload?.phase === "string" && payload.phase.trim()
        ? payload.phase.trim()
        : DEFAULT_PROCESSING_PHASE,
    focus_npcs: cleanFocusNpcs(payload?.focus_npcs),
    flavor: resolveProcessingFlavor(payload, currentLocation),
    // v2 思考态演进进度：stage 驱动 logo + i18n 文案（组件层拼装）。
    stage: payload?.stage,
    input_summary:
      typeof payload?.input_summary === "string" ? payload.input_summary : undefined,
    npcs: cleanFocusNpcs(payload?.npcs),
  };
}

export function applyProcessingEvent(
  state: PlayStreamStateSnapshot,
  payload: Partial<ProcessingEventPayload> | null | undefined,
  currentLocation?: string | null,
): PlayStreamStateSnapshot {
  if (state.phase === "streaming" || state.phase === "done" || state.phase === "error") {
    return state;
  }

  return {
    phase: "processing",
    processing: normalizeProcessingEvent(payload, currentLocation),
  };
}

export function receiveNarrativeToken(state: PlayStreamStateSnapshot): PlayStreamStateSnapshot {
  if (state.phase === "done" || state.phase === "error") {
    return state;
  }

  return {
    phase: "streaming",
    processing: null,
  };
}

export function completePlayStream(state: PlayStreamStateSnapshot): PlayStreamStateSnapshot {
  if (state.phase === "error") {
    return {
      phase: "error",
      processing: null,
    };
  }

  return {
    phase: "done",
    processing: null,
  };
}

export function failPlayStream(): PlayStreamStateSnapshot {
  return {
    phase: "error",
    processing: null,
  };
}
