/**
 * Discover page URL state management.
 *
 * URL params:
 *   ?q=<query>       — search (takes precedence)
 *   ?cat=<slug>      — category filter (English slug)
 *
 * Both are mutually exclusive in the URL — when query is present, cat is ignored.
 */

export const DESKTOP_CATEGORIES = [
  { label: "全部", slug: "all" },
  { label: "剧本", slug: "script" },
  { label: "悬疑", slug: "mystery" },
  { label: "情感", slug: "emotion" },
  { label: "奇幻", slug: "fantasy" },
  { label: "科幻", slug: "scifi" },
  { label: "古风", slug: "classical" },
  { label: "现代", slug: "modern" },
] as const;

/** Chinese labels for rendering. */
export const CATEGORIES = DESKTOP_CATEGORIES.map((c) => c.label);

const slugToLabelMap = new Map<string, string>(DESKTOP_CATEGORIES.map((c) => [c.slug, c.label]));
const labelToSlugMap = new Map<string, string>(DESKTOP_CATEGORIES.map((c) => [c.label, c.slug]));

export function slugToLabel(slug: string | null): string {
  if (!slug) return "全部";
  return slugToLabelMap.get(slug) ?? "全部";
}

export function labelToSlug(label: string): string {
  return labelToSlugMap.get(label) ?? label.toLowerCase();
}

function normalizeCategory(raw: string | null): string {
  const label = slugToLabel(raw);
  return (CATEGORIES as readonly string[]).includes(label) ? label : "全部";
}

export interface UrlState {
  query: string;
  category: string;
}

export function readUrlState(): UrlState {
  if (typeof window === "undefined") return { query: "", category: "全部" };
  const params = new URLSearchParams(window.location.search);
  return {
    query: params.get("q") ?? "",
    category: normalizeCategory(params.get("cat")),
  };
}

export function writeUrlState(
  next: UrlState,
  mode: "push" | "replace",
): void {
  if (typeof window === "undefined") return;

  const params = new URLSearchParams();
  const q = next.query.trim();
  if (q) {
    params.set("q", q);
  } else if (next.category !== "全部") {
    params.set("cat", labelToSlug(next.category));
  }

  const queryString = params.toString();
  const url = `${window.location.pathname}${queryString ? `?${queryString}` : ""}`;
  window.history[mode === "push" ? "pushState" : "replaceState"]({}, "", url);
}
