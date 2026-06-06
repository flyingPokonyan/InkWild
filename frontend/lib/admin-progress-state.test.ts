import assert from "node:assert/strict";

import type { AdminProgressEvent } from "./admin-sse-events.ts";
import {
  appendAdminPhaseEvent,
  completeAdminPhaseTimeline,
  markLatestAdminPhaseAsError,
} from "./admin-progress-state.ts";

test("appendAdminPhaseEvent keeps same-phase updates as separate timeline entries", () => {
  const first: AdminProgressEvent = {
    phase: "research",
    code: "analysis_started",
    message: "先判断要不要补一点参考资料…",
    meta: { stage_label: "世界框架" },
  };
  const second: AdminProgressEvent = {
    phase: "research",
    code: "searching",
    message: "正在检索外部资料…",
    meta: { stage_label: "世界框架" },
  };

  const afterFirst = appendAdminPhaseEvent([], first);
  const afterSecond = appendAdminPhaseEvent(afterFirst, second);

  assert.equal(afterSecond.length, 2);
  assert.equal(afterSecond[0].phase, "research");
  assert.equal(afterSecond[0].code, "analysis_started");
  assert.equal(afterSecond[0].status, "done");
  assert.equal(afterSecond[1].phase, "research");
  assert.equal(afterSecond[1].code, "searching");
  assert.equal(afterSecond[1].status, "running");
  assert.equal(afterSecond[1].stageLabel, "世界框架");
});

test("appendAdminPhaseEvent stores warnings as non-fatal warning entries", () => {
  const warning: AdminProgressEvent = {
    phase: "images",
    code: "generation_failed",
    message: "插画生成未返回有效结果",
  };

  const phases = appendAdminPhaseEvent([], warning, "warning");

  assert.equal(phases.length, 1);
  assert.equal(phases[0].kind, "warning");
  assert.equal(phases[0].status, "warning");
});

test("completeAdminPhaseTimeline finalizes the latest running entry", () => {
  const phases = appendAdminPhaseEvent([], {
    phase: "boot",
    code: "agent_ready",
    message: "生成引擎已接入，马上开始拆解任务…",
  });

  const completed = completeAdminPhaseTimeline(phases);

  assert.equal(completed[0].status, "done");
});

test("markLatestAdminPhaseAsError only marks the latest running entry", () => {
  const afterFirst = appendAdminPhaseEvent([], {
    phase: "boot",
    code: "session_started",
    message: "已收到生成请求，正在建立创作会话…",
  });
  const phases = appendAdminPhaseEvent(afterFirst, {
    phase: "research",
    code: "searching",
    message: "正在检索外部资料…",
  });

  const failed = markLatestAdminPhaseAsError(phases);

  assert.equal(failed[0].status, "done");
  assert.equal(failed[1].status, "error");
});

import {
  applyEventToStages,
  hydrateStagesFromEvents,
} from "./admin-progress-state.ts";
import { initStagesMap } from "./admin-generation-stages.ts";
import type { AdminGenerationTaskEvent } from "./types.ts";

test("applyEventToStages: started transitions stage to running", () => {
  const prev = initStagesMap();
  const next = applyEventToStages(prev, {
    phase: "shared_events",
    code: "started",
    message: "",
    meta: { stage_index: 6, total_stages: 14 },
  });
  assert.equal(next.get("shared_events")?.status, "running");
  assert.ok(next.get("shared_events")?.startedAt);
});

test("applyEventToStages: completed carries payloadSummary and completedMeta", () => {
  const prev = initStagesMap();
  const afterStart = applyEventToStages(prev, {
    phase: "shared_events",
    code: "started",
    message: "",
    meta: {},
  });
  const afterDone = applyEventToStages(afterStart, {
    phase: "shared_events",
    code: "completed",
    message: "",
    meta: {
      duration_ms: 12345,
      payload_summary: { event_count: 12 },
      sample: ["科举舞弊案", "安禄山入长安"],
    },
  });
  assert.equal(afterDone.get("shared_events")?.status, "completed");
  assert.equal(afterDone.get("shared_events")?.payloadSummary?.event_count, 12);
});

test("applyEventToStages: subtask_completed appends to recentItems (last 3, FIFO)", () => {
  let map = initStagesMap();
  for (const name of ["李白", "杜甫", "王维", "岑参"]) {
    map = applyEventToStages(map, {
      phase: "characters",
      code: "subtask_completed",
      message: "",
      meta: {
        payload_summary: { name, role_tag: "诗人" },
        subtask_index: 0,
        subtask_total: 12,
      },
    });
  }
  const items = map.get("characters")?.recentItems ?? [];
  assert.equal(items.length, 3);
  assert.deepEqual(items, ["杜甫·诗人", "王维·诗人", "岑参·诗人"]);
});

test("applyEventToStages: pulse events do NOT change stage status", () => {
  const prev = initStagesMap();
  const afterStart = applyEventToStages(prev, {
    phase: "shared_events",
    code: "started",
    message: "",
    meta: {},
  });
  const afterPulse = applyEventToStages(afterStart, {
    phase: "shared_events",
    code: "pulse",
    message: "正在编织共享历史…",
    meta: {},
  });
  assert.equal(afterPulse.get("shared_events")?.status, "running");
});

test("hydrateStagesFromEvents replays historical events into a fresh map", () => {
  const events: AdminGenerationTaskEvent[] = [
    { event: "progress", payload: { phase: "research_pack", code: "started", meta: {} } },
    {
      event: "progress",
      payload: {
        phase: "research_pack",
        code: "completed",
        meta: { duration_ms: 1000, payload_summary: {} },
      },
    },
    { event: "progress", payload: { phase: "shared_events", code: "started", meta: {} } },
  ] as unknown as AdminGenerationTaskEvent[];

  const map = hydrateStagesFromEvents(events);
  assert.equal(map.get("research_pack")?.status, "completed");
  assert.equal(map.get("shared_events")?.status, "running");
  assert.equal(map.get("characters")?.status, "pending");
});

test("hydrateStagesFromEvents: error event marks any running stage as failed", () => {
  const events: AdminGenerationTaskEvent[] = [
    { event: "progress", payload: { phase: "shared_events", code: "started", meta: {} } },
    { event: "error", payload: { phase: "shared_events", message: "boom" } },
  ] as unknown as AdminGenerationTaskEvent[];

  const map = hydrateStagesFromEvents(events);
  assert.equal(map.get("shared_events")?.status, "failed");
});
