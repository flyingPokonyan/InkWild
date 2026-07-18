"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { type ReactNode, startTransition, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { Eye, Save, Trash2 } from "lucide-react";

import { GenerationLoadingScreen } from "@/components/admin/GenerationLoadingScreen";
import { IPRecognitionCard } from "@/components/admin/workshop/IPRecognitionCard";
import { Drawer } from "@/components/ui/Drawer";
import { Modal } from "@/components/ui/Modal";
import {
  workshopFetch,
  streamAdminEvents,
  type AdminProgressEvent,
} from "@/lib/workshop-api";
import { isIPRecognitionEvent, type IPRecognitionEvent } from "@/lib/admin-sse-events";
import {
  initStagesMap,
  STAGE_KEYS,
  STAGE_LABELS,
  type StageKey,
  type StageState,
} from "@/lib/admin-generation-stages";
import { parseBackendIso } from "@/lib/datetime";
import {
  appendAdminPhaseEvent,
  applyEventToStages,
  completeAdminPhaseTimeline,
  hydrateAdminPhaseTimeline,
  hydrateStagesFromEvents,
  markLatestAdminPhaseAsError,
  markRunningStagesFailed,
  type AdminPhaseEntry,
} from "@/lib/admin-progress-state";
import type { AdminGenerationTaskEvent, AdminGenerationTaskSummary } from "@/lib/types";

/** Extract the most recent IP recognition meta from a task's event history.
 * Used to hydrate the IPRecognitionCard when the user lands on the draft
 * AFTER phase_a has already completed (e.g. coming from the generate page
 * which now waits for the result event before navigating). The live SSE path
 * only fires while the task is still running, so without this we'd silently
 * skip showing the card. */
function extractIpRecognitionFromEvents(
  events: AdminGenerationTaskEvent[] | undefined,
): IPRecognitionEvent["meta"] | null {
  if (!events || events.length === 0) return null;
  for (let i = events.length - 1; i >= 0; i--) {
    const evt = events[i];
    if (evt.event !== "progress") continue;
    const payload = evt.payload as { phase?: string; code?: string; meta?: unknown };
    if (payload.phase !== "ip_recognition" || payload.code !== "completed") continue;
    const meta = payload.meta as IPRecognitionEvent["meta"] | undefined;
    if (meta && typeof meta.kind === "string") return meta;
  }
  return null;
}

import { DraftStrip } from "./DraftStrip";
import { SectionRail, SectionRailMobile, type RailSection } from "./SectionRail";
import { useAutosave } from "./hooks/use-autosave";
import { useKeyboardShortcuts } from "./hooks/use-keyboard-shortcuts";
import { useSectionObserver } from "./hooks/use-section-observer";

interface BaseDraftDetail {
  id: string;
  updated_at: string;
  generation_task?: AdminGenerationTaskSummary | null;
}

export interface DraftEditorShellProps<P, D extends BaseDraftDetail> {
  draftId: string;
  kind: "world" | "script";
  /** 返回上一级的路径，默认 "/workshop" */
  backTo?: string;
  /** API path builders — workshop pages point to /api/workshop/*. */
  endpoints: {
    detail: (id: string) => string;
    publish: (id: string) => string;
    /** SSE stream URL for a generation task. */
    stream: (taskId: string, afterSeq: number) => string;
    /** POST to kick off phase_b after Stage 0 IP recognition (world drafts only). */
    continueGeneration?: (draftId: string) => string;
  };
  /** 从 detail 中拿 payload */
  selectPayload: (detail: D) => P;
  /** 渲染主体 sections。返回 reactNode + sections meta（rail 用） */
  renderBody: (ctx: {
    payload: P;
    setPayload: (updater: (current: P) => P) => void;
    rail: RailSection[];
    detail: D;
    draftId: string;
    kind: "world" | "script";
    /** flush 待保存编辑（图片重抽前调用，确保后端读到最新字段） */
    saveNow: () => Promise<void>;
    /** 主体内长任务（如 AI 精修）进行中时置 true —— shell 据此暂停 autosave、
     * 禁用保存/发布，避免与服务端回写打架。 */
    setBusy: (busy: boolean) => void;
  }) => ReactNode;
  /** 各 section 的 rail meta（id / label / 计数函数） */
  buildRail: (payload: P) => RailSection[];
  /** 草稿标题（顶端 strip 显示），通常 = payload.name 或 fallback */
  getTitle: (payload: P) => string;
  /** 仅 script 页有；用于 strip 模式徽 */
  modeGlyph?: "◆" | "◇";
  /** 预览面板（玩家视角）。render prop，能拿到当前 payload。 */
  renderPreview: (payload: P) => ReactNode;
  /** 生成进度页 subject 文案 */
  generationSubjectLabel: (payload: P) => string;
  /** 生成进度页 operation 文案 */
  generationOperationLabel: string;
}

/**
 * 共享编辑器 shell。
 * 负责：load / save / publish / discard / autosave / SSE generation loading / 路由守卫 / 快捷键 / 布局。
 * 子页只关心「这一类内容长什么样」（renderBody / preview）。
 */
export function DraftEditorShell<P, D extends BaseDraftDetail>(
  props: DraftEditorShellProps<P, D>,
) {
  const {
    draftId,
    kind,
    backTo = "/workshop",
    endpoints,
    selectPayload,
    renderBody,
    buildRail,
    getTitle,
    modeGlyph,
    renderPreview,
    generationSubjectLabel,
    generationOperationLabel,
  } = props;

  const t = useTranslations("admin.editor");
  const router = useRouter();

  const [detail, setDetail] = useState<D | null>(null);
  const [payload, setPayloadState] = useState<P | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [publishing, setPublishing] = useState(false);
  const [discarding, setDiscarding] = useState(false);
  const [confirm, setConfirm] = useState<"discard" | "publish" | "leave" | null>(null);
  const [pendingNavigate, setPendingNavigate] = useState<string | null>(null);
  const [previewOpen, setPreviewOpen] = useState(false);

  const [generationTask, setGenerationTask] = useState<AdminGenerationTaskSummary | null>(null);
  const [phases, setPhases] = useState<AdminPhaseEntry[]>([]);
  const [elapsed, setElapsed] = useState(0);
  const [stages, setStages] = useState<Map<StageKey, StageState>>(initStagesMap);
  const [ipRecognition, setIpRecognition] = useState<IPRecognitionEvent["meta"] | null>(null);
  const [cardDecided, setCardDecided] = useState(false);
  const [continueError, setContinueError] = useState<string | null>(null);
  // 主体内长任务（AI 精修）进行中：暂停 autosave、禁用保存/发布，防回写竞争。
  const [refineBusy, setRefineBusy] = useState(false);
  const continueInFlightRef = useRef(false);
  const continueRetryRef = useRef(0);
  const MAX_CONTINUE_RETRIES = 3;
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const streamAbortRef = useRef<AbortController | null>(null);

  const stopTaskTimer = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const startTaskTimer = useCallback(
    (startedAt: string | null | undefined) => {
      stopTaskTimer();
      const base = startedAt ? parseBackendIso(startedAt).getTime() : Date.now();
      const tick = () => setElapsed(Math.max(0, Math.floor((Date.now() - base) / 1000)));
      tick();
      timerRef.current = setInterval(tick, 1000);
    },
    [stopTaskTimer],
  );

  // ---------- load draft ----------
  const loadDraft = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await workshopFetch<D>(endpoints.detail(draftId));
      setDetail(result);
      const loadedPayload = selectPayload(result);
      setPayloadState(loadedPayload);
      setGenerationTask(result.generation_task ?? null);
      setPhases(
        result.generation_task ? hydrateAdminPhaseTimeline(result.generation_task.events) : [],
      );
      setStages(
        result.generation_task
          ? hydrateStagesFromEvents(result.generation_task.events)
          : initStagesMap(),
      );
      // Hydrate IPRecognitionCard from event history. The live SSE callback
      // only runs while task is pending/running, so without this we'd never
      // show the card when the user arrives after phase_a finished. We treat
      // the card as already-decided if draft.payload.fidelity_mode is set
      // (continue-generation writes it), so a phase_b-stage reload doesn't
      // re-surface the card.
      if (kind === "world" && result.generation_task) {
        const recognition = extractIpRecognitionFromEvents(result.generation_task.events);
        if (recognition) {
          setIpRecognition(recognition);
          const payloadFidelity = (loadedPayload as { fidelity_mode?: string }).fidelity_mode;
          setCardDecided(Boolean(payloadFidelity));
        }
      }
      if (result.generation_task?.started_at) {
        startTaskTimer(result.generation_task.started_at);
      } else {
        stopTaskTimer();
        setElapsed(0);
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t("loadFailed"));
    } finally {
      setLoading(false);
    }
  }, [draftId, endpoints, kind, selectPayload, startTaskTimer, stopTaskTimer, t]);

  useEffect(() => {
    void loadDraft();
  }, [loadDraft]);

  useEffect(() => {
    return () => {
      streamAbortRef.current?.abort();
      stopTaskTimer();
    };
  }, [stopTaskTimer]);

  // ---------- generation SSE (only when task is running) ----------
  useEffect(() => {
    if (!generationTask || !["pending", "running"].includes(generationTask.status)) {
      streamAbortRef.current?.abort();
      if (generationTask?.status === "succeeded") {
        setPhases((prev) => completeAdminPhaseTimeline(prev));
      } else if (generationTask?.status === "failed") {
        setPhases((prev) => markLatestAdminPhaseAsError(prev));
      }
      return;
    }
    const controller = new AbortController();
    streamAbortRef.current = controller;
    void streamAdminEvents(
      endpoints.stream(generationTask.id, generationTask.last_event_seq),
      {
        onProgress: (e: AdminProgressEvent) => {
          setPhases((prev) => appendAdminPhaseEvent(prev, e));
          setStages((prev) => applyEventToStages(prev, e));
          // T9: Stage 0 IP recognition — surface card so the user picks a fidelity mode.
          if (kind === "world" && isIPRecognitionEvent(e)) {
            setIpRecognition(e.meta);
            setCardDecided(false);
            setContinueError(null);
          }
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
        onDone: () => {
          void loadDraft();
        },
      },
      { signal: controller.signal },
    );
    return () => controller.abort();
  }, [generationTask, kind, loadDraft]);

  // ---------- payload + autosave ----------
  const setPayload = useCallback(
    (updater: (current: P) => P) => {
      setPayloadState((current) => (current === null ? current : updater(current)));
    },
    [],
  );

  const lastSavedAt = detail ? parseBackendIso(detail.updated_at) : null;

  const saveImpl = useCallback(
    async (next: P) => {
      const result = await workshopFetch<D>(endpoints.detail(draftId), {
        method: "PUT",
        body: JSON.stringify({ payload: next }),
      });
      setDetail(result);
    },
    [draftId, endpoints],
  );

  const autosaveActive = !!payload && !generationTask && !refineBusy;
  const { state, manualSave, isDirty } = useAutosave<P>({
    payload: payload as P,
    save: saveImpl,
    enabled: autosaveActive,
    initialSavedAt: lastSavedAt,
  });

  // flush pending edits so an image regen reads the latest persisted draft.
  const saveNow = useCallback(async () => {
    if (isDirty) await manualSave();
  }, [isDirty, manualSave]);

  // ---------- publish / discard ----------
  const doPublish = useCallback(async () => {
    if (!payload) return;
    setPublishing(true);
    setError(null);
    try {
      // flush pending edits first so publish == latest
      if (isDirty) await manualSave();
      await workshopFetch(endpoints.publish(draftId), { method: "POST" });
      startTransition(() => {
        router.push(backTo);
      });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "publish failed");
      setPublishing(false);
    }
  }, [backTo, draftId, endpoints, isDirty, manualSave, payload, router]);

  const doDiscard = useCallback(async () => {
    setDiscarding(true);
    setError(null);
    try {
      await workshopFetch(endpoints.detail(draftId), { method: "DELETE" });
      startTransition(() => {
        router.push(backTo);
      });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "discard failed");
      setDiscarding(false);
    }
  }, [backTo, draftId, endpoints, router]);

  // ---------- keyboard shortcuts ----------
  useKeyboardShortcuts({
    onSave: () => {
      if (refineBusy) return;
      void manualSave();
    },
    onPublish: () => {
      if (refineBusy) return;
      setConfirm("publish");
    },
  });

  // ---------- beforeunload ----------
  useEffect(() => {
    const handler = (e: BeforeUnloadEvent) => {
      if (!isDirty) return;
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [isDirty]);

  // ---------- rail meta ----------
  const rail = useMemo<RailSection[]>(
    () => (payload ? buildRail(payload) : []),
    [payload, buildRail],
  );
  const railIds = useMemo(() => rail.map((r) => r.id), [rail]);
  const activeId = useSectionObserver({ ids: railIds, topOffset: 100 });

  // ---------- responsive layout ----------
  const [layout, setLayout] = useState<"narrow" | "rail" | "split">("narrow");
  useEffect(() => {
    const compute = () => {
      if (window.matchMedia("(min-width: 1280px)").matches) setLayout("split");
      else if (window.matchMedia("(min-width: 1024px)").matches) setLayout("rail");
      else setLayout("narrow");
    };
    compute();
    const mql1 = window.matchMedia("(min-width: 1024px)");
    const mql2 = window.matchMedia("(min-width: 1280px)");
    mql1.addEventListener("change", compute);
    mql2.addEventListener("change", compute);
    return () => {
      mql1.removeEventListener("change", compute);
      mql2.removeEventListener("change", compute);
    };
  }, []);

  const gridTemplate =
    layout === "split"
      ? "220px minmax(0, 1fr) 360px"
      : layout === "rail"
        ? "220px minmax(0, 1fr)"
        : "minmax(0, 1fr)";

  // ---------- stage progress derived values ----------
  const streaming = !!generationTask && ["pending", "running"].includes(generationTask.status);

  const completedStages = useMemo(
    () => [...stages.values()].filter((s) => s.status === "completed").length,
    [stages],
  );

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

  // ---------- early returns ----------
  const showGenerationScreen =
    !!generationTask && ["pending", "running", "failed"].includes(generationTask.status);

  if (loading) {
    return (
      <div
        style={{
          minHeight: "100dvh",
          background: "var(--lv-bg)",
          display: "grid",
          placeItems: "center",
        }}
      >
        <span className="lv-loading-pulse" aria-label={t("loadFailed")} />
      </div>
    );
  }

  if (!payload || !detail) {
    // 加载结束但没拿到草稿 —— 通常是 404 / 网络错误。给用户出口。
    return (
      <div
        style={{
          minHeight: "100dvh",
          background: "var(--lv-bg)",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: "var(--lv-s-4)",
          padding: "var(--lv-s-6)",
          textAlign: "center",
        }}
      >
        <h1 className="lv-t-h2" style={{ margin: 0 }}>
          {t("loadFailed")}
        </h1>
        {error ? (
          <p className="lv-t-meta" style={{ margin: 0, color: "var(--lv-ink-3)" }}>
            {error}
          </p>
        ) : null}
        <div style={{ display: "flex", gap: "var(--lv-s-3)", marginTop: "var(--lv-s-3)" }}>
          <button
            type="button"
            onClick={() => void loadDraft()}
            className="lv-btn"
          >
            {t("saveErrorRetry")}
          </button>
          <Link href={backTo} className="lv-btn lv-btn-primary">
            {t("back")}
          </Link>
        </div>
      </div>
    );
  }

  if (showGenerationScreen) {
    const decisionSlot = ipRecognition && !cardDecided ? (
      <div className="ip-decision-slot">
        {continueError && (
          <div role="alert" className="ip-decision-error">
            {continueError}
          </div>
        )}
        <IPRecognitionCard
          recognition={ipRecognition}
          onChoose={async (mode) => {
            if (continueInFlightRef.current) return;
            continueInFlightRef.current = true;
            setCardDecided(true);
            setContinueError(null);
            try {
              if (!endpoints.continueGeneration) {
                throw new Error("continueGeneration endpoint not configured");
              }
              const { task_id } = await workshopFetch<{
                task_id: string;
                draft_id: string;
              }>(endpoints.continueGeneration(draftId), {
                method: "POST",
                body: JSON.stringify({ fidelity_mode: mode }),
              });
              continueRetryRef.current = 0;
              continueInFlightRef.current = false;
              // Trigger SSE re-subscription by swapping in a new task summary;
              // the existing useEffect keys off `generationTask` so it will
              // tear down the old stream and connect to the new task_id.
              setPhases([]);
              setStages(initStagesMap());
              setIpRecognition(null);
              setGenerationTask((prev) => ({
                id: task_id,
                kind: prev?.kind ?? "world",
                draft_type: prev?.draft_type ?? "world_draft",
                draft_id: draftId,
                status: "running",
                current_phase: null,
                current_code: null,
                current_message: null,
                last_event_seq: 0,
                error_message: null,
                started_at: new Date().toISOString(),
                finished_at: null,
                created_at: new Date().toISOString(),
                updated_at: new Date().toISOString(),
                events: [],
              }));
              startTaskTimer(new Date().toISOString());
            } catch (err) {
              continueRetryRef.current += 1;
              if (continueRetryRef.current >= MAX_CONTINUE_RETRIES) {
                setContinueError("继续生成多次失败，请刷新页面后重试");
                continueInFlightRef.current = false;
                return;
              }
              setContinueError(
                err instanceof Error ? err.message : "继续生成失败，请重试",
              );
              setCardDecided(false);
              continueInFlightRef.current = false;
            }
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
            border: 1px solid rgba(184, 92, 92, 0.35);
            background: rgba(184, 92, 92, 0.08);
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
        operationLabel={generationOperationLabel}
        subjectLabel={generationSubjectLabel(payload)}
        error={
          generationTask?.status === "failed"
            ? generationTask.error_message || error
            : error
        }
        onReset={() => startTransition(() => router.push(backTo))}
        onRetry={() => void loadDraft()}
        stages={stages}
        centerSlot={decisionSlot}
      />
    );
  }

  const title = getTitle(payload);

  return (
    <div
      className="lv-editor-root"
      style={{ background: "var(--lv-bg)", minHeight: "100dvh", color: "var(--lv-ink)" }}
    >
      <DraftStrip
        kind={kind}
        title={title}
        modeGlyph={modeGlyph}
        backTo={backTo}
        state={state}
        saving={state.status === "saving" || refineBusy}
        publishing={publishing}
        discarding={discarding}
        isDirty={isDirty}
        onManualSave={() => {
          if (refineBusy) return;
          void manualSave();
        }}
        onPublish={() => {
          if (refineBusy) return;
          setConfirm("publish");
        }}
        onDiscard={() => setConfirm("discard")}
        onBackAttempt={() => {
          if (!isDirty) return false;
          setPendingNavigate(backTo);
          setConfirm("leave");
          return true;
        }}
      />

      {layout === "narrow" && (
        <SectionRailMobile
          sections={rail}
          activeId={activeId}
          stickyTop={68}
          trailing={
            <button
              type="button"
              onClick={() => setPreviewOpen(true)}
              className="lv-t-meta lv-editor-preview-chip"
              aria-label={t("preview.openMobile")}
              style={{
                minHeight: 44,
                minWidth: 44,
                padding: "0 var(--lv-s-3)",
                whiteSpace: "nowrap",
                borderRadius: "var(--lv-r-pill)",
                border: "1px solid var(--lv-line-2)",
                background: "transparent",
                color: "var(--lv-ink-2)",
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
                gap: "var(--lv-s-2)",
              }}
            >
              <Eye size={15} strokeWidth={1.75} aria-hidden />
              <span>{t("preview.openMobile")}</span>
            </button>
          }
        />
      )}

      <div
        className="lv-editor-canvas"
        style={{
          display: "grid",
          gap: layout === "narrow" ? "var(--lv-s-12)" : "var(--lv-s-8)",
          gridTemplateColumns: gridTemplate,
          maxWidth: "var(--lv-max-w)",
          margin: "0 auto",
          padding: "var(--lv-s-8) var(--lv-pad-x) var(--lv-s-24)",
        }}
      >
        {layout !== "narrow" && (
          <aside>
            <SectionRail sections={rail} activeId={activeId} stickyTop={88} />
          </aside>
        )}

        <main
          style={{
            display: "flex",
            flexDirection: "column",
            gap: "var(--lv-s-12)",
            minWidth: 0,
          }}
        >
          {error && (
            <div
              role="alert"
              className="lv-t-meta"
              style={{
                padding: "var(--lv-s-3) var(--lv-s-4)",
                borderRadius: "var(--lv-r-card)",
                border: "1px solid rgba(184,92,92,0.3)",
                background: "rgba(184,92,92,0.08)",
                color: "var(--lv-danger)",
                display: "flex",
                alignItems: "center",
                gap: 8,
              }}
            >
              <span
                aria-hidden
                style={{
                  width: 6,
                  height: 6,
                  borderRadius: "50%",
                  background: "var(--lv-danger)",
                }}
              />
              {error}
            </div>
          )}
          {streaming && (
            <div
              style={{
                borderRadius: "var(--lv-r-card)",
                border: "1px solid var(--lv-border)",
                background: "var(--lv-surface)",
                padding: "var(--lv-s-4)",
              }}
            >
              {/* 主阶段进度条 */}
              <div className="lv-t-caps mb-2" style={{ color: "var(--lv-text-3)" }}>
                生成进度 {completedStages} / {STAGE_KEYS.length}
              </div>
              <div
                className="mb-3 h-1 w-full overflow-hidden rounded"
                style={{ background: "var(--lv-surface-2)" }}
              >
                <div
                  className="h-full transition-all"
                  style={{
                    width: `${(completedStages / STAGE_KEYS.length) * 100}%`,
                    background: "var(--lv-accent)",
                  }}
                />
              </div>

              {/* 当前 in-progress 阶段名 + 子任务进度 */}
              {currentStageInfo && (
                <div className="lv-t-body">
                  <span style={{ color: "var(--lv-text-2)" }}>{currentStageInfo.label}</span>
                  {currentStageInfo.subtaskTotal !== undefined &&
                    currentStageInfo.subtaskTotal > 0 && (
                      <>
                        <span className="lv-t-meta ml-2" style={{ color: "var(--lv-text-3)" }}>
                          {currentStageInfo.subtaskDone ?? 0} / {currentStageInfo.subtaskTotal}
                        </span>
                        <div
                          className="mt-1 h-0.5 w-32 overflow-hidden rounded"
                          style={{ background: "var(--lv-surface-2)" }}
                        >
                          <div
                            className="h-full transition-all"
                            style={{
                              width: `${((currentStageInfo.subtaskDone ?? 0) / currentStageInfo.subtaskTotal) * 100}%`,
                              background: "var(--lv-accent)",
                            }}
                          />
                        </div>
                      </>
                    )}
                </div>
              )}
            </div>
          )}

          {renderBody({ payload, setPayload, rail, detail, draftId, kind, saveNow, setBusy: setRefineBusy })}
        </main>

        {layout === "split" && (
          <aside>
            <div
              style={{
                position: "sticky",
                top: 88,
                display: "flex",
                flexDirection: "column",
                gap: "var(--lv-s-4)",
                maxHeight: "calc(100dvh - 100px)",
                overflowY: "auto",
                paddingRight: "var(--lv-s-2)",
                paddingTop: "var(--lv-s-6)",
              }}
            >
              <div className="lv-t-caps" style={{ color: "var(--lv-ink-3)" }}>
                {t("preview.label")}
              </div>
              <p className="lv-t-meta" style={{ margin: 0, color: "var(--lv-ink-4)" }}>
                {t("preview.subtitle")}
              </p>
              {renderPreview(payload)}
            </div>
          </aside>
        )}
      </div>

      <Drawer
        open={previewOpen && layout !== "split"}
        onClose={() => setPreviewOpen(false)}
        title={t("preview.label")}
        mobileBottom
      >
        {renderPreview(payload)}
      </Drawer>

      {layout === "narrow" && (
        <div className="lv-editor-mobile-actions" role="toolbar" aria-label="Draft actions">
          <button
            type="button"
            onClick={() => setConfirm("discard")}
            disabled={discarding}
            className="lv-editor-mobile-action lv-editor-mobile-action-icon"
            aria-label={discarding ? t("discarding") : t("discard")}
          >
            <Trash2 size={16} strokeWidth={1.75} aria-hidden />
          </button>
          <button
            type="button"
            onClick={() => void manualSave()}
            disabled={refineBusy || state.status === "saving" || (!isDirty && state.status !== "error")}
            className="lv-editor-mobile-action"
          >
            <Save size={16} strokeWidth={1.75} aria-hidden />
            <span>{state.status === "saving" ? t("saving") : t("manualSave")}</span>
          </button>
          <button
            type="button"
            onClick={() => setConfirm("publish")}
            disabled={publishing}
            className="lv-editor-mobile-action lv-editor-mobile-action-primary"
          >
            <span>{publishing ? t("publishing") : t("publishConfirmCta")}</span>
          </button>
        </div>
      )}

      <Modal
        open={confirm === "publish"}
        onClose={() => setConfirm(null)}
        title={t("publishConfirmTitle")}
        footer={
          <>
            <button type="button" className="lv-btn lv-btn-sm" onClick={() => setConfirm(null)}>
              {t("leaveConfirmStay")}
            </button>
            <button
              type="button"
              className="lv-btn lv-btn-primary lv-btn-sm"
              onClick={() => {
                setConfirm(null);
                void doPublish();
              }}
            >
              {t("publishConfirmCta")}
            </button>
          </>
        }
      >
        {t("publishConfirmDesc")}
      </Modal>

      <Modal
        open={confirm === "discard"}
        onClose={() => setConfirm(null)}
        title={t("discardConfirmTitle")}
        footer={
          <>
            <button type="button" className="lv-btn lv-btn-sm" onClick={() => setConfirm(null)}>
              {t("leaveConfirmStay")}
            </button>
            <button
              type="button"
              className="lv-btn lv-btn-sm"
              style={{ color: "var(--lv-danger)", borderColor: "rgba(184,92,92,0.3)" }}
              onClick={() => {
                setConfirm(null);
                void doDiscard();
              }}
            >
              {t("discardConfirmCta")}
            </button>
          </>
        }
      >
        {t("discardConfirmDesc")}
      </Modal>

      <Modal
        open={confirm === "leave"}
        onClose={() => setConfirm(null)}
        title={t("leaveConfirmTitle")}
        footer={
          <>
            <button type="button" className="lv-btn lv-btn-sm" onClick={() => setConfirm(null)}>
              {t("leaveConfirmStay")}
            </button>
            <button
              type="button"
              className="lv-btn lv-btn-sm"
              onClick={() => {
                const target = pendingNavigate ?? backTo;
                setConfirm(null);
                setPendingNavigate(null);
                startTransition(() => router.push(target));
              }}
            >
              {t("leaveConfirmLeave")}
            </button>
          </>
        }
      >
        {t("leaveConfirmDesc")}
      </Modal>

      <style jsx>{`
        @media (max-width: 767px) {
          .lv-editor-canvas {
            gap: var(--lv-s-8) !important;
            padding-top: var(--lv-s-6) !important;
            padding-bottom: calc(112px + env(safe-area-inset-bottom)) !important;
          }

          .lv-editor-preview-chip span {
            display: none;
          }

          .lv-editor-mobile-actions {
            position: fixed;
            left: 0;
            right: 0;
            bottom: 0;
            z-index: var(--lv-z-sticky);
            display: grid;
            grid-template-columns: 44px minmax(0, 0.86fr) minmax(0, 1.14fr);
            gap: var(--lv-s-2);
            padding: var(--lv-s-3) var(--lv-pad-x) calc(var(--lv-s-3) + env(safe-area-inset-bottom));
            border-top: 1px solid var(--lv-line);
            background: rgba(8, 8, 10, 0.96);
            -webkit-backdrop-filter: saturate(120%);
            backdrop-filter: saturate(120%);
          }

          .lv-editor-mobile-action {
            min-width: 0;
            min-height: 44px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: var(--lv-s-2);
            padding: 0 var(--lv-s-3);
            border: 1px solid var(--lv-line-2);
            border-radius: var(--lv-r-pill);
            background: transparent;
            color: var(--lv-ink-2);
            font-family: var(--lv-font-sans);
            font-size: var(--lv-t-meta);
            font-weight: 500;
            line-height: 1.2;
            white-space: nowrap;
          }

          .lv-editor-mobile-action:disabled {
            opacity: 0.45;
          }

          .lv-editor-mobile-action-icon {
            padding: 0;
            color: var(--lv-ink-3);
          }

          .lv-editor-mobile-action-primary {
            border-color: var(--lv-ink);
            background: var(--lv-ink);
            color: var(--lv-bg);
          }
        }

        @media (min-width: 768px) {
          .lv-editor-mobile-actions {
            display: none;
          }
        }
      `}</style>

    </div>
  );
}
