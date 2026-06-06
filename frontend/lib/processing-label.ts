import type { ProcessingEventPayload } from "./types";

/**
 * Resolve a processing milestone into its display label. Shared by the in-stage
 * thinking rail (StreamingStatusRail) and the full-screen entry loader
 * (GameLoadingScreen) so the opening shows the same real milestones
 * (体察态度 / 接收行动 / 谁进场 / 落笔) instead of a generic "正在加载".
 *
 * Returns "" when there's no milestone yet (breathing state — show logo only).
 */
export function resolveProcessingLabel(
  processing: ProcessingEventPayload | null | undefined,
  t: (key: string, values?: Record<string, string>) => string,
  locale: string,
): string {
  switch (processing?.stage) {
    case "casting":
      return t("processing.casting");
    case "received":
      return t("processing.received");
    case "reasoning": {
      const summary = (processing.input_summary || "").trim();
      return summary ? t("processing.reasoning", { summary }) : t("processing.reasoningGeneric");
    }
    case "npcs_entering": {
      const names = (processing.npcs || []).filter(Boolean);
      if (!names.length) return t("processing.reasoningGeneric");
      const sep = locale.startsWith("zh") ? "、" : ", ";
      return t("processing.npcsEntering", { names: names.join(sep) });
    }
    case "writing":
      return t("processing.writing");
    default:
      // v1 legacy path still sends a composed `flavor`; show it verbatim.
      return (processing?.flavor || "").trim();
  }
}
