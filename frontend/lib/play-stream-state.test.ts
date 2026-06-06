import assert from "node:assert/strict";

import {
  applyProcessingEvent,
  completePlayStream,
  createIdlePlayStreamState,
  failPlayStream,
  startPlayStream,
  receiveNarrativeToken,
} from "./play-stream-state.ts";

test("play stream starts in idle phase", () => {
  const state = createIdlePlayStreamState();

  assert.equal(state.phase, "idle");
  assert.equal(state.processing, null);
});

test("new stream enters processing before the first token", () => {
  const state = startPlayStream();

  assert.equal(state.phase, "processing");
  assert.equal(state.processing, null);
});

test("first narrative token switches the phase to streaming", () => {
  const state = receiveNarrativeToken(
    applyProcessingEvent(startPlayStream(), {
      phase: "thinking",
      focus_npcs: ["村头王大爷"],
      flavor: "村头王大爷像是想起了什么",
    }),
  );

  assert.equal(state.phase, "streaming");
  assert.equal(state.processing, null);
});

test("explicit processing flavor wins over local fallback text", () => {
  const state = applyProcessingEvent(
    startPlayStream(),
    {
      phase: "thinking",
      focus_npcs: ["村头王大爷"],
      flavor: "村头王大爷正眯起眼重新打量你",
    },
    "茶摊",
  );

  assert.equal(state.processing?.flavor, "村头王大爷正眯起眼重新打量你");
});

test("processing falls back to npc or environment copy when flavor is missing", () => {
  const npcState = applyProcessingEvent(startPlayStream(), {
    phase: "thinking",
    focus_npcs: ["村头王大爷"],
  });
  const environmentState = applyProcessingEvent(startPlayStream(), {}, "茶摊");

  assert.equal(npcState.processing?.flavor, "村头王大爷像是想起了什么");
  assert.equal(environmentState.processing?.flavor, "茶摊里一时安静下来，像是在等你看清局势");
});

test("processing carries v2 stage / input_summary / npcs through", () => {
  const received = applyProcessingEvent(startPlayStream(), { stage: "received", kind: "progress" });
  assert.equal(received.processing?.stage, "received");

  const reasoning = applyProcessingEvent(startPlayStream(), {
    stage: "reasoning",
    input_summary: "我检查门槛",
    kind: "progress",
  });
  assert.equal(reasoning.processing?.stage, "reasoning");
  assert.equal(reasoning.processing?.input_summary, "我检查门槛");

  const npcs = applyProcessingEvent(startPlayStream(), {
    stage: "npcs_entering",
    npcs: ["王福", "赵姐"],
    kind: "progress",
  });
  assert.equal(npcs.processing?.stage, "npcs_entering");
  assert.deepEqual(npcs.processing?.npcs, ["王福", "赵姐"]);
});

test("late milestone after streaming begins does not revert the phase", () => {
  // "writing" is pushed in the same backend tick that fires narrator_ready, so
  // it can race the first narrative token. Once streaming, processing is frozen.
  const streaming = receiveNarrativeToken(startPlayStream());
  const after = applyProcessingEvent(streaming, { stage: "writing", kind: "progress" });

  assert.equal(after.phase, "streaming");
  assert.equal(after.processing, null);
});

test("done and error clear processing state", () => {
  const processingState = applyProcessingEvent(startPlayStream(), {
    phase: "thinking",
    focus_npcs: ["村头王大爷"],
  });

  const doneState = completePlayStream(processingState);
  const errorState = failPlayStream(processingState);
  const errorDoneState = completePlayStream(errorState);

  assert.equal(doneState.phase, "done");
  assert.equal(doneState.processing, null);
  assert.equal(errorState.phase, "error");
  assert.equal(errorState.processing, null);
  assert.equal(errorDoneState.phase, "error");
  assert.equal(errorDoneState.processing, null);
});
