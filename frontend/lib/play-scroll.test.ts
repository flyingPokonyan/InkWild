import assert from "node:assert/strict";

import {
  isNearBottom,
  shouldAutoFollow,
  shouldShowJumpToLatest,
} from "./play-scroll.ts";

test("timeline auto-follows only when the reader is near the bottom", () => {
  const nearBottom = {
    scrollTop: 904,
    scrollHeight: 1600,
    clientHeight: 640,
  };
  const awayFromBottom = {
    scrollTop: 620,
    scrollHeight: 1600,
    clientHeight: 640,
  };

  assert.equal(isNearBottom(nearBottom), true);
  assert.equal(shouldAutoFollow(nearBottom, "streaming"), true);
  assert.equal(isNearBottom(awayFromBottom), false);
  assert.equal(shouldAutoFollow(awayFromBottom, "streaming"), false);
});

test("jump-to-latest appears when the reader is away from the bottom", () => {
  assert.equal(
    shouldShowJumpToLatest({
      scrollTop: 620,
      scrollHeight: 1600,
      clientHeight: 640,
    }),
    true,
  );
  assert.equal(
    shouldShowJumpToLatest({
      scrollTop: 912,
      scrollHeight: 1600,
      clientHeight: 640,
    }),
    false,
  );
});

test("processing and streaming updates share the same bottom-threshold logic", () => {
  const metrics = {
    scrollTop: 620,
    scrollHeight: 1600,
    clientHeight: 640,
  };

  assert.equal(shouldAutoFollow(metrics, "processing"), false);
  assert.equal(shouldAutoFollow(metrics, "streaming"), false);
});
