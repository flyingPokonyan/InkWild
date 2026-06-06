// Safe enum-key lookup for case_board fields where Director output may
// drift from the canonical enum (e.g. emits Chinese labels like "高" /
// "极高" instead of "high"). Returns the localized label if the enum key
// exists; otherwise returns the raw value so the user sees something
// sensible rather than a missing-message console error.

type Translator = {
  (key: string): string;
  has?: (key: string) => boolean;
};

export function tEnum(
  t: Translator,
  namespace: string,
  value: string | undefined | null,
): string {
  if (!value) return "";
  const key = `${namespace}.${value}`;
  // next-intl provides t.has() on the returned function in v3+.
  if (typeof t.has === "function" && !t.has(key)) {
    return value;
  }
  try {
    return t(key);
  } catch {
    return value;
  }
}
