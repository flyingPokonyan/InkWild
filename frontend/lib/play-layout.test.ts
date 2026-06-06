import assert from "node:assert/strict";

import { getDrawerMode, shouldOffsetTimelineForDrawer } from "./play-layout.ts";

test("desktop drawer stays docked so the story timeline remains scrollable", () => {
  assert.equal(getDrawerMode(1440), "docked");
  assert.equal(getDrawerMode(1280), "docked");
});

test("mobile drawer becomes modal", () => {
  assert.equal(getDrawerMode(1024), "modal");
  assert.equal(getDrawerMode(820), "modal");
  assert.equal(getDrawerMode(390), "modal");
});

test("overlay drawer no longer offsets the story timeline", () => {
  assert.equal(shouldOffsetTimelineForDrawer(true, "docked"), false);
  assert.equal(shouldOffsetTimelineForDrawer(true, "modal"), false);
  assert.equal(shouldOffsetTimelineForDrawer(false, "docked"), false);
});
