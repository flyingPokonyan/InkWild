"use client";

/**
 * 通用选择交互场景容器。
 *
 * 两种模式：
 * - standalone（默认）：整页全屏，5 层背景（封面虚化 + 暗化遮罩 + AmbientAura + 内容透明层）+ 顶栏 + 内容头 + children + 倒计时。
 * - embedded（embedded=true）：跳过外壳渲染，仅渲染内容头 + children + 倒计时。
 *   用于嵌入 GenerationLoadingScreen 的 centerSlot（IPRecognitionCard）。
 *
 * 视觉严格按 v2.2 §2.2：选中色走 ink 灰阶，accent 仅允许在 ◆/◇ 模式徽章。
 * 动效按 §6：入场 lvStaggerContainer/Item 500+70ms、step pip 切换 200ms、prefers-reduced-motion 自动降级。
 */

import type { ReactNode } from "react";

import { AmbientAura } from "./AmbientAura";

interface ChoiceSceneProps {
  // 内容头
  eyebrow?: string;
  title?: string;
  description?: string;

  // 顶栏（embedded 模式忽略）
  onBack?: () => void;
  backLabel?: string;
  steps?: { current: number; total: number };

  // 倒计时（仅显示，状态由 caller 维护）
  countdown?: {
    text: string; // 已格式化好的文案（"8s 后默认「高复刻原作」" / "暂停自动选择"）
  };

  // 内容
  children: ReactNode;

  // 背景（仅 standalone）
  coverImage?: string | null;
  background?: "cinematic" | "plain";

  // 模式开关
  embedded?: boolean;

  // hover/focus 暂停倒计时
  onCountdownPauseChange?: (paused: boolean) => void;
}

export function ChoiceScene({
  eyebrow,
  title,
  description,
  onBack,
  backLabel = "← 返回",
  steps,
  countdown,
  children,
  coverImage,
  background = "cinematic",
  embedded,
  onCountdownPauseChange,
}: ChoiceSceneProps) {
  const hasHeader = Boolean(eyebrow || title || description);
  const showCinematicBackground = background === "cinematic";
  const headerBlock = !hasHeader ? null : (
    <div style={{ textAlign: "center", display: "flex", flexDirection: "column", gap: "var(--lv-s-3)" }}>
      {eyebrow && (
        <div
          className="lv-t-caps"
          style={{
            color: "var(--lv-ink-3)",
            letterSpacing: "0.04em",
          }}
        >
          {eyebrow}
        </div>
      )}
      {title && (
        <h2
          className="lv-t-h2"
          style={{
            margin: 0,
            fontFamily: "var(--lv-font-serif)",
            fontWeight: 500,
            letterSpacing: "-0.01em",
            color: "var(--lv-ink)",
          }}
        >
          {title}
        </h2>
      )}
      {description && (
        <p
          className="lv-t-meta"
          style={{ color: "var(--lv-ink-3)", margin: 0, lineHeight: 1.6 }}
        >
          {description}
        </p>
      )}
    </div>
  );

  const contentBlock = (
    <div
      style={{ display: "flex", flexDirection: "column", gap: "var(--lv-s-8)", width: "100%" }}
      onMouseEnter={() => onCountdownPauseChange?.(true)}
      onMouseLeave={() => onCountdownPauseChange?.(false)}
      onFocus={() => onCountdownPauseChange?.(true)}
      onBlur={() => onCountdownPauseChange?.(false)}
    >
      {headerBlock}
      {children}
      {countdown && (
        <div
          className="lv-t-micro"
          style={{
            fontFamily: "var(--lv-font-mono)",
            color: "var(--lv-ink-4)",
            letterSpacing: "0.04em",
            textAlign: "center",
          }}
          aria-live="polite"
        >
          {countdown.text}
        </div>
      )}
    </div>
  );

  if (embedded) {
    return <div style={{ width: "100%" }}>{contentBlock}</div>;
  }

  return (
    <div
      className="lv-theme lv-h-dvh lv-content-mobile-pad"
      style={{
        position: "relative",
        background: "var(--lv-bg)",
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
      }}
    >
      {showCinematicBackground && coverImage && (
        <div aria-hidden style={{ position: "absolute", inset: 0, zIndex: 0, pointerEvents: "none", overflow: "hidden" }}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={coverImage}
            alt=""
            style={{
              width: "100%",
              height: "100%",
              objectFit: "cover",
              opacity: 0.3,
              filter: "blur(40px) saturate(140%)",
              transform: "scale(1.1)",
            }}
          />
          <div
            style={{
              position: "absolute",
              inset: 0,
              background:
                "linear-gradient(180deg, rgba(10,10,12,0.4) 0%, rgba(10,10,12,0.7) 50%, rgba(10,10,12,0.95) 100%)",
            }}
          />
        </div>
      )}

      {showCinematicBackground && <AmbientAura />}

      {/* 顶栏 */}
      {(onBack || steps) && (
        <div
          style={{
            position: "relative",
            zIndex: 1,
            flexShrink: 0,
            maxWidth: "var(--lv-max-w)",
            width: "100%",
            margin: "0 auto",
            padding: "var(--lv-s-4) var(--lv-pad-x)",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: "var(--lv-s-4)",
          }}
        >
          {onBack ? (
            <button
              type="button"
              onClick={onBack}
              className="lv-btn lv-btn-sm"
              style={{ minHeight: 44 }}
            >
              {backLabel}
            </button>
          ) : (
            <span />
          )}
          {steps && (
            <div style={{ display: "flex", gap: "var(--lv-s-1)" }}>
              {Array.from({ length: steps.total }).map((_, i) => (
                <span
                  key={i}
                  style={{
                    width: i === steps.current ? 24 : 8,
                    height: 2,
                    borderRadius: "var(--lv-r-pill)",
                    background: i <= steps.current ? "var(--lv-ink-2)" : "var(--lv-line-2)",
                    transition: "all var(--lv-dur-fast) var(--lv-ease)",
                  }}
                />
              ))}
            </div>
          )}
        </div>
      )}

      {/* 中央内容 */}
      <div
        style={{
          position: "relative",
          zIndex: 1,
          flex: 1,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          width: "100%",
          padding: "var(--lv-s-4) var(--lv-pad-x) var(--lv-s-12)",
          overflowY: "auto",
          minHeight: 0,
        }}
      >
        <div style={{ width: "100%", maxWidth: "var(--lv-max-w)", margin: "0 auto" }}>
          {contentBlock}
        </div>
      </div>
    </div>
  );
}
