/**
 * returnTo 透传：让「进入 play / 世界」的来源在退出时被尊重。
 *
 * 设计：用 query param `?return=<path>` 把来源路径逐跳带过去
 * （工坊试玩 → /worlds/[id] → /worlds/[id]/start → /play/[id]），
 * 退出时解析它，缺省回首页。只接受站内白名单路径，挡掉开放重定向。
 */

// 允许作为 return 落点的前缀。play 退出大多回这几个面。
const SAFE_PREFIXES = ["/workshop", "/discover", "/history", "/me", "/worlds"];

/** 校验并归一 return 值；非法（外链、协议相对、不在白名单）一律返回 null。 */
export function sanitizeReturn(raw: string | null | undefined): string | null {
  if (!raw) return null;
  let v = raw;
  try {
    v = decodeURIComponent(raw);
  } catch {
    // 解码失败说明值被污染，直接判废
    return null;
  }
  if (!v.startsWith("/") || v.startsWith("//")) return null; // 仅站内绝对路径
  return SAFE_PREFIXES.some((p) => v === p || v.startsWith(`${p}?`) || v.startsWith(`${p}/`))
    ? v
    : null;
}

/** 解析退出落点：合法 return 优先，否则用 fallback（默认首页）。 */
export function resolveExitHref(raw: string | null | undefined, fallback = "/"): string {
  return sanitizeReturn(raw) ?? fallback;
}

/** 给 href 追加 `?return=`（已带 query 时用 &）；return 非法则原样返回。 */
export function withReturn(href: string, ret: string | null | undefined): string {
  const safe = sanitizeReturn(ret);
  if (!safe) return href;
  const sep = href.includes("?") ? "&" : "?";
  return `${href}${sep}return=${encodeURIComponent(safe)}`;
}
