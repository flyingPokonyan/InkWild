const DEFAULT_NEXT_PATH = "/history";

function sanitizeNextPath(path: string | null | undefined, fallback: string = DEFAULT_NEXT_PATH): string {
  if (!path) {
    return fallback;
  }

  if (!path.startsWith("/") || path.startsWith("//")) {
    return fallback;
  }

  if (path.startsWith("/login")) {
    return fallback;
  }

  return path;
}

export function buildLoginHref(nextPath: string | null | undefined): string {
  const resolved = sanitizeNextPath(nextPath);
  return `/login?next=${encodeURIComponent(resolved)}`;
}

export function resolveAuthNextPath(nextPath: string | null | undefined): string {
  return sanitizeNextPath(nextPath);
}
