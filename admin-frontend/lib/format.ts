/** Format ISO datetime to "YYYY-MM-DD HH:mm:ss" in 北京时间 (Asia/Shanghai, UTC+8).
 *
 * Backend writes naive UTC datetimes (no tzinfo, serialized as
 * "2026-05-19T09:03:59.376819"). The browser would otherwise interpret a
 * suffix-less ISO as local time, so we explicitly tag it UTC before formatting.
 * If the string already carries a tz marker (Z / +HH:MM / -HH:MM), respect it.
 */
const _ISO_TZ_RE = /(Z|[+-]\d{2}:?\d{2})$/;

export function fmtDateTime(iso: string): string {
  const normalized = _ISO_TZ_RE.test(iso) ? iso : `${iso}Z`;
  const d = new Date(normalized);
  // zh-CN locale with explicit Beijing tz, formatted YYYY-MM-DD HH:mm:ss
  const parts = new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).formatToParts(d);
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? "";
  return `${get("year")}-${get("month")}-${get("day")} ${get("hour")}:${get("minute")}:${get("second")}`;
}

/** Returns ISO start of "now minus N days" at 00:00 local time. */
export function daysAgoIso(n: number): string {
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  d.setDate(d.getDate() - n);
  return d.toISOString();
}

/** Returns ISO start of today (00:00 local time). */
export function todayStartIso(): string {
  return daysAgoIso(0);
}

/** Initials for avatar — up to 2 chars uppercase. */
export function initials(name: string | null | undefined): string {
  if (!name) return "?";
  return name.slice(0, 2).toUpperCase();
}

/** Map an internal generation phase code to a human-readable Chinese label.
 * Falls back to the raw code when unknown — keeps debuggability while pretty
 * up the common cases admins actually see.
 */
const _PHASE_LABELS: Record<string, string> = {
  boot: "启动会话",
  ip_recognition: "IP 识别",
  ip_research: "原作锚点抽取",
  research_pack: "研究素材",
  world_base: "世界框架",
  lore_dimensions: "世界维度",
  character_roster: "人物阵容",
  lore_pack: "世界设定",
  characters: "角色档案",
  shared_events: "共享历史事件",
  relations_pack: "关系网",
  events_data: "事件数据",
  playable: "可玩角色",
  critic: "质检 / 复审",
  visual_brief: "视觉构思",
  images: "图片生成",
  validating: "数据校验",
  // script-side
  script_base: "剧本框架",
  events: "事件编排",
  endings: "结局设计",
  script_visual_brief: "剧本视觉构思",
  script_images: "剧本海报",
};

export function phaseLabel(code: string | null | undefined): string {
  if (!code) return "—";
  return _PHASE_LABELS[code] ?? code;
}

/** Stable color from a string (for avatar backgrounds). */
export function colorFromString(s: string): string {
  const palette = [
    "#7B5CFF",
    "#D97757",
    "#10A37F",
    "#4285F4",
    "#0EA5E9",
    "#EC4899",
    "#F59E0B",
    "#8B5CF6",
  ];
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0;
  return palette[h % palette.length];
}
