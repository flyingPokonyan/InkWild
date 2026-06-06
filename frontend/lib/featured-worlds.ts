/**
 * 精选世界挑选逻辑 —— 登录页左栏 + discover spotlight 共用，保证两处口径一致。
 *
 * 「每周精选」：按「自纪元起的周序号」对所有已发布世界做确定性轮播。
 * 同一周内稳定（全站一致），跨周自动换一批 / 换顺序，无需后台手动维护置顶。
 */

const WEEK_MS = 7 * 24 * 60 * 60 * 1000;

/** 自 epoch 起的周序号（确定性整数，跨周递增）。 */
export function currentWeekIndex(now: number = Date.now()): number {
  return Math.floor(now / WEEK_MS);
}

/**
 * 取本周精选世界：以 id 稳定排序得到基序，再按周序号旋转起点取前 count 个。
 * 世界多于 count 时每周展示不同子集；少于等于 count 时则每周轮换顺序。
 */
export function pickFeaturedWorlds<T extends { id: string }>(
  worlds: readonly T[] | undefined | null,
  count: number,
  weekIndex: number = currentWeekIndex(),
): T[] {
  if (!worlds || worlds.length === 0) return [];
  const ordered = [...worlds].sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
  const n = ordered.length;
  const limit = Math.min(count, n);
  const offset = ((weekIndex % n) + n) % n;
  const rotated = [...ordered.slice(offset), ...ordered.slice(0, offset)];
  return rotated.slice(0, limit);
}
