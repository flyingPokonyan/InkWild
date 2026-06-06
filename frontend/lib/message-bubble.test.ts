import assert from "node:assert/strict";

import { getMessageTone } from "./message-bubble.ts";

test("narrator messages have narrator tone", () => {
  assert.equal(getMessageTone("narrator"), "narrator");
});

test("user messages have player tone", () => {
  assert.equal(getMessageTone("user"), "player");
});
