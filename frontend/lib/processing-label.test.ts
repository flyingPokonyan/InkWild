import assert from "node:assert/strict";

import { resolveProcessingLabel } from "./processing-label.ts";
import type { ProcessingEventPayload } from "./types.ts";

// Fake translator: echoes key (+ interpolated values) so we can assert the mapping.
function t(key: string, values?: Record<string, string>): string {
  return values ? `${key}:${Object.values(values).join(",")}` : key;
}
const p = (partial: Partial<ProcessingEventPayload>) => partial as unknown as ProcessingEventPayload;

test("casting stage maps to the casting label", () => {
  assert.equal(resolveProcessingLabel(p({ stage: "casting" }), t, "zh"), "processing.casting");
});

test("received / writing map directly", () => {
  assert.equal(resolveProcessingLabel(p({ stage: "received" }), t, "zh"), "processing.received");
  assert.equal(resolveProcessingLabel(p({ stage: "writing" }), t, "zh"), "processing.writing");
});

test("npcs_entering joins names with the locale separator", () => {
  assert.equal(
    resolveProcessingLabel(p({ stage: "npcs_entering", npcs: ["皇后", "华妃"] }), t, "zh"),
    "processing.npcsEntering:皇后、华妃",
  );
  assert.equal(
    resolveProcessingLabel(p({ stage: "npcs_entering", npcs: ["Queen", "Hua"] }), t, "en"),
    "processing.npcsEntering:Queen, Hua",
  );
  // No names → generic reasoning.
  assert.equal(
    resolveProcessingLabel(p({ stage: "npcs_entering", npcs: [] }), t, "zh"),
    "processing.reasoningGeneric",
  );
});

test("reasoning uses summary when present, else generic", () => {
  assert.equal(
    resolveProcessingLabel(p({ stage: "reasoning", input_summary: "查案" }), t, "zh"),
    "processing.reasoning:查案",
  );
  assert.equal(resolveProcessingLabel(p({ stage: "reasoning" }), t, "zh"), "processing.reasoningGeneric");
});

test("no stage falls back to verbatim flavor; null → empty", () => {
  assert.equal(resolveProcessingLabel(p({ flavor: "夜色四合" }), t, "zh"), "夜色四合");
  assert.equal(resolveProcessingLabel(null, t, "zh"), "");
});
