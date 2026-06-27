/**
 * World ranking, deduplication, and play-count utilities for the discover page.
 */

import type { WorldListItem } from "@/lib/types";

/** Score a world by metadata completeness + play count. */
export function worldCompletenessScore(world: WorldListItem): number {
  return (
    (world.play_count || 0) * 100 +
    (world.hero_image ? 16 : 0) +
    (world.cover_image ? 12 : 0) +
    (world.description ? Math.min(world.description.length, 160) / 8 : 0) +
    (world.genre ? 4 : 0) +
    (world.era ? 4 : 0)
  );
}

/** Hot-score: play-count weighted + completeness tiebreaker. */
export function worldHotScore(world: WorldListItem): number {
  return (world.play_count || 0) * 1000 + worldCompletenessScore(world);
}

/** De-duplicate worlds by id. */
export function uniqueWorlds(worlds: WorldListItem[]): WorldListItem[] {
  const seen = new Set<string>();
  return worlds.filter((w) => {
    if (seen.has(w.id)) return false;
    seen.add(w.id);
    return true;
  });
}

/** Collect world ids into a Set, plus optional extra ids. */
export function idsOf(
  worlds: WorldListItem[],
  extraIds: Array<string | undefined> = [],
): Set<string> {
  const ids = new Set(worlds.map((w) => w.id));
  extraIds.forEach((id) => {
    if (id) ids.add(id);
  });
  return ids;
}

/** Filter out worlds whose id is in the given Set. */
export function excludeWorldIds(
  worlds: WorldListItem[],
  ids: Set<string>,
): WorldListItem[] {
  return worlds.filter((w) => !ids.has(w.id));
}

/** Concatenate primary + fallback, de-duplicate, slice to limit. */
export function takeRowWorlds(
  primary: WorldListItem[],
  fallback: WorldListItem[],
  limit = 8,
): WorldListItem[] {
  return uniqueWorlds([...primary, ...fallback]).slice(0, limit);
}

/** Format play count for display: 1.2万 / 3.5k / 42. */
export function formatPlayCount(count: number): string {
  if (count >= 10000) return `${(count / 10000).toFixed(1).replace(/\.0$/, "")}万`;
  if (count >= 1000) return `${(count / 1000).toFixed(1).replace(/\.0$/, "")}k`;
  return String(count);
}

/** Deterministic pseudo-random play count from a seed string (for worlds with 0 plays). */
export function mockPlayCount(seed: string): number {
  let hash = 0;
  for (let i = 0; i < seed.length; i += 1) {
    hash = (hash * 31 + seed.charCodeAt(i)) >>> 0;
  }
  return (hash % 200) + 1;
}
