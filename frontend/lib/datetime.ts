/**
 * 后端 datetime.isoformat() 输出的 timestamp 通常是 naive UTC（无时区标记），
 * 浏览器 new Date() 会按本地时间解析 → 时区不对（北京偏 8h）。
 * 这里检测末尾若无 Z / ±HH:MM 后缀，补 Z 强制当 UTC 处理。
 *
 * 所有解析后端返回的 ISO 字符串都走这个 helper。
 */

const HAS_TIMEZONE_RE = /(Z|[+-]\d{2}:\d{2})$/i;

export function parseBackendIso(iso: string | null | undefined): Date {
  if (!iso) return new Date(Number.NaN);
  const t = String(iso).trim();
  if (!t) return new Date(Number.NaN);
  return HAS_TIMEZONE_RE.test(t) ? new Date(t) : new Date(`${t}Z`);
}
