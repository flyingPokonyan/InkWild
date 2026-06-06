import assert from "node:assert/strict";

import { parseBackendIso } from "./datetime.ts";

test("parseBackendIso treats naive ISO timestamps as UTC", () => {
  const parsed = parseBackendIso("2026-04-14T09:00:00");

  assert.equal(parsed.toISOString(), "2026-04-14T09:00:00.000Z");
});

test("parseBackendIso preserves explicit UTC offsets", () => {
  const parsed = parseBackendIso("2026-04-14T09:00:00Z");

  assert.equal(parsed.toISOString(), "2026-04-14T09:00:00.000Z");
});

test("parseBackendIso preserves explicit numeric offsets", () => {
  const parsed = parseBackendIso("2026-04-14T17:00:00+08:00");

  assert.equal(parsed.toISOString(), "2026-04-14T09:00:00.000Z");
});

test("parseBackendIso returns invalid Date for empty/null", () => {
  assert.equal(Number.isNaN(parseBackendIso("").getTime()), true);
  assert.equal(Number.isNaN(parseBackendIso(null).getTime()), true);
  assert.equal(Number.isNaN(parseBackendIso(undefined).getTime()), true);
});
