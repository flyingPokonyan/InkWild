"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";

import { ChoiceScene, PromptComposer } from "@/components/choice";
import { GenerationLoadingScreen } from "@/components/admin/GenerationLoadingScreen";
import { IPRecognitionCard } from "@/components/admin/workshop/IPRecognitionCard";
import { LV_EASE, lvStaggerContainer } from "@/lib/motion";
import {
  appendAdminPhaseEvent,
  completeAdminPhaseTimeline,
  markLatestAdminPhaseAsError,
  type AdminPhaseEntry,
} from "@/lib/admin-progress-state";
import {
  workshopFetch,
  continueWorldDraftGeneration,
  getGenerationTask,
  streamAdminEvents,
  type AdminProgressEvent,
} from "@/lib/workshop-api";
import { isIPRecognitionEvent, type IPRecognitionEvent } from "@/lib/admin-sse-events";
import type { ProgressMeta } from "@/lib/admin-sse-events";
import type { AdminGenerationTaskCreateResponse, AdminGenerationTaskEvent } from "@/lib/types";

type GenStep = "prompt" | "options";
const STEPS_ORDER: GenStep[] = ["prompt", "options"];

function compactText(value: string, max = 34): string {
  const text = value.trim().replace(/\s+/g, " ");
  if (text.length <= max) {
    return text;
  }
  return `${text.slice(0, max)}…`;
}

type FidelityMode = "strict" | "loose" | "none";
const STREAM_RECONNECT_LIMIT = 5;
const STREAM_RECONNECT_DELAY_MS = 1200;

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function streamPath(taskId: string, afterSeq: number): string {
  const query = afterSeq > 0 ? `?after_seq=${afterSeq}` : "";
  return `/api/workshop/generation-tasks/${taskId}/stream${query}`;
}

function extractIpRecognitionFromEvents(
  events: AdminGenerationTaskEvent[],
): IPRecognitionEvent["meta"] | null {
  for (const event of events) {
    if (event.event !== "progress") {
      continue;
    }
    const progress = {
      phase: String(event.payload.phase || ""),
      code: String(event.payload.code || ""),
      message: String(event.payload.message || ""),
      meta: event.payload.meta as ProgressMeta | undefined,
    };
    if (isIPRecognitionEvent(progress)) {
      return progress.meta;
    }
  }
  return null;
}

export default function GenerateWorldPage() {
  const router = useRouter();

  const [step, setStep] = useState<GenStep>("prompt");
  const [description, setDescription] = useState("");
  const [genre, setGenre] = useState("");
  const [era, setEra] = useState("");

  const [generating, setGenerating] = useState(false);
  const [phases, setPhases] = useState<AdminPhaseEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState(0);

  const [ipRecognition, setIpRecognition] = useState<IPRecognitionEvent["meta"] | null>(null);
  const [cardDecided, setCardDecided] = useState(false);
  const [continueError, setContinueError] = useState<string | null>(null);

  const draftMetaRef = useRef<{ draft_id: string; draft_url: string } | null>(null);
  const continueInFlightRef = useRef(false);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const streamAbortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    return () => {
      streamAbortRef.current?.abort();
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    };
  }, []);

  const startTimer = () => {
    setElapsed(0);
    timerRef.current = setInterval(() => setElapsed((s) => s + 1), 1000);
  };
  const stopTimer = () => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  };

  const handleNext = () => {
     if (description.trim()) setStep("options");
  };

  const handleBack = () => {
     setStep("prompt");
  };

  /** Subscribe to one task's SSE stream. Returns once the stream ends. */
  const runTaskStream = useCallback(
    async (
      taskId: string,
    ): Promise<{ didComplete: boolean; ipRec: IPRecognitionEvent["meta"] | null }> => {
      let didComplete = false;
      let ipRec: IPRecognitionEvent["meta"] | null = null;
      let afterSeq = 0;
      let reconnects = 0;

      while (true) {
        let streamError: string | null = null;
        const controller = new AbortController();
        streamAbortRef.current = controller;

        const result = await streamAdminEvents(streamPath(taskId, afterSeq), {
          onEvent: (event) => {
            if (typeof event.seq === "number" && event.seq > afterSeq) {
              afterSeq = event.seq;
            }
          },
          onProgress: (event: AdminProgressEvent) => {
            setPhases((prev) => appendAdminPhaseEvent(prev, event));
            if (isIPRecognitionEvent(event)) {
              ipRec = event.meta;
              setIpRecognition(event.meta);
              setCardDecided(false);
              setContinueError(null);
            }
          },
          onWarning: (event: AdminProgressEvent) => {
            setPhases((prev) => appendAdminPhaseEvent(prev, event, "warning"));
          },
          onResult: () => {
            didComplete = true;
          },
          onError: (message) => {
            streamError = message;
          },
        }, { signal: controller.signal });

        if (streamAbortRef.current === controller) {
          streamAbortRef.current = null;
        }

        if (result.aborted) {
          return { didComplete: false, ipRec };
        }

        const task = await getGenerationTask(taskId).catch(() => null);
        if (task?.events?.length && !ipRec) {
          const recognition = extractIpRecognitionFromEvents(task.events);
          if (recognition) {
            ipRec = recognition;
            setIpRecognition(recognition);
            setCardDecided(false);
            setContinueError(null);
          }
        }

        if (didComplete || task?.status === "succeeded") {
          return { didComplete: true, ipRec };
        }

        if (task?.status === "failed" || task?.status === "cancelled") {
          setError(task.error_message || streamError || "生成失败");
          return { didComplete: false, ipRec };
        }

        reconnects += 1;
        if (reconnects > STREAM_RECONNECT_LIMIT || result.timedOut) {
          setError("连接不稳定，生成任务仍在后台运行。请稍后返回创作工坊查看草稿。");
          return { didComplete: false, ipRec };
        }

        await sleep(STREAM_RECONNECT_DELAY_MS * reconnects);
      }
    },
    [],
  );

  /** Phase B kick-off — called by IPRecognitionCard.onChoose or auto-skip path. */
  const runPhaseBAfterChoice = useCallback(
    async (mode: FidelityMode) => {
      if (continueInFlightRef.current) return;
      const draft = draftMetaRef.current;
      if (!draft) return;
      continueInFlightRef.current = true;
      setCardDecided(true);
      setContinueError(null);
      try {
        const { task_id } = await continueWorldDraftGeneration(draft.draft_id, mode);
        setPhases([]);
        setIpRecognition(null);
        const phaseB = await runTaskStream(task_id);
        if (!phaseB.didComplete) {
          stopTimer();
          setPhases((prev) => markLatestAdminPhaseAsError(prev));
          setError((prev) => prev || "连接中断，生成未完成");
          setGenerating(false);
          continueInFlightRef.current = false;
          return;
        }
        stopTimer();
        setPhases((prev) => completeAdminPhaseTimeline(prev));
        continueInFlightRef.current = false;
        router.push(draft.draft_url);
      } catch (err) {
        setContinueError(err instanceof Error ? err.message : "继续生成失败，请重试");
        setCardDecided(false);
        continueInFlightRef.current = false;
      }
    },
    [router, runTaskStream],
  );

  const handleGenerate = async () => {
    if (!description.trim() || generating) return;

    setGenerating(true);
    setError(null);
    setPhases([]);
    setIpRecognition(null);
    setCardDecided(false);
    setContinueError(null);
    draftMetaRef.current = null;
    startTimer();

    let taskMeta: AdminGenerationTaskCreateResponse | null = null;
    try {
      taskMeta = await workshopFetch<AdminGenerationTaskCreateResponse>("/api/workshop/world-generation-tasks", {
        method: "POST",
        body: JSON.stringify({ description, genre, era }),
      });
    } catch (reason) {
      stopTimer();
      setError(reason instanceof Error ? reason.message : "创建生成任务失败");
      setGenerating(false);
      return;
    }

    draftMetaRef.current = { draft_id: taskMeta.draft_id, draft_url: taskMeta.draft_url };

    const phaseA = await runTaskStream(taskMeta.task_id);

    if (!phaseA.didComplete) {
      stopTimer();
      setPhases((prev) => markLatestAdminPhaseAsError(prev));
      setError((prev) => prev || "连接中断，生成未完成");
      setGenerating(false);
      return;
    }

    if (phaseA.ipRec && !isAutoSkipRecognition(phaseA.ipRec)) {
      // Card will render; user picks → runPhaseBAfterChoice fires.
      return;
    }

    if (phaseA.ipRec && isAutoSkipRecognition(phaseA.ipRec)) {
      await runPhaseBAfterChoice("none");
      return;
    }

    stopTimer();
    setPhases((prev) => completeAdminPhaseTimeline(prev));
    router.push(taskMeta.draft_url);
  };

  const currentStepIndex = STEPS_ORDER.indexOf(step);
  const worldSubjectLabel = description.trim()
    ? `概念：${compactText(description, 24)}`
    : "AI 正在整理世界概念";

  if (generating || phases.length > 0) {
    const showCard = !!ipRecognition && !cardDecided && !isAutoSkipRecognition(ipRecognition);
    const decisionSlot = showCard && ipRecognition ? (
      <div className="ip-decision-slot">
        {continueError && (
          <div role="alert" className="ip-decision-error">
            {continueError}
          </div>
        )}
        <IPRecognitionCard
          recognition={ipRecognition}
          onChoose={(mode) => {
            void runPhaseBAfterChoice(mode);
          }}
        />
        <style>{`
          .ip-decision-slot {
            width: 100%;
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: var(--lv-s-3);
          }
          .ip-decision-error {
            width: 100%;
            max-width: 480px;
            font-family: var(--lv-font-sans);
            font-size: var(--lv-t-meta);
            padding: var(--lv-s-3) var(--lv-s-4);
            border-radius: var(--lv-r-card);
            border: 1px solid rgba(239, 130, 118, 0.35);
            background: rgba(239, 130, 118, 0.08);
            color: var(--lv-danger);
            letter-spacing: 0.02em;
            text-align: center;
          }
        `}</style>
      </div>
    ) : null;

    return (
      <GenerationLoadingScreen
        phases={phases}
        elapsed={elapsed}
        operationLabel="世界生成中"
        subjectLabel={worldSubjectLabel}
        error={error}
        onReset={() => {
          streamAbortRef.current?.abort();
          stopTimer();
          setPhases([]);
          setError(null);
          setIpRecognition(null);
          setCardDecided(false);
          setContinueError(null);
          setGenerating(false);
          router.push("/workshop");
        }}
        onRetry={() => {
          void handleGenerate();
        }}
        centerSlot={decisionSlot}
      />
    );
  }

  return (
    <ChoiceScene
      eyebrow="创作 · 世界"
      title={step === "prompt" ? "" : "附加世界设定"}
      description={
        step === "prompt"
          ? "用一句话写下灵感，AI 会把它展开成完整舞台。"
          : "为这个世界补充更精确的细分标签，都可留空。"
      }
      background="plain"
      onBack={step === "prompt" ? () => router.push("/workshop") : handleBack}
      backLabel={step === "prompt" ? "← 返回工坊" : "← 上一步"}
      steps={{ current: currentStepIndex, total: STEPS_ORDER.length }}
    >
      <AnimatePresence mode="wait">
        <motion.div
          key={step}
          variants={lvStaggerContainer}
          initial="hidden"
          animate="show"
          exit={{ opacity: 0, transition: { duration: 0.15, ease: LV_EASE } }}
          style={{ width: "100%" }}
        >
          {step === "prompt" && (
            <>
              <PromptComposer
                value={description}
                onChange={setDescription}
                onSubmit={handleNext}
                placeholder="例如：一座漂浮在云海之上的废墟之城，居民世代搜寻坠落的星骸……"
                ctaLabel="下一步"
                ariaLabel="世界描述"
                canSubmit={!!description.trim()}
                autoFocus
              />
              <button
                type="button"
                onClick={() => router.push("/workshop/generate/script")}
                style={{
                  display: "block",
                  margin: "16px auto 0",
                  background: "none",
                  border: 0,
                  color: "var(--lv-ink-3)",
                  fontSize: 12,
                  cursor: "pointer",
                  padding: "8px 12px",
                  borderRadius: "var(--lv-r-pill)",
                  transition: "color 150ms ease",
                }}
                onMouseEnter={(e) => { e.currentTarget.style.color = "var(--lv-ink-2)"; }}
                onMouseLeave={(e) => { e.currentTarget.style.color = "var(--lv-ink-3)"; }}
              >
                想给已有世界加剧本？ →
              </button>
            </>
          )}

          {step === "options" && (
            <div className="lv-gen-options">
              <div className="lv-gen-field">
                <label className="lv-form-label" htmlFor="gen-world-genre">
                  世界类型（可选）
                </label>
                <input
                  id="gen-world-genre"
                  className="lv-input"
                  value={genre}
                  onChange={(e) => setGenre(e.target.value)}
                  placeholder="如：废土修仙 / 赛博都市"
                />
              </div>
              <div className="lv-gen-field">
                <label className="lv-form-label" htmlFor="gen-world-era">
                  所处时代（可选）
                </label>
                <input
                  id="gen-world-era"
                  className="lv-input"
                  value={era}
                  onChange={(e) => setEra(e.target.value)}
                  placeholder="如：核战后 200 年"
                />
              </div>
              <button type="button" className="lv-cta-ivory" onClick={() => void handleGenerate()}>
                开始生成
              </button>

              <style jsx global>{`
                .lv-theme .lv-gen-options {
                  width: 100%;
                  max-width: 420px;
                  margin: 0 auto;
                  display: flex;
                  flex-direction: column;
                  gap: var(--lv-s-4);
                }
                @media (max-width: 768px) {
                  .lv-theme .lv-gen-options { max-width: 320px; }
                }
                .lv-theme .lv-gen-field {
                  display: flex;
                  flex-direction: column;
                  gap: var(--lv-s-2);
                }
                .lv-theme .lv-gen-options .lv-cta-ivory { margin-top: var(--lv-s-2); }
              `}</style>
            </div>
          )}
        </motion.div>
      </AnimatePresence>
    </ChoiceScene>
  );
}

function isAutoSkipRecognition(rec: IPRecognitionEvent["meta"]): boolean {
  return rec.kind === "original" || rec.confidence < 0.5;
}
