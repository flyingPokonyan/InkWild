import assert from "node:assert/strict";

import { extractSSEBlocks } from "./sse-parser.ts";

test("extractSSEBlocks splits CRLF-delimited SSE events", () => {
  const payload =
    'event: session_created\r\ndata: {"type":"session_created","session_id":"sess-1"}\r\n\r\n' +
    'event: error\r\ndata: {"type":"error","code":50001,"message":"boom"}\r\n\r\n';

  const { blocks, rest } = extractSSEBlocks(payload);

  assert.equal(rest, "");
  assert.equal(blocks.length, 2);
  assert.match(blocks[0], /session_created/);
  assert.match(blocks[1], /"type":"error"/);
});
