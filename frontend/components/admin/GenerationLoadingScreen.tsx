"use client";

/**
 * 创作工坊 AI 生成长任务（原创世界数分钟 · IP 复刻世界约 10–20min，主要耗在 ip_research
 *   与 images 两步）—— 世界生成 / 剧本生成 / 重新生成 共用。
 *
 * 视觉：黑底 + 中央径向呼吸光 + edge vignette；3 行文字 + 8px 暖金脉冲圆 + 1px 真进度条。
 * 数据：
 *   · 进度条 → buildAdminLoadingSnapshot + computeWeightedProgress（SSE phase 加权）
 *   · 计时器 → 纯已用时间（elapsed 秒，向上走），与进度条无关、不估剩余
 * 字体规则：
 *   · context label / eyebrow / 错误描述 → sans t-meta（中文禁用 mono caps/micro，§1.1）
 *   · phase headline / 错误标题 → serif h2（§1.1 ② italic 高亮 / 标题级）
 *   · 进度数字（47% · 3:05）→ sans tabular-nums
 * 文案规则：
 *   · 错误标题统一 "生成被中断"（不写"无法连接到叙事引擎"系统术语）
 *   · 错误描述透传 caller 的 error，无 error 时 fallback "请稍后再试。"
 *   · 按钮 "返回" / "重试"（不写"返回调整 / 再试一次"）
 */

import { useMemo, useRef, type ReactNode } from "react";

import { AmbientAura } from "@/components/choice/AmbientAura";
import { LoadingPulse } from "@/components/ui/LoadingPulse";
import type { AdminPhaseEntry } from "@/lib/admin-progress-state";
import {
  buildAdminLoadingSnapshot,
  computeWeightedProgress,
  EXPECTED_PHASE_SECONDS,
  formatClock,
} from "@/lib/admin-progress-view";
import {
  formatStageLine,
  STAGE_LIST,
  type StageKey,
  type StageState,
  type StageStatus,
} from "@/lib/admin-generation-stages";

// Re-export for back-compat (DraftEditorShell previously imported StageState from here).
export type { StageKey, StageState, StageStatus };

interface GenerationLoadingScreenProps {
  phases: AdminPhaseEntry[];
  elapsed: number;
  operationLabel: string;
  subjectLabel?: string | null;
  error?: string | null;
  onReset: () => void;
  onRetry: () => void;
  /** 12 阶段细粒度进度 map，key = stage key，value = StageState */
  stages?: Map<StageKey, StageState>;
  /** 占位"决策时刻"内容：传入时替代脉冲圆 + 进度条 + 数字读数。
   *  保留 context label / eyebrow / headline，让用户感知"还是同一个流程"，
   *  只是需要他做一个决定。卡片视觉由 caller 自决，外层提供统一氛围。 */
  centerSlot?: ReactNode;
}

export function GenerationLoadingScreen({
  phases,
  elapsed,
  operationLabel,
  subjectLabel,
  error,
  onReset,
  onRetry,
  stages,
  centerSlot,
}: GenerationLoadingScreenProps) {
  const snapshot = buildAdminLoadingSnapshot(phases);
  const current = snapshot.current;

  // 进度条长阶段时间插值：记录每个 phase 首次出现时的 elapsed，让条随时间缓爬。
  // 计时器本身只显示 elapsed（已用），不吃 phaseFloor / 进度 %。
  const phaseStartRef = useRef<Record<string, number>>({});
  for (const p of phases) {
    if (phaseStartRef.current[p.phase] === undefined) phaseStartRef.current[p.phase] = elapsed;
  }
  const activePhase = useMemo(
    () => [...phases].reverse().find((p) => p.status === "running")?.phase ?? null,
    [phases],
  );
  const phaseFloors = useMemo(() => {
    if (!activePhase) return undefined;
    const expected = EXPECTED_PHASE_SECONDS[activePhase];
    if (!expected) return undefined;
    const inPhase = Math.max(0, elapsed - (phaseStartRef.current[activePhase] ?? elapsed));
    // 缓到 0.9 封顶，真正的 completed 里程碑才推到 1（floor 与里程碑取 max，不回退）
    return { [activePhase]: Math.min(0.9, inPhase / expected) };
  }, [activePhase, elapsed]);

  const isDone = phases.length > 0 && phases.every((p) => p.status === "done" || p.status === "warning");
  const progressPct = isDone ? 100 : computeWeightedProgress(phases, phaseFloors ? { phaseFloors } : undefined);

  const contextLabel = subjectLabel ? `${operationLabel} · ${subjectLabel}` : operationLabel;

  // backend 没传 message 时 headline = stackLabel，这种情况只显示 headline 避免重复
  // centerSlot 决策时刻：phase 流凝固在等待用户，跳过 eyebrow + headline，把标题层让给 centerSlot
  const decisionMode = !!centerSlot && !error;
  const showEyebrow = !decisionMode && !!current && current.stackLabel !== current.headline;

  // ---------- stages panel derived values ----------
  const stagesCompleted = stages
    ? Array.from(stages.values()).filter((s) => s.status === "completed").length
    : 0;
  const stagesTotal = STAGE_LIST.length;
  const currentRunningStage = stages
    ? STAGE_LIST.find(({ key }) => stages.get(key)?.status === "running") ?? null
    : null;

  return (
    <div
      className="gen-loading-root relative flex min-h-dvh w-full flex-col items-center justify-center overflow-hidden px-6"
      style={{ background: "var(--lv-bg)" }}
    >
      <AmbientAura />

      <div
        className="relative z-10 flex flex-col items-center text-center"
        style={{ marginTop: "-2vh", maxWidth: "36rem" }}
      >
        {/* Context label —— 静态锚点：你在为啥做啥 */}
        <div
          className="lv-t-meta"
          style={{
            color: "var(--lv-ink-4)",
            letterSpacing: "0.06em",
          }}
        >
          {contextLabel}
        </div>

        {/* Eyebrow —— stackLabel，每 phase 切换 */}
        {!error && showEyebrow && (
          <div
            key={`eb-${current?.id}`}
            className="lv-t-meta gen-loading-fade mt-5"
            style={{
              color: "var(--lv-ink-3)",
              letterSpacing: "0.08em",
            }}
          >
            {current!.stackLabel}
          </div>
        )}

        {/* Headline —— phase 具体动作；错误态显示统一标签；决策时刻让给 centerSlot */}
        {!decisionMode && (
          <h2
            key={error ? "err" : current?.id || "headline"}
            className="lv-t-h2 gen-loading-fade"
            style={{
              fontFamily: "var(--lv-font-serif)",
              fontWeight: 500,
              color: error ? "var(--lv-danger)" : "var(--lv-ink)",
              letterSpacing: "-0.01em",
              maxWidth: "32rem",
              marginTop: error ? 20 : showEyebrow ? 12 : 20,
            }}
          >
            {error ? "生成被中断" : current?.headline}
          </h2>
        )}

        {/* 决策时刻 —— centerSlot 优先；否则走常规 pulse + progress */}
        {decisionMode ? (
          <div className="gen-loading-fade mt-8 w-full">{centerSlot}</div>
        ) : (
          <>
            {/* Branch + Grow —— 错误态用 danger dot 替代 */}
            <div className="mt-8">
              {error ? (
                <span
                  className="block"
                  style={{
                    width: 8,
                    height: 8,
                    borderRadius: 9999,
                    background: "var(--lv-danger)",
                    opacity: 0.7,
                  }}
                />
              ) : (
                /* 已有 phase headline + 真进度条 + %/已用计时，不再叠加默认文案 */
                <LoadingPulse variant="block" size={48} label="" />
              )}
            </div>

            {/* 进度条（% 加权）与计时器（已用秒数）分列，互不推导 —— 错误态隐藏 */}
            {!error && (
              <div className="mt-10 flex flex-col items-center gap-4">
                <div
                  className="relative overflow-hidden"
                  style={{
                    width: 240,
                    height: 1,
                    background: "rgba(255,255,255,0.06)",
                    borderRadius: 9999,
                  }}
                >
                  <div
                    style={{
                      position: "absolute",
                      inset: "0 auto 0 0",
                      width: `${progressPct}%`,
                      background: "var(--lv-ink-3)",
                      borderRadius: 9999,
                      transition: "width 1100ms cubic-bezier(0.2, 0.7, 0.2, 1)",
                    }}
                  />
                </div>
                <div
                  className="lv-t-micro tabular-nums"
                  style={{
                    fontFamily: "var(--lv-font-sans)",
                    color: "var(--lv-ink-4)",
                    letterSpacing: "0.02em",
                  }}
                >
                  <span style={{ color: "var(--lv-ink-3)" }}>{progressPct}%</span>
                  <span style={{ margin: "0 14px", color: "var(--lv-ink-5)" }}>·</span>
                  <span style={{ color: "var(--lv-ink-3)" }}>{formatClock(elapsed)}</span>
                </div>
              </div>
            )}
          </>
        )}

        {/* 错误态描述 + 按钮 */}
        {error && (
          <div className="mt-10 flex flex-col items-center gap-7">
            <p
              className="lv-t-meta"
              style={{
                maxWidth: "26rem",
                color: "var(--lv-ink-3)",
                lineHeight: 1.7,
                letterSpacing: "0.02em",
              }}
            >
              {error || "请稍后再试。"}
            </p>
            <div className="flex gap-3">
              <button type="button" onClick={onReset} className="gen-loading-btn gen-loading-btn-ghost">
                返回
              </button>
              <button type="button" onClick={onRetry} className="gen-loading-btn gen-loading-btn-accent">
                重试
              </button>
            </div>
          </div>
        )}

        {/* 12 阶段细粒度进度面板 */}
        {stages && (
          <section
            className="mt-8 w-full text-left"
            style={{
              borderRadius: "var(--lv-r-card)",
              border: "1px solid var(--lv-line-2)",
              background: "rgba(255,255,255,0.03)",
              padding: "var(--lv-s-4)",
            }}
            aria-label="生成阶段进度"
          >
            <header
              style={{
                display: "flex",
                alignItems: "baseline",
                justifyContent: "space-between",
                marginBottom: "var(--lv-s-3)",
              }}
            >
              <h3
                className="lv-t-h3"
                style={{ margin: 0, color: "var(--lv-ink-2)" }}
              >
                生成进度
              </h3>
              <span
                className="lv-t-micro tabular-nums"
                style={{
                  fontFamily: "var(--lv-font-sans)",
                  color: "var(--lv-ink-4)",
                }}
              >
                {stagesCompleted} / {stagesTotal}
              </span>
            </header>

            {/* 整体进度条 */}
            <div
              className="relative overflow-hidden"
              style={{
                height: 2,
                borderRadius: 9999,
                background: "rgba(255,255,255,0.06)",
                marginBottom: "var(--lv-s-4)",
              }}
            >
              <div
                style={{
                  position: "absolute",
                  inset: "0 auto 0 0",
                  width: `${(stagesCompleted / stagesTotal) * 100}%`,
                  background: "var(--lv-accent)",
                  borderRadius: 9999,
                  transition: "width 800ms cubic-bezier(0.2, 0.7, 0.2, 1)",
                }}
              />
            </div>

            {/* 12 阶段列表 */}
            <ul
              style={{
                margin: 0,
                padding: 0,
                listStyle: "none",
                display: "flex",
                flexDirection: "column",
                gap: "var(--lv-s-1)",
              }}
            >
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
                const trailing = line.running ?? line.completed;
                const subtaskCount =
                  status === "running" &&
                  state?.subtaskTotal !== undefined &&
                  state.subtaskTotal > 0
                    ? `${state.subtaskDone ?? 0} / ${state.subtaskTotal}`
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
                    {trailing && (
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
                        · {trailing}
                      </span>
                    )}
                  </li>
                );
              })}
            </ul>

            {/* 当前 in-progress 阶段提示 */}
            {currentRunningStage && (
              <p
                className="lv-t-meta"
                style={{
                  marginTop: "var(--lv-s-3)",
                  marginBottom: 0,
                  color: "var(--lv-ink-3)",
                }}
              >
                当前：{currentRunningStage.label}
              </p>
            )}
          </section>
        )}
      </div>

      <style>{`
        .gen-loading-fade {
          animation: gen-loading-in 700ms cubic-bezier(0.2, 0.7, 0.2, 1) both;
        }
        @keyframes gen-loading-in {
          from { opacity: 0; transform: translateY(6px); filter: blur(4px); }
          to   { opacity: 1; transform: translateY(0); filter: blur(0); }
        }

        .gen-loading-btn {
          height: 42px;
          padding: 0 22px;
          border-radius: 9999px;
          font-family: var(--lv-font-sans);
          font-size: var(--lv-t-body);
          font-weight: 500;
          letter-spacing: 0.04em;
          cursor: pointer;
          transition: all 220ms cubic-bezier(0.2, 0.7, 0.2, 1);
        }
        .gen-loading-btn-ghost {
          background: transparent;
          border: 1px solid rgba(255,255,255,0.12);
          color: var(--lv-ink-2);
        }
        .gen-loading-btn-ghost:hover {
          background: rgba(255,255,255,0.04);
          border-color: rgba(255,255,255,0.22);
          color: var(--lv-ink);
        }
        .gen-loading-btn-accent {
          background: rgba(201, 180, 138, 0.08);
          border: 1px solid rgba(201, 180, 138, 0.4);
          color: var(--lv-accent);
        }
        .gen-loading-btn-accent:hover {
          background: rgba(201, 180, 138, 0.14);
          border-color: rgba(201, 180, 138, 0.6);
        }

        @media (prefers-reduced-motion: reduce) {
          .gen-loading-aura { animation: none; opacity: 0.7; }
          .gen-loading-fade { animation: none; }
        }
      `}</style>
    </div>
  );
}
