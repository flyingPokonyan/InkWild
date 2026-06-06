const DRAWER_PREFERENCE_KEY = "inkwild:play:drawer";

type DrawerPreference = "open" | "closed";

function isDrawerPreference(value: string | null | undefined): value is DrawerPreference {
  return value === "open" || value === "closed";
}

export function getInitialDrawerOpen(_width: number, stored?: string | null): boolean {
  // Default closed on entry (any width). The case board used to auto-open on
  // desktop, popping over the opening stage before there was anything to show.
  // Only honour an explicit prior preference to open it.
  if (isDrawerPreference(stored)) {
    return stored === "open";
  }

  return false;
}

export function readDrawerPreference(storage: Pick<Storage, "getItem"> | null): DrawerPreference | null {
  if (!storage) {
    return null;
  }

  const stored = storage.getItem(DRAWER_PREFERENCE_KEY);
  return isDrawerPreference(stored) ? stored : null;
}

export function writeDrawerPreference(storage: Pick<Storage, "setItem"> | null, open: boolean): void {
  if (!storage) {
    return;
  }

  storage.setItem(DRAWER_PREFERENCE_KEY, open ? "open" : "closed");
}
