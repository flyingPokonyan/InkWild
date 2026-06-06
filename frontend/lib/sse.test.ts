import assert from "node:assert/strict";

import { streamAction, type SSEError } from "./sse.ts";

const textEncoder = new TextEncoder();

function sseResponse(payload: string, init: ResponseInit = { status: 200 }): Response {
  return new Response(
    new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(textEncoder.encode(payload));
        controller.close();
      },
    }),
    init,
  );
}

test("streamAction rejects mismatched SSE schema versions without crashing", async () => {
  const originalFetch = globalThis.fetch;
  const errors: SSEError[] = [];
  let doneCount = 0;

  globalThis.fetch = async () =>
    sseResponse('event: narrative\ndata: {"version":2,"text":"hello"}\n\n');

  try {
    await streamAction("/api/game/session/action", { action_text: "look" }, {
      onError: (error) => errors.push(error),
      onDone: () => {
        doneCount += 1;
      },
    });

    assert.equal(errors.length, 1);
    assert.equal(errors[0]?.code, "unknown");
    assert.match(errors[0]?.message || "", /SSE.*版本.*1/);
    assert.equal(doneCount, 1);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("streamAction surfaces malformed SSE JSON as a readable stream error", async () => {
  const originalFetch = globalThis.fetch;
  const errors: SSEError[] = [];
  let doneCount = 0;

  globalThis.fetch = async () => sseResponse('event: narrative\ndata: {"text":\n\n');

  try {
    await streamAction("/api/game/session/action", { action_text: "look" }, {
      onError: (error) => errors.push(error),
      onDone: () => {
        doneCount += 1;
      },
    });

    assert.equal(errors.length, 1);
    assert.equal(errors[0]?.code, "unknown");
    assert.match(errors[0]?.message || "", /SSE.*解析失败/);
    assert.equal(doneCount, 1);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("streamAction dispatches cost guardrail events", async () => {
  const originalFetch = globalThis.fetch;
  const capEvents: Array<{ message: string; suggest?: string }> = [];
  const errors: SSEError[] = [];
  let doneCount = 0;

  globalThis.fetch = async () =>
    sseResponse(
      'event: cap_reached\ndata: {"version":1,"message":"费用达到上限","suggest":"ending"}\n\n'
      + 'event: done\ndata: {"version":1}\n\n',
    );

  try {
    await streamAction("/api/game/session/action", { action_text: "look" }, {
      onCapReached: (event) => capEvents.push(event),
      onError: (error) => errors.push(error),
      onDone: () => {
        doneCount += 1;
      },
    });

    assert.deepEqual(capEvents, [{ message: "费用达到上限", suggest: "ending" }]);
    assert.equal(errors.length, 1);
    assert.equal(errors[0]?.code, "cost_cap");
    assert.equal(errors[0]?.message, "费用达到上限");
    assert.equal(doneCount, 1);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("streamAction maps typed SSE error codes from backend payloads", async () => {
  const originalFetch = globalThis.fetch;
  const errors: SSEError[] = [];

  globalThis.fetch = async () =>
    sseResponse(
      'event: error\ndata: {"version":1,"code":"llm_timeout","message":"LLM 调用超时"}\n\n'
      + 'event: done\ndata: {"version":1}\n\n',
    );

  try {
    await streamAction("/api/game/session/action", { action_text: "look" }, {
      onError: (error) => errors.push(error),
    });

    assert.deepEqual(errors, [{ code: "llm_timeout", message: "LLM 调用超时", retryAfterMs: undefined }]);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("streamAction normalises unknown error codes to 'unknown'", async () => {
  const originalFetch = globalThis.fetch;
  const errors: SSEError[] = [];

  globalThis.fetch = async () =>
    sseResponse(
      'event: error\ndata: {"version":1,"code":"weird_code","message":"x"}\n\n'
      + 'event: done\ndata: {"version":1}\n\n',
    );

  try {
    await streamAction("/api/game/session/action", { action_text: "look" }, {
      onError: (error) => errors.push(error),
    });

    assert.equal(errors.length, 1);
    assert.equal(errors[0]?.code, "unknown");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("streamAction propagates retry_after_ms from rate_limit payloads", async () => {
  const originalFetch = globalThis.fetch;
  const errors: SSEError[] = [];

  globalThis.fetch = async () =>
    sseResponse(
      'event: error\ndata: {"version":1,"code":"rate_limit","message":"操作过于频繁","retry_after_ms":5000}\n\n'
      + 'event: done\ndata: {"version":1}\n\n',
    );

  try {
    await streamAction("/api/game/session/action", { action_text: "look" }, {
      onError: (error) => errors.push(error),
    });

    assert.deepEqual(errors, [
      { code: "rate_limit", message: "操作过于频繁", retryAfterMs: 5000 },
    ]);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("streamAction maps HTTP 429 to rate_limit with Retry-After header", async () => {
  const originalFetch = globalThis.fetch;
  const errors: SSEError[] = [];

  globalThis.fetch = async () =>
    new Response(
      JSON.stringify({ detail: { code: 42902, message: "操作过于频繁，请稍后再试" } }),
      { status: 429, headers: { "Retry-After": "3", "Content-Type": "application/json" } },
    );

  try {
    await streamAction("/api/game/session/action", { action_text: "look" }, {
      onError: (error) => errors.push(error),
    });

    assert.equal(errors.length, 1);
    assert.equal(errors[0]?.code, "rate_limit");
    assert.equal(errors[0]?.message, "操作过于频繁，请稍后再试");
    assert.equal(errors[0]?.retryAfterMs, 3000);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("streamAction ignores SSE comment heartbeat lines", async () => {
  const originalFetch = globalThis.fetch;
  const errors: SSEError[] = [];
  const narratives: string[] = [];
  let doneCount = 0;

  globalThis.fetch = async () =>
    sseResponse(
      ': heartbeat\n\n'
      + ':hb\n\n'
      + 'event: narrative\ndata: {"version":1,"text":"x"}\n\n'
      + 'event: done\ndata: {"version":1}\n\n',
    );

  try {
    await streamAction("/api/game/session/action", { action_text: "look" }, {
      onNarrative: (text) => narratives.push(text),
      onError: (error) => errors.push(error),
      onDone: () => {
        doneCount += 1;
      },
    });

    assert.deepEqual(narratives, ["x"]);
    assert.deepEqual(errors, []);
    assert.equal(doneCount, 1);
  } finally {
    globalThis.fetch = originalFetch;
  }
});
