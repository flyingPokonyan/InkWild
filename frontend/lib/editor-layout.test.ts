import assert from "node:assert/strict";

import {
  getEditorLayoutMode,
  getEditorRailStickyTop,
  type EditorLayoutMode,
} from "./editor-layout.ts";

test("editor layout stays single column until desktop rail has room", () => {
  const cases: Array<[number, EditorLayoutMode]> = [
    [375, "narrow"],
    [767, "narrow"],
    [1023, "narrow"],
    [1024, "rail"],
    [1279, "rail"],
    [1280, "split"],
  ];

  for (const [width, expected] of cases) {
    assert.equal(getEditorLayoutMode(width), expected);
  }
});

test("mobile section rail sits below the two-row editor strip", () => {
  assert.equal(
    getEditorRailStickyTop("narrow"),
    "calc(112px + env(safe-area-inset-top, 0px))",
  );
  assert.equal(getEditorRailStickyTop("rail"), 88);
  assert.equal(getEditorRailStickyTop("split"), 88);
});
