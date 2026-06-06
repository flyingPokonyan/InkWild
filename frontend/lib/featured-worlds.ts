/**
 * 精选世界挑选逻辑 —— 登录页左栏 + discover spotlight 共用，保证两处口径一致。
 * 默认按 play_count 降序，并把运营置顶世界固定排在第一位。
 */

// 运营临时置顶：把「后宫·甄嬛传」钉在精选第一位（用户拍板 2026-06-02）。
// TODO: 长期应由后台「运营位 / featured 标记」配置，而非前端硬编码 world id。
export const FEATURED_PIN_WORLD_ID = "e9c87a8e-cde7-4229-9c4f-02d764c2a197";

export function pickFeaturedWorlds<T extends { id: string; play_count?: number | null }>(
  worlds: readonly T[] | undefined | null,
  count: number,
  pinId: string | null = FEATURED_PIN_WORLD_ID,
): T[] {
  if (!worlds || worlds.length === 0) return [];
  const ranked = [...worlds].sort((a, b) => (b.play_count ?? 0) - (a.play_count ?? 0));
  const limit = Math.min(count, ranked.length);
  if (!pinId) return ranked.slice(0, limit);

  const pinned = ranked.find((w) => w.id === pinId);
  if (!pinned) return ranked.slice(0, limit);

  return [pinned, ...ranked.filter((w) => w.id !== pinId)].slice(0, limit);
}
