import assert from "node:assert/strict";

import {
  getInitialDrawerOpen,
  readDrawerPreference,
  writeDrawerPreference,
} from "./play-preferences.ts";

class MemoryStorage {
  private store = new Map<string, string>();

  getItem(key: string) {
    return this.store.get(key) ?? null;
  }

  setItem(key: string, value: string) {
    this.store.set(key, value);
  }
}

test("defaults drawer to closed on entry regardless of width", () => {
  assert.equal(getInitialDrawerOpen(1440, null), false);
  assert.equal(getInitialDrawerOpen(1024, null), false);
});

test("stored preference overrides default", () => {
  assert.equal(getInitialDrawerOpen(1440, "closed"), false);
  assert.equal(getInitialDrawerOpen(900, "open"), true);
});

test("invalid stored preference falls back to closed", () => {
  assert.equal(getInitialDrawerOpen(1440, "bad-value"), false);
  assert.equal(getInitialDrawerOpen(900, "bad-value"), false);
});

test("read and write drawer preference round-trip", () => {
  const storage = new MemoryStorage();

  assert.equal(readDrawerPreference(storage), null);

  writeDrawerPreference(storage, true);
  assert.equal(readDrawerPreference(storage), "open");

  writeDrawerPreference(storage, false);
  assert.equal(readDrawerPreference(storage), "closed");
});
