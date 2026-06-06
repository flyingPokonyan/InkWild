// Derive a human-readable progress phase from narrative_arc.current_act +
// script_type. Mirrors backend engine/case_board_prompts.derive_progress_phase.
//
// The API injects this into GET /case-board responses; SSE turn updates
// only ship raw game_state, so the client derives it on the fly when
// reading from the live store.

const MYSTERY_PHASES: Record<string, string> = {
  intro: "初步调查",
  middle: "深入追查",
  climax: "真相浮现",
};

const EMOTIONAL_PHASES: Record<string, string> = {
  intro: "相遇",
  middle: "羁绊",
  climax: "抉择",
};

const DEFAULT_PHASES: Record<string, string> = {
  intro: "序章",
  middle: "发展",
  climax: "高潮",
};

export function deriveProgressPhase(
  scriptType: string | null | undefined,
  currentAct: string | null | undefined,
): string {
  if (!currentAct) return "";
  const table =
    scriptType === "mystery"
      ? MYSTERY_PHASES
      : scriptType === "emotional"
        ? EMOTIONAL_PHASES
        : DEFAULT_PHASES;
  return table[currentAct] ?? "";
}
