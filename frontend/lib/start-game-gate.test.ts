import assert from "node:assert/strict";

import { createStartGameGate } from "./start-game-gate.ts";

test("方案 A：session_created 只记录，不放行导航（仍 pending）", async () => {
  const gate = createStartGameGate();

  gate.markSessionCreated("sess-1");

  // 与一个立即兑现的 Promise 竞速：若 gate 已 settle 会先返回，否则 pending 分支胜出。
  const winner = await Promise.race([
    gate.promise.then(() => "settled"),
    Promise.resolve("pending"),
  ]);
  assert.equal(winner, "pending");
});

test("markReady 放行导航并返回 sessionId（内容就绪 → 跳 play）", async () => {
  const gate = createStartGameGate();

  gate.markSessionCreated("sess-1");
  gate.markReady();

  assert.equal(await gate.promise, "sess-1");
});

test("done 兜底：未显式 ready 时仍按已创建 session 放行", async () => {
  const gate = createStartGameGate();

  gate.markSessionCreated("sess-1");
  gate.markDone();

  assert.equal(await gate.promise, "sess-1");
});

test("内容就绪前出错：resolve null（留在 setup 页报错，不导航）", async () => {
  const gate = createStartGameGate();

  gate.markSessionCreated("sess-1");
  gate.markError();

  assert.equal(await gate.promise, null);
});

test("session_created 前出错：resolve null", async () => {
  const gate = createStartGameGate();

  gate.markError();

  assert.equal(await gate.promise, null);
});

test("ready 之后再 error 是 no-op（已放行）", async () => {
  const gate = createStartGameGate();

  gate.markSessionCreated("sess-1");
  gate.markReady();
  gate.markError();

  assert.equal(await gate.promise, "sess-1");
});
