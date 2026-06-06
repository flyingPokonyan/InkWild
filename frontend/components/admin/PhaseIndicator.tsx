"use client";

import { useTranslations } from "next-intl";

import type { AdminPhaseEntry } from "@/lib/admin-progress-state";

const PHASE_KEYS = [
  "boot",
  "research",
  "world_base",
  "characters",
  "playable",
  "images",
  "validating",
  "script_base",
  "events",
  "endings",
] as const;

type PhaseKey = (typeof PHASE_KEYS)[number];

function isPhaseKey(s: string): s is PhaseKey {
  return (PHASE_KEYS as readonly string[]).includes(s);
}

export function PhaseIndicator({
  phases,
  elapsed,
}: {
  phases: AdminPhaseEntry[];
  elapsed: number;
}) {
  const t = useTranslations("admin.phase");
  const tLabel = useTranslations("admin.phase.phaseLabels");

  const resolvePhaseLabel = (phase: AdminPhaseEntry): string => {
    const base = isPhaseKey(phase.phase) ? tLabel(phase.phase) : phase.phase;
    if (phase.phase === "research" && phase.stageLabel) {
      return `${base} · ${phase.stageLabel}`;
    }
    return base;
  };

  const MAX_DISPLAY = 6;
  const displayPhases = phases.slice(-MAX_DISPLAY);
  const progressPercent =
    phases.length === 0 ? 5 : Math.min((phases.length / 9) * 100, 98);

  const minutes = Math.floor(elapsed / 60);
  const seconds = (elapsed % 60).toString().padStart(2, "0");

  return (
    <div className="flex flex-col items-center justify-center w-full max-w-lg mx-auto">
      {/* Progress bar */}
      <div
        className="w-full h-px mb-12 overflow-hidden relative"
        style={{ background: "var(--lv-line)" }}
      >
        <div
          className="absolute top-0 left-0 h-full transition-all"
          style={{
            width: `${progressPercent}%`,
            background: "var(--lv-accent)",
            transitionDuration: "var(--lv-dur-page)",
            transitionTimingFunction: "var(--lv-ease)",
          }}
        />
      </div>

      {/* Steps */}
      <div className="flex flex-col items-center justify-end h-56 space-y-4 w-full relative">
        <div
          className="absolute top-0 left-0 right-0 h-16 z-10 pointer-events-none"
          style={{
            background:
              "linear-gradient(to bottom, var(--lv-bg) 0%, transparent 100%)",
          }}
        />

        {phases.length === 0 && (
          <span className="lv-t-caps">{t("connecting")}</span>
        )}

        {displayPhases.map((p, idx) => {
          const isLast = idx === displayPhases.length - 1;
          const distance = displayPhases.length - 1 - idx;

          const opacityClass =
            distance === 0
              ? "opacity-100"
              : distance === 1
                ? "opacity-60"
                : distance === 2
                  ? "opacity-30"
                  : distance === 3
                    ? "opacity-10"
                    : "opacity-0 hidden md:block";

          const scaleClass = distance === 0 ? "scale-100" : "scale-95";

          let color: string = "var(--lv-ink)";
          if (p.status === "error") color = "var(--lv-danger)";
          else if (p.status === "warning") color = "var(--lv-warn)";
          else if (isLast && p.status === "running") color = "var(--lv-accent)";
          else if (!isLast || p.status === "done") color = "var(--lv-ink-3)";

          return (
            <div
              key={p.id}
              className={`flex flex-col items-center transition-all transform ${opacityClass} ${scaleClass}`}
              style={{
                transitionDuration: "var(--lv-dur-page)",
                transitionTimingFunction: "var(--lv-ease)",
              }}
            >
              <div className="lv-t-h3" style={{ color }}>
                {resolvePhaseLabel(p)}
                {isLast && p.status === "running" && (
                  <span className="ml-1 inline-block animate-pulse">…</span>
                )}
              </div>

              {isLast && p.message && (
                <div
                  className="lv-t-meta mt-3 max-w-sm text-center leading-relaxed h-8"
                  style={{ color: "var(--lv-ink-4)" }}
                >
                  {p.message}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Elapsed Time */}
      {phases.length > 0 && (
        <div className="mt-8">
          <span className="lv-t-micro">
            {t("elapsed", { time: `${minutes}:${seconds}` })}
          </span>
        </div>
      )}
    </div>
  );
}
