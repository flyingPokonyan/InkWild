# Generation Feedback Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the "0/12 stuck after refresh" bug, replace generic per-stage labels with rich activity feedback (counts + samples + recent items), and add heartbeat pulses to long single-LLM stages so the loading screen never appears frozen.

**Architecture:**
- Frontend: extract a single shared stage module (`admin-generation-stages.ts`) consumed by both `DraftEditorShell` and `GenerationLoadingScreen`; lift `stages` Map state-machine logic into a pure function so hydrate + live SSE share one path; add a per-stage formatter that picks samples / recent items.
- Backend: enrich `completed` event meta with `sample` arrays and per-stage extras (`clue_count`, `repair_count`, `cover_count`, `avatar_count`, `dim_label`, `title`, `label`); add an `_run_with_pulse` async-generator helper that interleaves periodic `pulse` progress events with the underlying LLM call; apply to 5 long-single-LLM stages.

**Tech Stack:** TypeScript + React 19 (vitest, jsdom), Python 3.12 async + pytest, SSE.

**Spec:** `docs/superpowers/specs/2026-05-12-generation-feedback-design.md`

**Repo note:** the working tree at `/Users/jie/Desktop/code/pokonyan/talealive` is not currently a git repo (`git rev-parse` fails). Skip `git commit` steps; landing each task = file changes + passing tests is enough. The user can integrate with their VCS afterward.

---

## File Structure

**New files:**
- `frontend/lib/admin-generation-stages.ts` — single source of truth: `StageKey`, `StageStatus`, `StageState`, `STAGE_LIST`, `STAGE_LABELS`, `initStagesMap()`, `extractSubtaskItem()`, `formatStageLine()`
- `frontend/lib/admin-generation-stages.test.ts` — table-driven tests for formatter + extractor

**Modified frontend:**
- `frontend/components/admin/editor/DraftEditorShell.tsx` — delete duplicated stage table, import from shared; switch SSE handler to shared `applyEventToStages`; call `hydrateStagesFromEvents` in `loadDraft()`
- `frontend/components/admin/GenerationLoadingScreen.tsx` — delete local `STAGE_LIST` / `StageState` / `StageStatus`, import from shared; render formatter output with single-line CSS truncation
- `frontend/lib/admin-progress-state.ts` — add `applyEventToStages` (pure state-machine over one event) + `hydrateStagesFromEvents` (fold over historical events)
- `frontend/lib/admin-progress-state.test.ts` — new tests for the two new functions
- `frontend/lib/admin-progress-view.ts` — add `pulse: 0.5` to `PHASE_CODE_PROGRESS` for the 5 wrapped stages
- `frontend/lib/admin-sse-events.ts` — extend `ProgressMeta` with new optional fields (`sample`, `clue_count`, `repair_count`, `cover_count`, `avatar_count`, `edge_count`, `dim_label`, `title`, `label`, `world_name`, `dimension_count`, `role_count`, `event_count`, `character_count`, `npc_count`, `location_count`)

**Modified backend:**
- `backend/services/world_creator_agent_v2.py` — add `_run_with_pulse` helper; enrich `completed` and key `subtask_completed` event meta; wrap 5 long stages with pulse
- `backend/services/generation_feedback.py` — add 5 `(phase, "pulse")` templates; update `("characters","completed")`, `("shared_events","completed")`, etc. templates to use new meta keys gracefully (existing keys keep working)

**Modified backend tests:**
- `backend/tests/test_generation_feedback.py` — add pulse template tests
- `backend/tests/test_world_creator_v2_entry.py` — add tests for enriched meta + pulse helper

---

## Task 1: Create shared stage module (foundation)

**Files:**
- Create: `frontend/lib/admin-generation-stages.ts`
- Create: `frontend/lib/admin-generation-stages.test.ts`

- [ ] **Step 1.1: Write the failing test** — create `frontend/lib/admin-generation-stages.test.ts`:

```ts
import assert from "node:assert/strict";

import {
  STAGE_LIST,
  STAGE_LABELS,
  initStagesMap,
  type StageKey,
} from "./admin-generation-stages.ts";

test("STAGE_LIST is in backend _STAGE_INDEX order (excluding visual_brief and validating)", () => {
  const expected: StageKey[] = [
    "research_pack",
    "world_base",
    "lore_dimensions",
    "character_roster",
    "lore_pack",
    "characters",
    "shared_events",
    "relations_pack",
    "events_data",
    "playable",
    "critic",
    "images",
  ];
  assert.deepEqual(
    STAGE_LIST.map((s) => s.key),
    expected,
  );
});

test("STAGE_LABELS covers every stage key", () => {
  for (const { key } of STAGE_LIST) {
    assert.equal(typeof STAGE_LABELS[key], "string");
    assert.ok(STAGE_LABELS[key].length > 0);
  }
});

test("initStagesMap returns Map with every stage in pending state and empty recentItems", () => {
  const map = initStagesMap();
  assert.equal(map.size, STAGE_LIST.length);
  for (const { key } of STAGE_LIST) {
    const state = map.get(key);
    assert.ok(state);
    assert.equal(state.status, "pending");
    assert.deepEqual(state.recentItems, []);
  }
});
```

- [ ] **Step 1.2: Run test to verify it fails**

Run from `frontend/`: `npm test -- admin-generation-stages`
Expected: FAIL with "Cannot find module './admin-generation-stages.ts'"

- [ ] **Step 1.3: Create the module** — write `frontend/lib/admin-generation-stages.ts`:

```ts
import type { ProgressMeta } from "./admin-sse-events";

// Stage key union, ordered to match backend services/world_creator_agent_v2.py _STAGE_INDEX
// (visual_brief is folded into the images entry visually; validating is post-process and not shown).
export type StageKey =
  | "research_pack"
  | "world_base"
  | "lore_dimensions"
  | "character_roster"
  | "lore_pack"
  | "characters"
  | "shared_events"
  | "relations_pack"
  | "events_data"
  | "playable"
  | "critic"
  | "images";

export type StageStatus = "pending" | "running" | "completed" | "failed";

export interface StageState {
  status: StageStatus;
  startedAt?: number;
  completedAt?: number;
  subtaskTotal?: number;
  subtaskDone?: number;
  payloadSummary?: ProgressMeta["payload_summary"];
  /** Last completed_meta carried alongside the `completed` event for richer summaries. */
  completedMeta?: ProgressMeta;
  /** Recent subtask item labels, FIFO, keep last 3. */
  recentItems: string[];
}

export const STAGE_LIST: Array<{ key: StageKey; label: string }> = [
  { key: "research_pack", label: "收集研究素材" },
  { key: "world_base", label: "构建世界基础" },
  { key: "lore_dimensions", label: "扩展世界维度" },
  { key: "character_roster", label: "规划角色阵容" },
  { key: "lore_pack", label: "生成世界设定" },
  { key: "characters", label: "创建角色档案" },
  { key: "shared_events", label: "设计共享事件" },
  { key: "relations_pack", label: "构建角色关系" },
  { key: "events_data", label: "生成事件数据" },
  { key: "playable", label: "可玩性校验" },
  { key: "critic", label: "品质审核" },
  { key: "images", label: "生成配图" },
];

export const STAGE_LABELS: Record<StageKey, string> = STAGE_LIST.reduce(
  (acc, { key, label }) => {
    acc[key] = label;
    return acc;
  },
  {} as Record<StageKey, string>,
);

export const STAGE_KEYS: ReadonlyArray<StageKey> = STAGE_LIST.map((s) => s.key);

export function initStagesMap(): Map<StageKey, StageState> {
  return new Map(
    STAGE_LIST.map(({ key }) => [key, { status: "pending" as const, recentItems: [] }]),
  );
}

/** Returns true iff `value` is one of the known StageKeys. */
export function isStageKey(value: string): value is StageKey {
  return (STAGE_KEYS as readonly string[]).includes(value);
}
```

- [ ] **Step 1.4: Run test to verify it passes**

Run from `frontend/`: `npm test -- admin-generation-stages`
Expected: 3 passing.

---

## Task 2: Migrate DraftEditorShell + GenerationLoadingScreen to shared module

**Files:**
- Modify: `frontend/components/admin/editor/DraftEditorShell.tsx:23-57`
- Modify: `frontend/components/admin/editor/DraftEditorShell.tsx:139` (state init)
- Modify: `frontend/components/admin/editor/DraftEditorShell.tsx:385-403` (derived stage values)
- Modify: `frontend/components/admin/GenerationLoadingScreen.tsx:21-47` (delete local types + STAGE_LIST)

This task is a pure refactor with **zero behavior change** — existing tests must still pass.

- [ ] **Step 2.1: Update `GenerationLoadingScreen.tsx` — replace local exports with imports**

In `frontend/components/admin/GenerationLoadingScreen.tsx`:

Delete lines 21-47 (`StageStatus`, `StageState`, `STAGE_LIST`).

Add at the top (after the existing `import { buildAdminLoadingSnapshot ...}` line):

```ts
import {
  STAGE_LIST,
  type StageKey,
  type StageState,
  type StageStatus,
} from "@/lib/admin-generation-stages";
```

Update the `stages` prop type on `GenerationLoadingScreenProps` (around line 64):

```ts
stages?: Map<StageKey, StageState>;
```

Update `stagesCompleted` derived (around line 89):

```ts
const stagesCompleted = stages
  ? Array.from(stages.values()).filter((s) => s.status === "completed").length
  : 0;
```

This remains the same — but verify no `import` of the now-deleted local types remains.

Re-export the types from this file (for any other admin code that may import from here — back-compat):

```ts
export type { StageKey, StageState, StageStatus } from "@/lib/admin-generation-stages";
```

- [ ] **Step 2.2: Update `DraftEditorShell.tsx` — delete local table, import from shared**

In `frontend/components/admin/editor/DraftEditorShell.tsx`:

Delete lines 23-57 (`STAGE_KEYS`, `STAGE_LABEL_ZH`, `initStagesMap`).

Replace with imports:

```ts
import {
  initStagesMap,
  STAGE_KEYS,
  STAGE_LABELS,
  type StageKey,
  type StageState,
} from "@/lib/admin-generation-stages";
```

Remove the existing `import { GenerationLoadingScreen, type StageState } from "@/components/admin/GenerationLoadingScreen";` line — keep only `import { GenerationLoadingScreen } from "@/components/admin/GenerationLoadingScreen";` since `StageState` now comes from `admin-generation-stages`.

Update state init (line 139):

```ts
const [stages, setStages] = useState<Map<StageKey, StageState>>(initStagesMap);
```

Update `currentStageInfo` (around line 390):

```ts
const currentStageInfo = useMemo(() => {
  for (const key of STAGE_KEYS) {
    const state = stages.get(key);
    if (state?.status === "running") {
      return {
        key,
        label: STAGE_LABELS[key],
        subtaskTotal: state.subtaskTotal,
        subtaskDone: state.subtaskDone,
      };
    }
  }
  return null;
}, [stages]);
```

In the SSE handler (line 218-243), update the fallback default so `recentItems` is always present:

```ts
const existing: StageState = next.get(phase as StageKey) ?? {
  status: "pending" as const,
  recentItems: [],
};
```

(Task 3 will extract this into a shared function — for now just ensure the local code initializes the new field.)

- [ ] **Step 2.3: Run frontend test suite — should be all green**

Run from `frontend/`: `npm test`
Expected: all existing tests pass (this is a non-behavioral refactor). The new `admin-generation-stages.test.ts` tests also pass.

- [ ] **Step 2.4: Run `npm run lint`**

Run from `frontend/`: `npm run lint`
Expected: zero new lint errors. (If existing project has warnings, they remain unchanged.)

---

## Task 3: Extract `applyEventToStages` + `hydrateStagesFromEvents` (fixes 0/12 bug)

**Files:**
- Modify: `frontend/lib/admin-progress-state.ts`
- Modify: `frontend/lib/admin-progress-state.test.ts`
- Modify: `frontend/components/admin/editor/DraftEditorShell.tsx:170-178` (call hydrate in loadDraft)
- Modify: `frontend/components/admin/editor/DraftEditorShell.tsx:218-243` (delegate to applyEventToStages)

- [ ] **Step 3.1: Write failing tests** — append to `frontend/lib/admin-progress-state.test.ts`:

```ts
import {
  applyEventToStages,
  hydrateStagesFromEvents,
} from "./admin-progress-state.ts";
import { initStagesMap, type StageKey } from "./admin-generation-stages.ts";
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

test("applyEventToStages: completed carries payloadSummary + completedMeta", () => {
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
      // @ts-expect-error sample is a new optional field added by Task 6 plumbing
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
      meta: { payload_summary: { name, role_tag: "诗人" }, subtask_index: 0, subtask_total: 12 },
    });
  }
  const items = map.get("characters")?.recentItems ?? [];
  assert.equal(items.length, 3);
  assert.deepEqual(items, ["杜甫·诗人", "王维·诗人", "岑参·诗人"]);
});

test("hydrateStagesFromEvents replays historical events into a fresh map", () => {
  const events: AdminGenerationTaskEvent[] = [
    { event: "progress", payload: { phase: "research_pack", code: "started", meta: {} } },
    { event: "progress", payload: { phase: "research_pack", code: "completed", meta: { duration_ms: 1000, payload_summary: {} } } },
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
```

- [ ] **Step 3.2: Run tests to verify they fail**

Run from `frontend/`: `npm test -- admin-progress-state`
Expected: FAIL with "applyEventToStages is not a function" and "hydrateStagesFromEvents is not a function".

- [ ] **Step 3.3: Add `extractSubtaskItem` to the shared stage module first** (Step 3.4's `applyEventToStages` imports it)

Append to `frontend/lib/admin-generation-stages.ts`:

```ts
/**
 * Extracts a single display-ready item label from a subtask_completed event's meta.
 * Returns null when the meta does not contain a recognizable identifier for that stage.
 *
 * Stage → field mapping (see backend services/world_creator_agent_v2.py):
 * - characters: payload_summary.name (+ optional · role_tag)
 * - lore_pack: payload_summary.dim_label
 * - events_data: payload_summary.title
 * - images: payload_summary.label
 */
export function extractSubtaskItem(
  stage: StageKey,
  meta: ProgressMeta | undefined,
): string | null {
  const summary = meta?.payload_summary as Record<string, unknown> | undefined;
  if (!summary) return null;

  switch (stage) {
    case "characters": {
      const name = typeof summary.name === "string" ? summary.name : null;
      const role = typeof summary.role_tag === "string" && summary.role_tag.length > 0
        ? summary.role_tag
        : null;
      if (!name) return null;
      return role ? `${name}·${role}` : name;
    }
    case "lore_pack":
      return typeof summary.dim_label === "string" ? summary.dim_label : null;
    case "events_data":
      return typeof summary.title === "string" ? summary.title : null;
    case "images":
      return typeof summary.label === "string" ? summary.label : null;
    default:
      return null;
  }
}
```

- [ ] **Step 3.4: Implement `applyEventToStages` + `hydrateStagesFromEvents`**

Append to `frontend/lib/admin-progress-state.ts`:

```ts
import {
  extractSubtaskItem,
  initStagesMap,
  isStageKey,
  type StageKey,
  type StageState,
} from "./admin-generation-stages";

const COMPLETED_CODES = new Set([
  "completed",
  "repair_completed",
  "review_adjusted",
  "review_completed",
]);

/**
 * Pure reducer: applies one progress/warning event to the stages map,
 * returning a new Map. Shared by live SSE handling and `hydrateStagesFromEvents`.
 *
 * Pulse events (`code === "pulse"`) do NOT change stage status — they only
 * drive the headline timeline. We early-return the map unchanged.
 */
export function applyEventToStages(
  prev: Map<StageKey, StageState>,
  event: AdminProgressEvent,
): Map<StageKey, StageState> {
  if (!event.phase || !isStageKey(event.phase)) return prev;
  if (event.code === "pulse") return prev;

  const phase = event.phase;
  const meta = event.meta;
  const next = new Map(prev);
  const existing: StageState =
    next.get(phase) ?? { status: "pending", recentItems: [] };

  if (event.code === "started") {
    next.set(phase, {
      ...existing,
      status: "running",
      startedAt: existing.startedAt ?? Date.now(),
      subtaskTotal: meta?.subtask_total ?? existing.subtaskTotal,
    });
    return next;
  }

  if (COMPLETED_CODES.has(event.code)) {
    next.set(phase, {
      ...existing,
      status: "completed",
      completedAt: Date.now(),
      payloadSummary: meta?.payload_summary ?? existing.payloadSummary,
      completedMeta: meta ?? existing.completedMeta,
    });
    return next;
  }

  if (event.code === "subtask_started") {
    next.set(phase, {
      ...existing,
      subtaskTotal: meta?.subtask_total ?? existing.subtaskTotal,
    });
    return next;
  }

  if (event.code === "subtask_completed") {
    const prevDone = existing.subtaskDone ?? 0;
    const nextDone =
      meta?.subtask_index !== undefined
        ? Math.max(prevDone, meta.subtask_index + 1)
        : prevDone + 1;
    const item = extractSubtaskItem(phase, meta);
    const nextRecentItems = item
      ? [...existing.recentItems, item].slice(-3)
      : existing.recentItems;
    next.set(phase, {
      ...existing,
      subtaskTotal: meta?.subtask_total ?? existing.subtaskTotal,
      subtaskDone: nextDone,
      recentItems: nextRecentItems,
      payloadSummary: meta?.payload_summary ?? existing.payloadSummary,
    });
    return next;
  }

  return next;
}

/**
 * Marks any currently-running stage as failed.
 * Used when an error event arrives during hydrate or live SSE.
 */
export function markRunningStagesFailed(
  prev: Map<StageKey, StageState>,
): Map<StageKey, StageState> {
  const next = new Map(prev);
  for (const [key, state] of next) {
    if (state.status === "running") {
      next.set(key, { ...state, status: "failed" });
    }
  }
  return next;
}

/**
 * Replays a historical event list into a fresh stages Map.
 * Mirror of `hydrateAdminPhaseTimeline` for the stages state machine —
 * fixes the "0/12 stuck after refresh" bug.
 */
export function hydrateStagesFromEvents(
  events: AdminGenerationTaskEvent[],
): Map<StageKey, StageState> {
  let map = initStagesMap();
  for (const evt of events) {
    if (evt.event === "progress" || evt.event === "warning") {
      const payload = evt.payload as {
        phase?: string;
        code?: string;
        message?: string;
        meta?: ProgressMeta;
      };
      map = applyEventToStages(map, {
        phase: String(payload.phase || ""),
        code: String(payload.code || ""),
        message: String(payload.message || ""),
        meta: payload.meta,
      });
    } else if (evt.event === "error") {
      map = markRunningStagesFailed(map);
    }
  }
  return map;
}
```

Also add the type import at the top of the file (alongside existing imports):

```ts
import type { AdminGenerationTaskEvent } from "./types";
```

(`AdminGenerationTaskEvent` and `AdminProgressEvent` are already used in the file; verify imports are correct.)

- [ ] **Step 3.5: Run tests to verify they pass**

Run from `frontend/`: `npm test -- admin-progress-state admin-generation-stages`
Expected: all green.

- [ ] **Step 3.6: Wire hydrate into `DraftEditorShell.tsx:170-178`**

In `loadDraft()`:

```ts
setPhases(
  result.generation_task ? hydrateAdminPhaseTimeline(result.generation_task.events) : [],
);
setStages(
  result.generation_task
    ? hydrateStagesFromEvents(result.generation_task.events)
    : initStagesMap(),
);
```

Add `hydrateStagesFromEvents` to the import from `@/lib/admin-progress-state`.

- [ ] **Step 3.7: Replace live SSE handler stage logic with `applyEventToStages`**

In `DraftEditorShell.tsx`, the existing inline `setStages((prev) => { ... })` blocks at lines 218-243 and 251-259 collapse to:

```ts
onProgress: (e: AdminProgressEvent) => {
  setPhases((prev) => appendAdminPhaseEvent(prev, e));
  setStages((prev) => applyEventToStages(prev, e));
},
onWarning: (e: AdminProgressEvent) => {
  setPhases((prev) => appendAdminPhaseEvent(prev, e, "warning"));
  setStages((prev) => applyEventToStages(prev, e));
},
onError: (message) => {
  setError(message);
  setPhases((prev) => markLatestAdminPhaseAsError(prev));
  setStages((prev) => markRunningStagesFailed(prev));
},
```

Add `applyEventToStages` and `markRunningStagesFailed` to the existing `import { ... } from "@/lib/admin-progress-state"`.

- [ ] **Step 3.8: Smoke-test refresh fix manually (or note for executing-plans review)**

Start the dev server (`cd frontend && npm run dev`) and the backend, kick off a generation, wait for the agent to be mid-`shared_events`, refresh the page. The 12-stage panel should now reflect "research_pack ✓ · world_base ✓ · … · shared_events ●" — not 0/12 all-pending.

(This is a manual visual check; no automated test for it. If unable to run servers, the unit tests in Step 3.1 cover the same logic.)

- [ ] **Step 3.9: Run full frontend test suite**

Run from `frontend/`: `npm test`
Expected: all green.

---

## Task 4: Add `formatStageLine` per-stage formatter

**Files:**
- Modify: `frontend/lib/admin-generation-stages.ts` (append `formatStageLine`)
- Modify: `frontend/lib/admin-generation-stages.test.ts` (append formatter tests)

- [ ] **Step 4.1: Write failing tests** — append to `admin-generation-stages.test.ts`:

```ts
import { formatStageLine } from "./admin-generation-stages.ts";

test("formatStageLine returns empty object for pending stage", () => {
  const result = formatStageLine("characters", { status: "pending", recentItems: [] });
  assert.deepEqual(result, {});
});

test("formatStageLine.running uses recentItems for subtask stages", () => {
  const result = formatStageLine("characters", {
    status: "running",
    recentItems: ["李白·诗人", "杜甫·诗人"],
  });
  assert.equal(result.running, "刚生成：李白·诗人、杜甫·诗人");
});

test("formatStageLine.running fallback when recentItems is empty (subtask stages)", () => {
  const result = formatStageLine("characters", { status: "running", recentItems: [] });
  assert.equal(result.running, "正在创建角色档案…");
});

test("formatStageLine.running returns undefined for stages driven by pulse (no recentItems)", () => {
  const result = formatStageLine("shared_events", { status: "running", recentItems: [] });
  assert.equal(result.running, undefined);
});

test("formatStageLine.completed renders characters summary with sample + total", () => {
  const result = formatStageLine("characters", {
    status: "completed",
    recentItems: [],
    completedMeta: {
      payload_summary: { character_count: 12 },
      // @ts-expect-error sample is a new optional field
      sample: ["李白", "杜甫", "王维"],
    },
  });
  assert.equal(result.completed, "12 位 · 李白、杜甫、王维 等");
});

test("formatStageLine.completed renders events_data summary with clues", () => {
  const result = formatStageLine("events_data", {
    status: "completed",
    recentItems: [],
    completedMeta: {
      payload_summary: { event_count: 8 },
      // @ts-expect-error new optional fields
      clue_count: 12,
      sample: ["朱雀街刺杀案", "月夜会客厅"],
    },
  });
  assert.equal(result.completed, "8 事件 · 12 线索 · 朱雀街刺杀案、月夜会客厅");
});

test("formatStageLine.completed renders images split", () => {
  const result = formatStageLine("images", {
    status: "completed",
    recentItems: [],
    completedMeta: {
      // @ts-expect-error new optional fields
      cover_count: 1,
      avatar_count: 13,
    },
  });
  assert.equal(result.completed, "1 主图 · 13 头像");
});

test("formatStageLine.completed renders critic pass vs repair", () => {
  const pass = formatStageLine("critic", {
    status: "completed",
    recentItems: [],
    completedMeta: { payload_summary: {} },
  });
  assert.equal(pass.completed, "通过");

  const repair = formatStageLine("critic", {
    status: "completed",
    recentItems: [],
    completedMeta: {
      // @ts-expect-error new optional fields
      repair_count: 3,
    },
  });
  assert.equal(repair.completed, "修正 3 处");
});

test("formatStageLine.completed gracefully degrades when meta is missing", () => {
  const result = formatStageLine("characters", {
    status: "completed",
    recentItems: [],
  });
  assert.equal(result.completed, undefined);
});
```

- [ ] **Step 4.2: Run tests to verify they fail**

Run from `frontend/`: `npm test -- admin-generation-stages`
Expected: FAIL with "formatStageLine is not a function".

- [ ] **Step 4.3: Implement `formatStageLine`**

Append to `frontend/lib/admin-generation-stages.ts`:

```ts
type CompletedFormatter = (meta: ProgressMeta) => string | undefined;

const RUNNING_LINES: Partial<Record<StageKey, (state: StageState) => string | undefined>> = {
  characters: (s) =>
    s.recentItems.length > 0
      ? `刚生成：${s.recentItems.slice(-2).join("、")}`
      : "正在创建角色档案…",
  lore_pack: (s) =>
    s.recentItems.length > 0
      ? `刚补完：${s.recentItems.slice(-2).join("、")}`
      : "正在补全世界设定…",
  events_data: (s) =>
    s.recentItems.length > 0
      ? `刚设计事件：${s.recentItems.slice(-2).join("、")}`
      : "正在编排事件链…",
  images: (s) =>
    s.recentItems.length > 0
      ? `刚画完：${s.recentItems.slice(-2).join("、")}`
      : "正在生成配图…",
  // research_pack / world_base / lore_dimensions / character_roster /
  // shared_events / relations_pack / playable / critic intentionally return
  // undefined here — their narrative is carried by pulse events in the headline.
};

function joinSample(meta: ProgressMeta): string {
  const sample = (meta as { sample?: unknown }).sample;
  if (!Array.isArray(sample)) return "";
  return sample.filter((s) => typeof s === "string" && s.length > 0).join("、");
}

function num(meta: ProgressMeta, key: string): number | undefined {
  const summary = meta.payload_summary as Record<string, unknown> | undefined;
  const candidate = summary?.[key] ?? (meta as Record<string, unknown>)[key];
  return typeof candidate === "number" ? candidate : undefined;
}

function str(meta: ProgressMeta, key: string): string | undefined {
  const summary = meta.payload_summary as Record<string, unknown> | undefined;
  const candidate = summary?.[key] ?? (meta as Record<string, unknown>)[key];
  return typeof candidate === "string" ? candidate : undefined;
}

const COMPLETED_LINES: Partial<Record<StageKey, CompletedFormatter>> = {
  research_pack: (m) => {
    const n = num(m, "artifact_count");
    const sample = joinSample(m);
    if (n === undefined && !sample) return undefined;
    return [n !== undefined ? `${n} 条素材` : null, sample || null]
      .filter(Boolean)
      .join(" · ");
  },
  world_base: (m) => {
    const name = str(m, "world_name");
    const n = num(m, "location_count");
    const sample = joinSample(m);
    const head = name ?? "世界";
    if (n === undefined && !sample) return head;
    const tail = sample
      ? `${sample}${n !== undefined && n > 3 ? ` 等 ${n} 地` : ""}`
      : `${n} 地`;
    return `${head} · ${tail}`;
  },
  lore_dimensions: (m) => {
    const n = num(m, "dimension_count");
    const sample = joinSample(m);
    if (n === undefined && !sample) return undefined;
    return [n !== undefined ? `${n} 维度` : null, sample || null]
      .filter(Boolean)
      .join(" · ");
  },
  character_roster: (m) => {
    const n = num(m, "role_count");
    const sample = joinSample(m);
    if (n === undefined && !sample) return undefined;
    return [n !== undefined ? `${n} 位身份` : null, sample || null]
      .filter(Boolean)
      .join(" · ");
  },
  lore_pack: (m) => {
    const n = num(m, "dimension_count");
    const sample = joinSample(m);
    if (n === undefined && !sample) return undefined;
    return [n !== undefined ? `${n} 维度补全` : null, sample || null]
      .filter(Boolean)
      .join(" · ");
  },
  characters: (m) => {
    const n = num(m, "character_count");
    const sample = joinSample(m);
    if (n === undefined) return undefined;
    return sample ? `${n} 位 · ${sample} 等` : `${n} 位`;
  },
  shared_events: (m) => {
    const n = num(m, "event_count");
    const sample = joinSample(m);
    if (n === undefined && !sample) return undefined;
    return [n !== undefined ? `${n} 段历史` : null, sample || null]
      .filter(Boolean)
      .join(" · ");
  },
  relations_pack: (m) => {
    const npcs = num(m, "npc_count");
    const edges = num(m, "edge_count");
    if (npcs === undefined) return undefined;
    return edges !== undefined
      ? `${npcs} 位角色 · 共 ${edges} 条关系`
      : `${npcs} 位角色`;
  },
  events_data: (m) => {
    const n = num(m, "event_count");
    const clues = num(m, "clue_count");
    const sample = joinSample(m);
    if (n === undefined) return undefined;
    return [
      `${n} 事件`,
      clues !== undefined ? `${clues} 线索` : null,
      sample || null,
    ]
      .filter(Boolean)
      .join(" · ");
  },
  playable: (m) => {
    const n = num(m, "playable_count");
    const sample = joinSample(m);
    if (n === undefined && !sample) return undefined;
    return sample ? `选定 ${n ?? sample.split("、").length} 位 · ${sample}` : `选定 ${n} 位`;
  },
  critic: (m) => {
    const repair = num(m, "repair_count");
    if (repair !== undefined && repair > 0) return `修正 ${repair} 处`;
    return "通过";
  },
  images: (m) => {
    const cover = num(m, "cover_count");
    const avatar = num(m, "avatar_count");
    const total = num(m, "image_count");
    if (cover !== undefined || avatar !== undefined) {
      return [
        cover !== undefined ? `${cover} 主图` : null,
        avatar !== undefined ? `${avatar} 头像` : null,
      ]
        .filter(Boolean)
        .join(" · ");
    }
    return total !== undefined ? `${total} 张` : undefined;
  },
};

export function formatStageLine(
  stage: StageKey,
  state: StageState,
): { running?: string; completed?: string } {
  if (state.status === "running") {
    return { running: RUNNING_LINES[stage]?.(state) };
  }
  if (state.status === "completed") {
    const meta = state.completedMeta;
    if (!meta) return {};
    return { completed: COMPLETED_LINES[stage]?.(meta) };
  }
  return {};
}
```

- [ ] **Step 4.4: Run tests to verify they pass**

Run from `frontend/`: `npm test -- admin-generation-stages`
Expected: all green.

---

## Task 5: Render formatter output in `GenerationLoadingScreen` + enforce single-line

**Files:**
- Modify: `frontend/components/admin/GenerationLoadingScreen.tsx:301-379` (stage list `<li>` render)

- [ ] **Step 5.1: Update the `<li>` rendering to call `formatStageLine` and apply ellipsis CSS**

In `frontend/components/admin/GenerationLoadingScreen.tsx`, find the `STAGE_LIST.map(({ key, label }) => { ... })` block (around line 301) and replace it with:

```tsx
{STAGE_LIST.map(({ key, label }) => {
  const state = stages.get(key);
  const status: StageStatus = state?.status ?? "pending";

  const indicatorChar =
    status === "completed"
      ? "✓"
      : status === "running"
        ? "●"
        : status === "failed"
          ? "✕"
          : "○";

  const indicatorColor =
    status === "completed"
      ? "var(--lv-accent)"
      : status === "running"
        ? "var(--lv-warn)"
        : status === "failed"
          ? "var(--lv-danger)"
          : "var(--lv-ink-5)";

  const labelColor =
    status === "pending" ? "var(--lv-ink-4)" : "var(--lv-ink-2)";

  const line = state ? formatStageLine(key, state) : {};
  const subtaskCount =
    status === "running" && state?.subtaskTotal && state.subtaskTotal > 0
      ? `${state.subtaskDone ?? 0}/${state.subtaskTotal}`
      : null;

  return (
    <li
      key={key}
      className="lv-t-body"
      style={{
        display: "flex",
        alignItems: "center",
        gap: "var(--lv-s-2)",
        whiteSpace: "nowrap",
        overflow: "hidden",
        textOverflow: "ellipsis",
        minWidth: 0,
      }}
    >
      <span
        aria-hidden
        style={{
          fontFamily: "var(--lv-font-mono)",
          color: indicatorColor,
          width: "1em",
          flexShrink: 0,
          textAlign: "center",
        }}
      >
        {indicatorChar}
      </span>
      <span style={{ color: labelColor, flexShrink: 0 }}>{label}</span>
      {subtaskCount && (
        <span
          className="lv-t-meta"
          style={{ color: "var(--lv-ink-4)", flexShrink: 0 }}
        >
          · {subtaskCount}
        </span>
      )}
      {(line.running || line.completed) && (
        <span
          className="lv-t-meta"
          style={{
            color: "var(--lv-ink-4)",
            overflow: "hidden",
            textOverflow: "ellipsis",
            minWidth: 0,
            flex: "1 1 auto",
          }}
        >
          · {line.running || line.completed}
        </span>
      )}
    </li>
  );
})}
```

Add `formatStageLine` to the existing `import { ... } from "@/lib/admin-generation-stages"`.

- [ ] **Step 5.2: Run the existing GenerationLoadingScreen tests if any (none currently — note this)**

Run from `frontend/`: `npm test`
Expected: all green. The visual single-line behavior is verified manually (Step 5.4).

- [ ] **Step 5.3: Add a smoke test for the dev preview page**

Open `frontend/app/dev/loading-preview/page.tsx` to confirm it can still render with the new prop shape (it should — `StageState` is back-compat with the new optional fields). If it imports the old `StageState` type from `GenerationLoadingScreen.tsx`, that's fine — Task 2 added a re-export.

- [ ] **Step 5.4: Manual visual check**

`cd frontend && npm run dev`, navigate to `/dev/loading-preview` (or trigger a real generation). Verify:
- Each stage row stays single-line — narrow the viewport to 375px, the trailing info gets ellipsis, never wraps
- "● 创建角色档案 · 5/12 · 刚生成：李白·诗人、杜甫·诗人" looks balanced
- "✓ 创建角色档案 · 12 位 · 李白、杜甫、王维 等" after completion

---

## Task 6: Backend — enrich `completed` event meta

**Files:**
- Modify: `backend/services/world_creator_agent_v2.py` (multiple `progress_event(...)` call sites)
- Modify: `backend/tests/test_world_creator_v2_entry.py` (add assertions on new meta fields)

This task adds new optional fields to existing events. Frontend gracefully handles missing fields (Task 4 formatters all check for presence). Order: write the backend changes alongside test assertions in one logical pass since each event is small.

- [ ] **Step 6.1: Write failing test for enriched meta**

Append to `backend/tests/test_world_creator_v2_entry.py` (create the file if checking the existing one shows a different pattern — there's already `test_world_creator_v2_entry.py` in the tree per `ls`):

```python
import pytest
from unittest.mock import AsyncMock, MagicMock

from services.world_creator_agent_v2 import WorldCreatorAgentV2


async def _collect_events(agent_iter):
    out = []
    async for ev in agent_iter:
        out.append(ev)
    return out


@pytest.mark.asyncio
async def test_shared_events_completed_includes_sample_and_event_count(monkeypatch):
    """shared_events.completed should carry sample (event titles) + event_count."""
    # Use the real agent with mocked LLM router that returns fixed shared events
    # …construction omitted; reuse existing fixtures in this file…

    # The exact mock setup depends on existing fixtures. The assertion shape:
    # find the completed event for shared_events and assert:
    # - meta["event_count"] is an int
    # - meta["sample"] is a list of 2 strings (titles)

    # Skeleton (adapt to fixture conventions):
    # events = await _collect_events(agent._run_shared_events(...))
    # completed = [e for e in events if e.get("phase") == "shared_events" and e.get("code") == "completed"][0]
    # assert isinstance(completed["meta"]["event_count"], int)
    # assert isinstance(completed["meta"].get("sample"), list)
    # assert len(completed["meta"]["sample"]) <= 2
```

**NOTE for the implementer**: this test file already has agent fixtures — read it first and adapt. If the existing test patterns inject specific shared-events lists via mock, reuse them. The point is: assert `meta["sample"]` exists and is a 2-element string list on `shared_events.completed`.

Do the same skeleton for: `characters.completed.sample`, `events_data.completed.clue_count + sample`, `images.completed.cover_count + avatar_count`, `lore_pack.subtask_completed.dim_label`.

- [ ] **Step 6.2: Run tests — expect failures**

Run from `backend/`: `python -m pytest tests/test_world_creator_v2_entry.py -v -k "sample or clue_count or dim_label or cover_count"`
Expected: FAIL (new fields are missing from meta).

- [ ] **Step 6.3: Edit `world_creator_agent_v2.py` — enrich each event**

For each event listed below, add the indicated fields to the `progress_event(...)` kwargs. (Line numbers approximate from the file at time of writing — search by context.)

**`_run_world_base` completed event** (around line 380):

```python
yield progress_event(
    "world_base", "completed",
    stage_index=_STAGE_INDEX["world_base"],
    total_stages=TOTAL_STAGES,
    duration_ms=int((time.monotonic() - start) * 1000),
    world_name=world_base.get("name", ""),
    location_count=len(locations),
    sample=[loc.get("name", "") for loc in locations[:3] if isinstance(loc, dict) and loc.get("name")],
)
```

**`_run_lore_dimensions` completed event** (around line 471):

```python
yield progress_event(
    "lore_dimensions", "completed",
    stage_index=_STAGE_INDEX["lore_dimensions"],
    total_stages=TOTAL_STAGES,
    duration_ms=int((time.monotonic() - start) * 1000),
    dimension_count=len(lore_dimensions),
    sample=[d.label for d in lore_dimensions[:3] if getattr(d, "label", "")],
)
```

(If `lore_dimensions` items don't have `.label`, use `.key` or whatever the most human-readable string field is — confirm by inspecting the dataclass/model in the same file.)

**`_run_character_roster` completed event** (around line 514):

```python
yield progress_event(
    "character_roster", "completed",
    stage_index=_STAGE_INDEX["character_roster"],
    total_stages=TOTAL_STAGES,
    duration_ms=int((time.monotonic() - start) * 1000),
    role_count=len(roster),
    sample=[r.role_tag or r.name for r in roster[:3] if getattr(r, "role_tag", "") or getattr(r, "name", "")],
)
```

**`_run_lore_pack` subtask_completed** (line 598):

```python
yield progress_event(
    "lore_pack", "subtask_completed",
    subtask_key=f"dim:{dim.key}",
    subtask_index=completed_count,
    subtask_total=total_dims,
    payload_summary={
        "content_blocks": len(dim.content_blocks),
        "dim_label": getattr(dim, "label", "") or dim.key,
    },
)
```

**`_run_lore_pack` completed** (around line 611):

```python
yield progress_event(
    "lore_pack", "completed",
    stage_index=_STAGE_INDEX["lore_pack"],
    total_stages=TOTAL_STAGES,
    duration_ms=int((time.monotonic() - start) * 1000),
    dimension_count=len(pack.dimensions),
    sample=[getattr(d, "label", "") or d.key for d in pack.dimensions[:3] if getattr(d, "label", "") or getattr(d, "key", "")],
)
```

**`_run_characters` completed** (around line 670):

```python
yield progress_event(
    "characters", "completed",
    stage_index=_STAGE_INDEX["characters"],
    total_stages=TOTAL_STAGES,
    duration_ms=int((time.monotonic() - start) * 1000),
    character_count=len(characters),
    sample=[c.name for c in characters[:3] if c.name],
)
```

**`_run_shared_events` completed** (line 719):

```python
yield progress_event(
    "shared_events", "completed",
    stage_index=_STAGE_INDEX["shared_events"],
    total_stages=TOTAL_STAGES,
    duration_ms=int((time.monotonic() - start) * 1000),
    event_count=len(shared_events),
    sample=[ev.title for ev in shared_events[:2] if getattr(ev, "title", "")],
)
```

**`_run_relations_pack` completed** (line 750):

```python
edge_count = sum(len(rels) for rels in pack.relations_by_npc.values())
yield progress_event(
    "relations_pack", "completed",
    stage_index=_STAGE_INDEX["relations_pack"],
    total_stages=TOTAL_STAGES,
    duration_ms=int((time.monotonic() - start) * 1000),
    npc_count=len(pack.relations_by_npc),
    edge_count=edge_count,
)
```

**`_run_events_data` subtask_completed** (line 816):

```python
ev_title = getattr(ev, "title", None) or ""
yield progress_event(
    "events_data", "subtask_completed",
    subtask_key=f"event:{ev_id or i}",
    subtask_index=i + 1,
    subtask_total=target_count,
    payload_summary={"event_id": ev_id or str(i), "title": ev_title},
)
```

**`_run_events_data` completed** (line 824):

```python
clue_count = sum(len(getattr(ev, "clues", []) or []) for ev in events_data)
yield progress_event(
    "events_data", "completed",
    stage_index=_STAGE_INDEX["events_data"],
    total_stages=TOTAL_STAGES,
    duration_ms=int((time.monotonic() - start) * 1000),
    event_count=len(events_data),
    clue_count=clue_count,
    sample=[ev.title for ev in events_data[:2] if getattr(ev, "title", "")],
)
```

(If `EventDataEntry` doesn't have `.clues`, search for the closest equivalent — `evidence`, `leads`, etc. — and use that field. If no per-event clue concept exists, omit `clue_count` and the frontend formatter just won't render the `12 线索` segment.)

**`_run_playable` completed** (in `_run_playable`):

```python
yield progress_event(
    "playable", "completed",
    stage_index=_STAGE_INDEX["playable"],
    total_stages=TOTAL_STAGES,
    duration_ms=int((time.monotonic() - start) * 1000),
    playable_count=len(playable_chars),
    sample=[c.name for c in playable_chars[:3] if c.name],
)
```

**`_run_critic` repair_completed** — find the call site and add `repair_count`:

```python
yield progress_event(
    "critic", "repair_completed",
    stage_index=_STAGE_INDEX["critic"],
    total_stages=TOTAL_STAGES,
    duration_ms=int((time.monotonic() - start) * 1000),
    repair_count=len(repaired_targets),  # or whatever variable holds the list
)
```

(For `critic.completed` without repair, no new fields needed — the frontend falls back to "通过".)

**`_run_images` subtask_completed** — every per-image emit gains `label`. Find the existing call sites for `images.subtask_started` / `images.subtask_completed` and add `payload_summary={"label": image_label}` where `image_label` is the cover label / character name / etc. that the renderer is currently handling.

**`_run_images` completed** — add `cover_count` and `avatar_count`:

```python
cover_count = sum(1 for img in generated_images if img.kind in ("hero", "cover", "list"))
avatar_count = sum(1 for img in generated_images if img.kind == "character")
yield progress_event(
    "images", "completed",
    ...,
    image_count=len(generated_images),
    cover_count=cover_count,
    avatar_count=avatar_count,
)
```

(Adapt field names to actual `Image`/`GeneratedImage` schema. Inspect the relevant model in `models/` or builder in `services/`.)

- [ ] **Step 6.4: Run backend tests to verify they pass**

Run from `backend/`: `python -m pytest tests/test_world_creator_v2_entry.py -v`
Expected: tests added in Step 6.1 pass; existing tests still pass.

Run full agent suite: `python -m pytest tests/test_world_creator_v2_entry.py tests/test_world_creator_v2_migration.py tests/test_world_creator_agent_dynamic.py -v`
Expected: all green.

- [ ] **Step 6.5: Update `frontend/lib/admin-sse-events.ts` `ProgressMeta` type**

Append optional fields to the `ProgressMeta` type (around line 1-19):

```ts
export type ProgressMeta = {
  stage_index?: number;
  total_stages?: number;
  stage_label?: string;
  subtask_key?: string;
  subtask_index?: number;
  subtask_total?: number;
  duration_ms?: number;
  payload_summary?: Record<string, number | string>;
  attempt?: number;
  max_attempts?: number;
  error_class?: string;
  // New fields (Task 6) — all optional, frontend formatter degrades gracefully
  sample?: string[];
  world_name?: string;
  location_count?: number;
  dimension_count?: number;
  role_count?: number;
  character_count?: number;
  event_count?: number;
  npc_count?: number;
  edge_count?: number;
  clue_count?: number;
  playable_count?: number;
  repair_count?: number;
  cover_count?: number;
  avatar_count?: number;
  image_count?: number;
};
```

- [ ] **Step 6.6: Re-run the frontend test suite to ensure type changes don't break anything**

Run from `frontend/`: `npm test`
Expected: all green.

---

## Task 7: Backend — `_run_with_pulse` helper

**Files:**
- Modify: `backend/services/world_creator_agent_v2.py` (add method)
- Create or modify: `backend/tests/test_world_creator_v2_entry.py` (add helper test)

- [ ] **Step 7.1: Write failing test**

Append to `backend/tests/test_world_creator_v2_entry.py`:

```python
import asyncio
import pytest

from services.world_creator_agent_v2 import WorldCreatorAgentV2


@pytest.mark.asyncio
async def test_run_with_pulse_yields_periodic_pulses_during_long_work():
    """While work runs, _run_with_pulse should emit pulse events at the configured interval,
    then yield the result tuple. The final yield is ('result', value)."""

    agent = WorldCreatorAgentV2(llm=None, image_gen=None, broker=None)

    async def slow_work():
        await asyncio.sleep(0.35)
        return "done"

    pulses = []
    result = None
    async for item in agent._run_with_pulse("shared_events", slow_work(), interval=0.1):
        if isinstance(item, tuple) and item[0] == "result":
            result = item[1]
        elif isinstance(item, dict):
            assert item.get("phase") == "shared_events"
            assert item.get("code") == "pulse"
            pulses.append(item)

    assert result == "done"
    # ~3 pulses (0.35s / 0.1s); accept >= 2 for jitter tolerance
    assert len(pulses) >= 2, f"expected at least 2 pulses, got {len(pulses)}"


@pytest.mark.asyncio
async def test_run_with_pulse_propagates_exception():
    agent = WorldCreatorAgentV2(llm=None, image_gen=None, broker=None)

    async def failing_work():
        await asyncio.sleep(0.05)
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        async for item in agent._run_with_pulse("shared_events", failing_work(), interval=0.5):
            pass  # should raise before any pulse


@pytest.mark.asyncio
async def test_run_with_pulse_returns_immediately_for_fast_work():
    """Work that completes before the first interval should still yield a result and no pulses."""
    agent = WorldCreatorAgentV2(llm=None, image_gen=None, broker=None)

    async def fast_work():
        return 42

    pulses = []
    result = None
    async for item in agent._run_with_pulse("shared_events", fast_work(), interval=1.0):
        if isinstance(item, tuple) and item[0] == "result":
            result = item[1]
        else:
            pulses.append(item)

    assert result == 42
    assert len(pulses) == 0
```

- [ ] **Step 7.2: Run tests to verify failure**

Run from `backend/`: `python -m pytest tests/test_world_creator_v2_entry.py -v -k "run_with_pulse"`
Expected: FAIL — `_run_with_pulse` method does not exist.

- [ ] **Step 7.3: Implement `_run_with_pulse`**

Add to `backend/services/world_creator_agent_v2.py` (inside the `WorldCreatorAgentV2` class):

```python
async def _run_with_pulse(
    self,
    phase: str,
    work: "Coroutine[Any, Any, T]",
    *,
    interval: float = 7.0,
) -> "AsyncIterator[dict | tuple[str, T]]":
    """Run `work` while emitting periodic `pulse` progress events.

    Yields:
        - dict progress events (kind == "pulse") at every `interval` seconds
        - a final tuple ("result", value) when work succeeds

    Raises whatever exception `work` raises.
    """
    queue: "asyncio.Queue[tuple[str, Any]]" = asyncio.Queue()

    async def runner() -> None:
        try:
            value = await work
        except Exception as exc:  # noqa: BLE001
            await queue.put(("error", exc))
        else:
            await queue.put(("result", value))

    async def pulser() -> None:
        while True:
            await asyncio.sleep(interval)
            await queue.put(("pulse", None))

    work_task = asyncio.create_task(runner())
    pulse_task = asyncio.create_task(pulser())

    try:
        while True:
            kind, payload = await queue.get()
            if kind == "pulse":
                yield progress_event(phase, "pulse")
            elif kind == "result":
                yield ("result", payload)
                return
            elif kind == "error":
                raise payload  # type: ignore[misc]
    finally:
        pulse_task.cancel()
        if not work_task.done():
            work_task.cancel()
        # Drain cancellation
        for task in (pulse_task, work_task):
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
```

Add typing imports at the top of the file if not present:

```python
from typing import Any, AsyncIterator, Coroutine, TypeVar

T = TypeVar("T")
```

- [ ] **Step 7.4: Run tests — should pass**

Run from `backend/`: `python -m pytest tests/test_world_creator_v2_entry.py -v -k "run_with_pulse"`
Expected: 3 passing.

---

## Task 8: Apply pulse to 5 long stages + register pulse templates + update progress weights

**Files:**
- Modify: `backend/services/world_creator_agent_v2.py` — wrap `_run_research_pack`, `_run_lore_dimensions`, `_run_character_roster`, `_run_shared_events`, `_run_visual_brief`
- Modify: `backend/services/generation_feedback.py` — add 5 pulse templates
- Modify: `frontend/lib/admin-progress-view.ts` — add `pulse: 0.5` to `PHASE_CODE_PROGRESS` for those stages
- Modify: `backend/tests/test_generation_feedback.py` — add pulse template tests

- [ ] **Step 8.1: Add pulse template tests**

Append to `backend/tests/test_generation_feedback.py`:

```python
def test_pulse_templates_registered_for_long_single_llm_stages():
    """Five long single-LLM stages must have a pulse template so the headline can render text."""
    for phase in ("research_pack", "lore_dimensions", "character_roster", "shared_events", "visual_brief"):
        event = progress_event(phase, "pulse")
        assert event["type"] == "progress"
        assert event["code"] == "pulse"
        assert event["message"], f"{phase}.pulse should have a non-empty message"
```

- [ ] **Step 8.2: Run tests to verify failure**

Run from `backend/`: `python -m pytest tests/test_generation_feedback.py -v -k "pulse_templates"`
Expected: FAIL — templates missing → message is empty string.

- [ ] **Step 8.3: Add pulse templates to `generation_feedback.py`**

In `backend/services/generation_feedback.py`, add to `FEEDBACK_TEMPLATES`:

```python
("research_pack", "pulse"): "正在整理参考素材…",
("lore_dimensions", "pulse"): "正在拓展世界各维度…",
("character_roster", "pulse"): "正在校准角色身份和密度…",
("shared_events", "pulse"): "正在编织共享历史的因果链…",
("visual_brief", "pulse"): "正在统一视觉语言…",
```

- [ ] **Step 8.4: Run tests — should pass**

Run from `backend/`: `python -m pytest tests/test_generation_feedback.py -v`
Expected: all green.

- [ ] **Step 8.5: Wrap `_run_shared_events` with pulse**

In `backend/services/world_creator_agent_v2.py`, refactor `_run_shared_events` (line 682 onwards):

```python
async def _run_shared_events(
    self,
    description: str,
    ip_canon: IPCanon,
    characters: list[Character],
    research_pack: ResearchPack,
) -> AsyncIterator[dict]:
    start = time.monotonic()
    yield progress_event(
        "shared_events", "started",
        stage_index=_STAGE_INDEX["shared_events"],
        total_stages=TOTAL_STAGES,
    )

    work = with_transient_retry(
        lambda: build_shared_events(
            description=description,
            ip_canon=ip_canon,
            characters=characters,
            passages=research_pack.passages,
            llm_router=self.llm,
            k_target=15,
            k_min=5,
        ),
        max_attempts=3,
        on_retry=self._make_retry_logger("shared_events"),
    )

    shared_events: list[SharedEvent] = []
    try:
        async for item in self._run_with_pulse("shared_events", work):
            if isinstance(item, tuple) and item[0] == "result":
                shared_events = item[1] or []
            else:
                yield item
    except Exception as exc:  # noqa: BLE001
        logger.warning("shared_events_failed", error=str(exc))
        shared_events = []

    self._last_shared_events = shared_events
    await self._record_intermediate(
        "shared_events", [e.model_dump() for e in shared_events]
    )

    yield progress_event(
        "shared_events", "completed",
        stage_index=_STAGE_INDEX["shared_events"],
        total_stages=TOTAL_STAGES,
        duration_ms=int((time.monotonic() - start) * 1000),
        event_count=len(shared_events),
        sample=[ev.title for ev in shared_events[:2] if getattr(ev, "title", "")],
    )
```

- [ ] **Step 8.6: Apply the same pattern to the other 4 stages**

Repeat Step 8.5's pattern for:
- `_run_research_pack` (around line 270): wrap the call that fetches passages + ip_canon
- `_run_lore_dimensions` (around line 448): wrap the LLM call that produces dimensions
- `_run_character_roster` (around line 489): wrap the LLM call that produces roster
- `_run_visual_brief` (around line 1025): wrap the LLM call that produces visual brief

For each: identify the single `await with_transient_retry(...)` (or `await <single_llm_call>(...)`) that dominates the stage's runtime, replace `result = await X` with the `async for item in self._run_with_pulse(...)` loop pattern.

If a stage has multiple sequential awaits (e.g., `_run_research_pack` does search + summarize), wrap the longer one or both — but emit the started/completed events *outside* the pulse wrapping, since pulse should run during the long work, not envelop the framing events.

- [ ] **Step 8.7: Run backend tests**

Run from `backend/`: `python -m pytest tests/ -v -k "world_creator or generation_feedback"`
Expected: all green. New tests + existing tests pass.

- [ ] **Step 8.8: Update frontend progress weights**

In `frontend/lib/admin-progress-view.ts`, locate `PHASE_CODE_PROGRESS` (line 97 onwards). Add `pulse: 0.5` to each of the 5 wrapped stages:

```ts
research_pack: {
  started: 0.3,
  pulse: 0.5,
  completed: 1,
},
lore_dimensions: {
  started: 0.3,
  pulse: 0.5,
  completed: 1,
},
character_roster: {
  started: 0.3,
  pulse: 0.5,
  completed: 1,
},
shared_events: {
  started: 0.3,
  pulse: 0.5,
  completed: 1,
},
visual_brief: {
  started: 0.4,
  pulse: 0.6,
  completed: 1,
},
```

This gives the weighted progress bar something to move during pulse-only stretches.

- [ ] **Step 8.9: Manual end-to-end check**

Start backend + frontend (`uvicorn main:app --reload` and `npm run dev`). Trigger a real world generation, watch the loading screen:
- During `shared_events`, observe `headline` flicker through `pulse` text every ~7s
- Progress bar inches forward during pulse-only stretches (no longer parks)
- After completion, the 12-stage panel rows show enriched summaries: "✓ 设计共享事件 · 12 段历史 · 科举舞弊案、安禄山入长安"
- Refresh mid-generation; the panel correctly shows already-completed steps as ✓ (Task 3 fix retained)

---

## Final verification

- [ ] **Step F.1: Frontend** — `cd frontend && npm test && npm run lint` → all green
- [ ] **Step F.2: Backend** — `cd backend && python -m pytest tests/ -v` → all green (or no new failures vs. main)
- [ ] **Step F.3: Manual smoke** per Step 8.9. Capture screenshots if desired.

---

## Decisions captured (mirror of spec)

- Included `clue_count` (events_data) and `cover_count` / `avatar_count` (images) — cheap, adds depth
- Did **not** detail critic repair labels — no structured data available
- `sample` array is 2-3 strings; over-length handled by CSS ellipsis, not JS truncation
- Pulse interval: 7s global default, can be overridden per-call
- Single-line constraint: pure CSS (`white-space: nowrap` + `text-overflow: ellipsis`); formatter never truncates

## Out of scope

- Stage timing dashboard (item 3 of brainstorm) — data already in `duration_ms`; revisit when doing generation speedup
- SSE reconnect catch-up (re-fetch events after stream re-establishes) — hydrate from `loadDraft()` covers the common case; small race window acceptable
