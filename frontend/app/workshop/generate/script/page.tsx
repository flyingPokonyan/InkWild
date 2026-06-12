"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";

import {
  CardDetailStrip,
  ChoiceScene,
  type DetailEntry,
  MediaChoiceCard,
  PromptComposer,
} from "@/components/choice";
import { GenerationLoadingScreen } from "@/components/admin/GenerationLoadingScreen";
import { LoadingPulse } from "@/components/ui/LoadingPulse";
import {
  appendAdminPhaseEvent,
  completeAdminPhaseTimeline,
  markLatestAdminPhaseAsError,
  type AdminPhaseEntry,
} from "@/lib/admin-progress-state";
import { LV_EASE, lvStaggerContainer } from "@/lib/motion";
import {
  getGenerationTask,
  workshopFetch,
  streamAdminEvents,
  type AdminProgressEvent,
} from "@/lib/workshop-api";
import type { AdminGenerationTaskCreateResponse, AdminWorldListResponse } from "@/lib/types";

type GenStep = "world_select" | "prompt";
const STEPS_ORDER: GenStep[] = ["world_select", "prompt"];
const STREAM_RECONNECT_LIMIT = 5;
const STREAM_RECONNECT_DELAY_MS = 1200;

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function streamPath(taskId: string, afterSeq: number): string {
  const query = afterSeq > 0 ? `?after_seq=${afterSeq}` : "";
  return `/api/workshop/generation-tasks/${taskId}/stream${query}`;
}

function compactText(value: string, max = 34): string {
  const text = value.trim().replace(/\s+/g, " ");
  if (text.length <= max) {
    return text;
  }
  return `${text.slice(0, max)}…`;
}

function GenerateScriptPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const initialWorldId = searchParams?.get("world_id");
  
  const [step, setStep] = useState<GenStep>(initialWorldId ? "prompt" : "world_select");
  const [worldId, setWorldId] = useState<string | null>(initialWorldId);
  const [worlds, setWorlds] = useState<AdminWorldListResponse["published"] | null>(null);
  const [loadingWorlds, setLoadingWorlds] = useState(!initialWorldId);

  const [outline, setOutline] = useState("");
  const [focusedWorldId, setFocusedWorldId] = useState<string | null>(null);

  const [generating, setGenerating] = useState(false);
  const [phases, setPhases] = useState<AdminPhaseEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const streamAbortRef = useRef<AbortController | null>(null);
  const observerRef = useRef<IntersectionObserver | null>(null);

  // 移动端用 IntersectionObserver 跟随 scroll-snap 中心卡驱动 CardDetailStrip；
  // PC（hover 可用）只走 onFocus（hover）。与 start 页 attachCarousel 同款。
  const attachCarousel = useCallback(
    (node: HTMLDivElement | null) => {
      observerRef.current?.disconnect();
      observerRef.current = null;
      if (!node) return;
      if (typeof window !== "undefined" && window.matchMedia("(hover: hover)").matches) return;

      const observer = new IntersectionObserver(
        (entries) => {
          let bestId: string | null = null;
          let bestRatio = 0;
          entries.forEach((e) => {
            if (e.isIntersecting && e.intersectionRatio > bestRatio) {
              bestRatio = e.intersectionRatio;
              bestId = e.target.getAttribute("data-card-id");
            }
          });
          if (bestId) setFocusedWorldId(bestId);
        },
        { root: node, rootMargin: "0px -40% 0px -40%", threshold: [0.5, 0.75, 1] },
      );
      node.querySelectorAll("[data-card-id]").forEach((card) => observer.observe(card));
      observerRef.current = observer;
    },
    // ref 回调在 grid 挂载/卸载时由 React 调用，挂载时世界卡已渲染；无需依赖 worlds。
    [],
  );

  useEffect(() => {
    return () => {
      streamAbortRef.current?.abort();
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    };
  }, []);

  useEffect(() => {
     let active = true;
     workshopFetch<AdminWorldListResponse>("/api/workshop/worlds")
       .then(res => {
          if (active) {
             setWorlds(res.published);
             if (!initialWorldId) {
               setLoadingWorlds(false);
             }
          }
       })
       .catch(err => {
          if (active) {
             if (!initialWorldId) {
               setError(err instanceof Error ? err.message : "无法获取世界列表");
               setLoadingWorlds(false);
             }
          }
       });
     return () => { active = false; };
  }, [initialWorldId]);

  const startTimer = () => { setElapsed(0); timerRef.current = setInterval(() => setElapsed(s => s + 1), 1000); };
  const stopTimer = () => { if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null; } };

  const trackPhase = useCallback((event: AdminProgressEvent) => {
    setPhases((prev) => appendAdminPhaseEvent(prev, event));
  }, []);

  const trackWarning = useCallback((event: AdminProgressEvent) => {
    setPhases((prev) => appendAdminPhaseEvent(prev, event, "warning"));
  }, []);

  const handleSelectWorld = (id: string) => {
     setWorldId(id);
     setStep("prompt");
  };

  const handleBackToWorldSelect = () => {
     if (!initialWorldId) {
        setWorldId(null);
        setStep("world_select");
     } else {
        router.push("/workshop");
     }
  };

  const handleGenerate = async () => {
    if (!worldId || generating) return;
    
    setGenerating(true); 
    setError(null); 
    setPhases([]); 
    startTimer();

    let taskMeta: AdminGenerationTaskCreateResponse | null = null;
    let didComplete = false;
    try {
      taskMeta = await workshopFetch<AdminGenerationTaskCreateResponse>("/api/workshop/script-generation-tasks", {
        method: "POST",
        body: JSON.stringify({ world_id: worldId, outline: outline.trim() }),
      });
    } catch (reason) {
      stopTimer();
      setError(reason instanceof Error ? reason.message : "创建生成任务失败");
      setGenerating(false);
      return;
    }

    let afterSeq = 0;
    let reconnects = 0;
    while (!didComplete) {
      let streamError: string | null = null;
      const abortController = new AbortController();
      streamAbortRef.current = abortController;
      const streamResult = await streamAdminEvents(streamPath(taskMeta.task_id, afterSeq), {
        onEvent: (event) => {
          if (typeof event.seq === "number" && event.seq > afterSeq) {
            afterSeq = event.seq;
          }
        },
        onProgress: trackPhase,
        onWarning: trackWarning,
        onResult: () => { didComplete = true; },
        onError: (m) => {
          streamError = m;
        },
      }, {
        signal: abortController.signal,
      });
      if (streamAbortRef.current === abortController) {
        streamAbortRef.current = null;
      }

      if (streamResult.aborted) {
        stopTimer();
        setGenerating(false);
        return;
      }

      const task = await getGenerationTask(taskMeta.task_id).catch(() => null);
      if (task?.status === "succeeded") {
        didComplete = true;
        break;
      }
      if (task?.status === "failed" || task?.status === "cancelled") {
        stopTimer();
        setGenerating(false);
        setError(task.error_message || streamError || "生成失败");
        setPhases((prev) => markLatestAdminPhaseAsError(prev));
        return;
      }

      reconnects += 1;
      if (reconnects > STREAM_RECONNECT_LIMIT || streamResult.timedOut) {
        stopTimer();
        setGenerating(false);
        setError("连接不稳定，生成任务仍在后台运行。请稍后返回创作工坊查看草稿。");
        setPhases((prev) => markLatestAdminPhaseAsError(prev));
        return;
      }
      await sleep(STREAM_RECONNECT_DELAY_MS * reconnects);
    }

    stopTimer();
    
    if (!taskMeta) {
      setGenerating(false);
      return;
    }

    if (!didComplete) { 
      setGenerating(false); 
      setPhases((prev) => markLatestAdminPhaseAsError(prev));
      return; 
    }
    
    setPhases((prev) => completeAdminPhaseTimeline(prev));
    router.push(taskMeta.draft_url);
  };

  const currentStepIndex = STEPS_ORDER.indexOf(step);
  const selectedWorld = worlds?.find((item) => item.id === worldId) || null;
  const scriptSubjectLabel = selectedWorld
    ? outline.trim()
      ? `《${selectedWorld.name}》 · ${compactText(outline, 22)}`
      : `《${selectedWorld.name}》 · AI 自动构思中`
    : outline.trim()
      ? `当前世界 · ${compactText(outline, 22)}`
      : "当前世界 · AI 自动构思中";

  const focusedWorld = focusedWorldId
    ? worlds?.find((w) => w.id === focusedWorldId) ?? null
    : null;
  const worldEntries: DetailEntry[] = focusedWorld
    ? [
        ...(focusedWorld.genre ? [{ label: "题材", value: focusedWorld.genre }] : []),
        ...(focusedWorld.era ? [{ label: "时代", value: focusedWorld.era }] : []),
        ...(focusedWorld.script_count
          ? [{ label: "剧本", value: `${focusedWorld.script_count} 部` }]
          : []),
      ]
    : [];

  if (generating || phases.length > 0) {
    return (
      <GenerationLoadingScreen
        phases={phases}
        elapsed={elapsed}
        operationLabel="剧本生成中"
        subjectLabel={scriptSubjectLabel}
        error={error}
        onReset={() => {
          setPhases([]);
          setError(null);
          setGenerating(false);
          router.push("/workshop");
        }}
        onRetry={() => {
          void handleGenerate();
        }}
      />
    );
  }

  return (
    <ChoiceScene
      eyebrow="创作 · 剧本"
      title={step === "world_select" ? "选择基底世界" : "剧本概述"}
      description={
        step === "world_select"
          ? "剧本将在这个世界里展开。"
          : "写下方向、钩子或转折；留空就交给 AI 自由发挥。"
      }
      coverImage={step === "prompt" ? selectedWorld?.cover_image ?? null : null}
      onBack={step === "world_select" ? () => router.push("/workshop") : handleBackToWorldSelect}
      backLabel={step === "world_select" || initialWorldId ? "← 返回工坊" : "← 上一步"}
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
          {step === "world_select" &&
            (loadingWorlds ? (
              <div style={{ display: "flex", justifyContent: "center", padding: "var(--lv-s-8) 0" }}>
                <LoadingPulse variant="block" />
              </div>
            ) : worlds && worlds.length === 0 ? (
              <div
                style={{
                  maxWidth: 420,
                  margin: "0 auto",
                  textAlign: "center",
                  display: "flex",
                  flexDirection: "column",
                  gap: "var(--lv-s-6)",
                }}
              >
                <p className="lv-t-body" style={{ color: "var(--lv-ink-3)", lineHeight: 1.7 }}>
                  还没有已发布的世界。先去创造并发布一个世界，再回来写剧本。
                </p>
                <Link
                  href="/workshop/generate/world"
                  className="lv-cta-ivory"
                  style={{ maxWidth: 240, margin: "0 auto" }}
                >
                  去创造世界
                </Link>
              </div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: "var(--lv-s-4)" }}>
                <div
                  ref={attachCarousel}
                  onMouseLeave={() => setFocusedWorldId(null)}
                  className="lv-media-grid"
                  style={{ maxWidth: 920, margin: "0 auto", width: "100%" }}
                >
                  {worlds?.map((w) => (
                    <MediaChoiceCard
                      key={w.id}
                      cardId={w.id}
                      coverImage={w.cover_image}
                      title={w.name}
                      selected={false}
                      onSelect={() => handleSelectWorld(w.id)}
                      onFocus={() => setFocusedWorldId(w.id)}
                    />
                  ))}
                </div>
                <CardDetailStrip
                  cardKey={focusedWorld?.id ?? "empty"}
                  entries={worldEntries}
                  description={focusedWorld?.description}
                  descriptionMaxChars={180}
                />
              </div>
            ))}

          {step === "prompt" && (
            <PromptComposer
              value={outline}
              onChange={setOutline}
              onSubmit={() => void handleGenerate()}
              placeholder="留下起因、转折或钩子，留空也行……"
              ctaLabel={outline.trim() ? "开始生成" : "全部交给 AI"}
              ariaLabel="剧本概述"
              autoFocus
            />
          )}
        </motion.div>
      </AnimatePresence>
    </ChoiceScene>
  );
}

export default function GenerateScriptPage() {
  return (
    <Suspense
      fallback={
        <div
          className="lv-theme"
          style={{
            minHeight: "100dvh",
            display: "grid",
            placeItems: "center",
            background: "var(--lv-bg)",
          }}
        >
          <LoadingPulse variant="block" />
        </div>
      }
    >
      <GenerateScriptPageContent />
    </Suspense>
  );
}
