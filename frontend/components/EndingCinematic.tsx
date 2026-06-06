"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";

import { useGameStore } from "@/stores/game";
import type { PathNode } from "@/lib/types";

/* ── Ending theme config — lv-* tokens (§12.6) ── */

interface EndingTheme {
  accentVar: string;
  labelKey: "perfect" | "good" | "bad" | "timeout" | "testExit" | "withdrawn";
}

const THEMES: Record<string, EndingTheme> = {
  perfect: { accentVar: "var(--lv-accent)", labelKey: "perfect" },
  good: { accentVar: "var(--lv-warn)", labelKey: "good" },
  bad: { accentVar: "var(--lv-danger)", labelKey: "bad" },
  timeout: { accentVar: "var(--lv-ink-3)", labelKey: "timeout" },
  test_exit: { accentVar: "var(--lv-ink-3)", labelKey: "testExit" },
  // 玩家主动退场：银雾灰，区别于"挣来"的结局
  withdrawn: { accentVar: "var(--lv-accent-2)", labelKey: "withdrawn" },
};

function getTheme(type: string): EndingTheme {
  return THEMES[type] ?? THEMES.timeout;
}

const IMPACT_COLOR: Record<string, string> = {
  positive: "var(--lv-accent)",
  negative: "var(--lv-danger)",
  neutral: "var(--lv-ink-3)",
};

type Phase = "curtain" | "narrative" | "credits" | "actions";

/* ── StatCard helper ── */

function StatCard({ value, label }: { value: number | string; label: string }) {
  return (
    <div
      className="text-center"
      style={{
        padding: "var(--lv-s-6)",
        border: "1px solid var(--lv-line)",
        background: "var(--lv-bg-1)",
        borderRadius: "var(--lv-r-card)",
      }}
    >
      <div className="lv-t-h2" style={{ color: "var(--lv-ink)" }}>
        {value}
      </div>
      <div className="lv-t-micro mt-1">{label}</div>
    </div>
  );
}

/* ── Badge helper ── */

function TypeBadge({ theme, label }: { theme: EndingTheme; label: string }) {
  return (
    <span
      className="lv-t-caps inline-block"
      style={{
        padding: "var(--lv-s-1) var(--lv-s-4)",
        border: "1px solid",
        borderColor: theme.accentVar,
        color: theme.accentVar,
        borderRadius: "var(--lv-r-pill)",
      }}
    >
      {label}
    </span>
  );
}

/* ── Main component ── */

export function EndingCinematic() {
  const router = useRouter();
  const ending = useGameStore((s) => s.ending);
  const gameState = useGameStore((s) => s.gameState);
  const messages = useGameStore((s) => s.messages);
  const reset = useGameStore((s) => s.reset);

  const t = useTranslations("play.ending");

  const [phase, setPhase] = useState<Phase>("curtain");
  const [narrativeIndex, setNarrativeIndex] = useState(0);
  const [showTitle, setShowTitle] = useState(false);

  const endingType = ending?.ending_type ?? "timeout";
  const theme = useMemo(() => getTheme(endingType), [endingType]);

  /* Split narrative into segments, interleave with path flashbacks */
  const summary = ending?.summary;
  const narrativeSegments = useMemo(() => {
    if (!summary) return [];
    const lines = summary.ending_narrative
      .split("\n")
      .map((l) => l.trim())
      .filter(Boolean);
    const pathNodes = summary.path_review ?? [];
    const result: { type: "narrative" | "flashback"; text: string }[] = [];
    for (let i = 0; i < lines.length; i++) {
      result.push({ type: "narrative", text: lines[i] });
      if (pathNodes[i]) {
        result.push({
          type: "flashback",
          text: `${pathNodes[i].time} — ${pathNodes[i].summary}`,
        });
      }
    }
    return result;
  }, [summary]);

  const totalSegments = narrativeSegments.length;

  const handleSkip = useCallback(() => {
    if (phase !== "actions") setPhase("actions");
  }, [phase]);

  /* Phase 0: curtain auto-advance (cinematic 例外 B)。
     主动退场（withdrawn）的落幕白由 LLM 现生成、有延迟：summary 未到时停在固定
     pre 描述（见 curtain 渲染），等落幕白到了再短停一拍进入叙事；其余结局保持 4s。 */
  useEffect(() => {
    if (phase !== "curtain") return;
    const waitingForSendoff = endingType === "withdrawn" && !summary;
    if (waitingForSendoff) return;
    const hold = endingType === "withdrawn" ? 1500 : 4000;
    const timer = setTimeout(() => setPhase("narrative"), hold);
    return () => clearTimeout(timer);
  }, [phase, endingType, summary]);

  /* Phase 1a: narrative segment auto-advance every 3.5s */
  useEffect(() => {
    if (phase !== "narrative" || narrativeIndex >= totalSegments) return;
    const timer = setTimeout(() => {
      setNarrativeIndex((i) => i + 1);
    }, 3500);
    return () => clearTimeout(timer);
  }, [phase, narrativeIndex, totalSegments]);

  /* Phase 1b: narrative segments finished -> show title then transition to credits */
  useEffect(() => {
    if (phase !== "narrative" || narrativeIndex < totalSegments) return;

    if (totalSegments === 0) {
      setPhase("credits");
      return;
    }

    setShowTitle(true);
    const timer = setTimeout(() => {
      setPhase("credits");
    }, 3000);

    return () => clearTimeout(timer);
  }, [phase, narrativeIndex, totalSegments]);

  if (!ending) return null;

  const playerRounds = messages.filter((m) => m.role === "user").length;
  const clueCount = gameState?.discovered_clues.length ?? 0;
  const eventCount = gameState?.triggered_events.length ?? 0;
  const evidenceReview = ending.summary?.evidence_review ?? null;
  const pathReview = ending.summary?.path_review ?? [];

  /* ── Phase 0: Curtain ── */
  if (phase === "curtain") {
    return (
      <div
        className="lv-theme fixed inset-0 flex cursor-pointer items-center justify-center"
        style={{
          zIndex: "var(--lv-z-overlay)" as unknown as number,
          background: "var(--lv-bg)",
        }}
        onClick={handleSkip}
      >
        <div className="flex flex-col items-center" style={{ gap: "var(--lv-s-6)" }}>
          <div
            className="h-px w-48 animate-pulse"
            style={{ backgroundColor: theme.accentVar, opacity: 0.6 }}
          />
          {/* 主动退场落幕白生成中：固定 pre 描述顶住等待空窗 */}
          {endingType === "withdrawn" && !summary && (
            <p
              className="lv-t-narrative max-w-md px-6 text-center animate-[fadeIn_0.8s_ease-out]"
              style={{ color: "var(--lv-ink-3)" }}
            >
              {t("preparing")}
            </p>
          )}
        </div>
        <SkipHint label={t("skip")} />
      </div>
    );
  }

  /* ── Phase 1: Narrative ── */
  if (phase === "narrative") {
    const current = narrativeSegments[narrativeIndex];
    return (
      <div
        className="lv-theme fixed inset-0 flex cursor-pointer flex-col items-center justify-center px-6"
        style={{
          zIndex: "var(--lv-z-overlay)" as unknown as number,
          background: "var(--lv-bg)",
        }}
        onClick={handleSkip}
      >
        {current && !showTitle && (
          <p
            key={narrativeIndex}
            className={`max-w-xl text-center animate-[fadeIn_0.8s_ease-out] ${
              current.type === "flashback"
                ? "lv-t-meta"
                : "lv-t-narrative"
            }`}
            style={{
              color:
                current.type === "flashback"
                  ? "var(--lv-ink-3)"
                  : "var(--lv-ink-2)",
            }}
          >
            {current.text}
          </p>
        )}
        {showTitle && (
          <div
            className="flex flex-col items-center animate-[fadeIn_0.8s_ease-out]"
            style={{ gap: "var(--lv-s-4)" }}
          >
            <TypeBadge theme={theme} label={t(theme.labelKey)} />
            <h1 className="lv-t-h1" style={{ color: "var(--lv-ink)" }}>
              {ending.title}
            </h1>
          </div>
        )}
        <SkipHint label={t("skip")} />
      </div>
    );
  }

  /* ── Phase 2: Credits ── */
  if (phase === "credits") {
    return (
      <div
        className="lv-theme fixed inset-0 cursor-pointer overflow-y-auto"
        style={{
          zIndex: "var(--lv-z-overlay)" as unknown as number,
          background: "var(--lv-bg)",
        }}
        onClick={handleSkip}
      >
        <div className="mx-auto max-w-xl px-6 py-16 sm:py-24">
          {/* Title + badge */}
          <div
            className="flex flex-col items-center text-center"
            style={{ gap: "var(--lv-s-3)" }}
          >
            <TypeBadge theme={theme} label={t(theme.labelKey)} />
            <h1 className="lv-t-h1" style={{ color: "var(--lv-ink)" }}>
              {ending.title}
            </h1>
          </div>

          {/* Evidence review */}
          {evidenceReview && (
            <div className="mt-12 space-y-4">
              <h2 className="lv-t-caps">{t("evidenceReview")}</h2>
              <div className="grid grid-cols-3 gap-3">
                <StatCard value={evidenceReview.found.length} label={t("found")} />
                <StatCard value={evidenceReview.missed.length} label={t("missed")} />
                <StatCard
                  value={`${Math.round(evidenceReview.accuracy * 100)}%`}
                  label={t("accuracy")}
                />
              </div>
              {evidenceReview.found.length > 0 && (
                <div className="space-y-1">
                  <p className="lv-t-meta">{t("foundList")}</p>
                  {evidenceReview.found.map((e) => (
                    <p
                      key={e}
                      className="lv-t-body"
                      style={{ color: "var(--lv-ink-2)" }}
                    >
                      • {e}
                    </p>
                  ))}
                </div>
              )}
              {evidenceReview.missed.length > 0 && (
                <div className="space-y-1">
                  <p className="lv-t-meta">{t("missedList")}</p>
                  {evidenceReview.missed.map((e) => (
                    <p
                      key={e}
                      className="lv-t-body"
                      style={{ color: "var(--lv-danger)", opacity: 0.7 }}
                    >
                      • {e}
                    </p>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Path review timeline */}
          {pathReview.length > 0 && (
            <div className="mt-12">
              <h2 className="lv-t-caps mb-4">{t("pathReview")}</h2>
              <div className="relative pl-6">
                <div
                  className="absolute left-[7px] top-1 bottom-1 w-px"
                  style={{ background: "var(--lv-line-2)" }}
                />
                {pathReview.map((node: PathNode, i: number) => (
                  <div key={i} className="relative mb-6 last:mb-0">
                    <div
                      className="absolute -left-6 top-1.5 h-3.5 w-3.5"
                      style={{
                        background:
                          IMPACT_COLOR[node.impact] ?? IMPACT_COLOR.neutral,
                        border: "2px solid var(--lv-bg)",
                        borderRadius: "var(--lv-r-pill)",
                      }}
                    />
                    <p className="lv-t-micro">{node.time}</p>
                    <p
                      className="lv-t-body mt-1"
                      style={{ color: "var(--lv-ink-2)" }}
                    >
                      {node.event}
                    </p>
                    <p className="lv-t-meta mt-1">{node.summary}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Game stats */}
          <div className="mt-12">
            <h2 className="lv-t-caps mb-4">{t("stats")}</h2>
            <div className="grid grid-cols-3 gap-3">
              <StatCard value={playerRounds} label={t("rounds")} />
              <StatCard value={clueCount} label={t("clues")} />
              <StatCard value={eventCount} label={t("events")} />
            </div>
          </div>

          {/* Continue button */}
          <div className="mt-12 flex justify-center">
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                setPhase("actions");
              }}
              className="lv-btn"
            >
              {t("continue")}
            </button>
          </div>
        </div>
        <SkipHint label={t("skip")} />
      </div>
    );
  }

  /* ── Phase 3: Actions ── */
  return (
    <div
      className="lv-theme fixed inset-0 flex flex-col items-center justify-center px-6"
      style={{
        zIndex: "var(--lv-z-overlay)" as unknown as number,
        background: "var(--lv-bg)",
      }}
    >
      <div
        className="flex flex-col items-center animate-[fadeIn_0.8s_ease-out]"
        style={{ gap: "var(--lv-s-4)" }}
      >
        <TypeBadge theme={theme} label={t(theme.labelKey)} />
        <h1 className="lv-t-h1" style={{ color: "var(--lv-ink)" }}>
          {ending.title}
        </h1>
      </div>

      <div className="mt-12 flex flex-col items-center gap-3 sm:flex-row">
        <button
          type="button"
          onClick={() => {
            reset();
            router.push("/");
          }}
          className="lv-btn lv-btn-primary lv-btn-lg"
        >
          {t("backHome")}
        </button>
        <button
          type="button"
          onClick={() => router.push("/history")}
          className="lv-btn lv-btn-lg"
        >
          {t("viewHistory")}
        </button>
      </div>
    </div>
  );
}

/* ── Skip hint overlay ── */

function SkipHint({ label }: { label: string }) {
  return (
    <p
      className="lv-t-micro fixed bottom-8 left-0 right-0 text-center animate-pulse"
      style={{ color: "var(--lv-ink-4)" }}
    >
      {label}
    </p>
  );
}
