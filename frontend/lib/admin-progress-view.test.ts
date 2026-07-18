import assert from "node:assert/strict";

import type { AdminPhaseEntry } from "./admin-progress-state.ts";
import {
  buildAdminLoadingSnapshot,
  computeWeightedProgress,
  formatClock,
  MAX_VISIBLE_ADMIN_FEEDBACK,
} from "./admin-progress-view.ts";

function makeEntry(overrides: Partial<AdminPhaseEntry>): AdminPhaseEntry {
  return {
    id: overrides.id || crypto.randomUUID(),
    phase: overrides.phase || "boot",
    code: overrides.code || "session_started",
    message: overrides.message || "已收到生成请求，正在建立创作会话…",
    kind: overrides.kind || "progress",
    status: overrides.status || "running",
    stageLabel: overrides.stageLabel,
  };
}

test("buildAdminLoadingSnapshot limits history to the latest visible entries", () => {
  const phases = [
    makeEntry({ id: "entry-0", phase: "boot", code: "session_started", message: "反馈 0", status: "done" }),
    makeEntry({ id: "entry-1", phase: "world_base", code: "started", message: "反馈 1", status: "done" }),
    makeEntry({ id: "entry-2", phase: "characters", code: "started", message: "反馈 2", status: "done" }),
    makeEntry({ id: "entry-3", phase: "playable", code: "started", message: "反馈 3", status: "done" }),
    makeEntry({ id: "entry-4", phase: "images", code: "started", message: "反馈 4", status: "done" }),
    makeEntry({ id: "entry-5", phase: "validating", code: "started", message: "反馈 5", status: "running" }),
  ];

  const snapshot = buildAdminLoadingSnapshot(phases);

  assert.equal(snapshot.history.length, MAX_VISIBLE_ADMIN_FEEDBACK - 1);
  assert.equal(snapshot.history[0]?.message, "反馈 1");
  assert.equal(snapshot.current?.message, "反馈 5");
});

test("buildAdminLoadingSnapshot prefers human-friendly stage labels", () => {
  const snapshot = buildAdminLoadingSnapshot([
    makeEntry({
      phase: "research",
      code: "searching",
      message: "正在为世界框架检索外部资料…",
      stageLabel: "世界框架",
    }),
  ]);

  assert.equal(snapshot.current?.label, "资料研判 · 世界框架");
  assert.equal(snapshot.current?.stackLabel, "世界框架");
  assert.equal(snapshot.current?.headline, "正在为世界框架检索外部资料…");
});

test("buildAdminLoadingSnapshot collapses repeated research labels in history", () => {
  const snapshot = buildAdminLoadingSnapshot([
    makeEntry({
      id: "boot",
      phase: "boot",
      code: "agent_ready",
      message: "生成引擎已接入",
      status: "done",
    }),
    makeEntry({
      id: "r1",
      phase: "research",
      code: "analysis_started",
      message: "先判断剧本框架要不要补资料",
      stageLabel: "剧本框架",
      status: "done",
    }),
    makeEntry({
      id: "r2",
      phase: "research",
      code: "analysis_pulse",
      message: "正在梳理剧本框架缺哪类资料",
      stageLabel: "剧本框架",
      status: "running",
    }),
  ]);

  assert.deepEqual(
    snapshot.history.map((entry) => entry.stackLabel),
    ["创作会话"],
  );
  assert.equal(snapshot.current?.label, "资料研判 · 剧本框架");
});

test("buildAdminLoadingSnapshot provides a stable fallback when no feedback exists", () => {
  const snapshot = buildAdminLoadingSnapshot([]);

  assert.equal(snapshot.history.length, 0);
  assert.equal(snapshot.current?.label, "创作会话");
  assert.equal(snapshot.current?.headline, "正在建立生成连接…");
});

test("computeWeightedProgress advances when later milestones appear inside the same phase", () => {
  const early = computeWeightedProgress([
    makeEntry({ id: "boot", phase: "boot", code: "agent_ready", status: "done" }),
    makeEntry({ id: "s1", phase: "script_base", code: "started", message: "正在构思剧本框架和核心秘密…", status: "running" }),
  ]);

  const later = computeWeightedProgress([
    makeEntry({ id: "boot", phase: "boot", code: "agent_ready", status: "done" }),
    makeEntry({ id: "s1", phase: "script_base", code: "started", message: "正在构思剧本框架和核心秘密…", status: "done" }),
    makeEntry({ id: "s2", phase: "script_base", code: "drafting_pulse", message: "主线已经起稿，正在收束核心秘密和调查入口…", status: "running" }),
  ]);

  assert.ok(later > early, `expected later milestone progress (${later}) to exceed early progress (${early})`);
});

test("computeWeightedProgress does not jump near completion when playable finishes before the main branch", () => {
  const progress = computeWeightedProgress([
    makeEntry({ id: "boot", phase: "boot", code: "agent_ready", status: "done" }),
    makeEntry({ id: "base", phase: "script_base", code: "completed", status: "done" }),
    makeEntry({ id: "playable", phase: "playable", code: "completed", status: "done" }),
  ]);

  assert.ok(progress < 50, `expected parallel playable completion to stay below 50%, got ${progress}`);
});

test("computeWeightedProgress keeps advancing during critic review", () => {
  const beforeCritic = computeWeightedProgress([
    makeEntry({ id: "boot", phase: "boot", code: "agent_ready", status: "done" }),
    makeEntry({ id: "base", phase: "script_base", code: "completed", status: "done" }),
    makeEntry({ id: "events", phase: "events", code: "completed", status: "done" }),
    makeEntry({ id: "endings", phase: "endings", code: "completed", status: "done" }),
    makeEntry({ id: "playable", phase: "playable", code: "review_completed", status: "done" }),
  ]);

  const duringCritic = computeWeightedProgress([
    makeEntry({ id: "boot", phase: "boot", code: "agent_ready", status: "done" }),
    makeEntry({ id: "base", phase: "script_base", code: "completed", status: "done" }),
    makeEntry({ id: "events", phase: "events", code: "completed", status: "done" }),
    makeEntry({ id: "endings", phase: "endings", code: "completed", status: "done" }),
    makeEntry({ id: "playable", phase: "playable", code: "review_completed", status: "done" }),
    makeEntry({ id: "critic", phase: "critic", code: "review_pulse", status: "running" }),
  ]);

  assert.ok(duringCritic > beforeCritic, `expected critic review to add progress (${beforeCritic} -> ${duringCritic})`);
});

test("formatClock pads seconds", () => {
  assert.equal(formatClock(0), "0:00");
  assert.equal(formatClock(65), "1:05");
  assert.equal(formatClock(12 * 60 + 3), "12:03");
});
