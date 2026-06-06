export interface PlayScrollMetrics {
  scrollTop: number;
  scrollHeight: number;
  clientHeight: number;
}

export type TimelineUpdateKind = "processing" | "streaming";

export const PLAY_TIMELINE_BOTTOM_THRESHOLD = 96;

export function isNearBottom(
  metrics: PlayScrollMetrics,
  threshold = PLAY_TIMELINE_BOTTOM_THRESHOLD,
): boolean {
  const distanceFromBottom = metrics.scrollHeight - (metrics.scrollTop + metrics.clientHeight);
  return distanceFromBottom <= threshold;
}

export function shouldAutoFollow(
  metrics: PlayScrollMetrics,
  _updateKind: TimelineUpdateKind,
  threshold = PLAY_TIMELINE_BOTTOM_THRESHOLD,
): boolean {
  return isNearBottom(metrics, threshold);
}

export function shouldShowJumpToLatest(
  metrics: PlayScrollMetrics,
  threshold = PLAY_TIMELINE_BOTTOM_THRESHOLD,
): boolean {
  return !isNearBottom(metrics, threshold);
}
