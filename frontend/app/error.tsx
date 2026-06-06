"use client";

import Link from "next/link";
import { useEffect } from "react";

/**
 * 全局错误边界 · App Router 顶层
 *
 * 任何 render error 冒泡到这里时显示。
 * 视觉：黑底 + Branch（半透明 + 微倾"折枝"暗示）+ 一句话 + 重试 / 回首页。
 * 文案规则：不写"出现错误"系统术语，用"故事中断了"叙事化口吻（参考 §10.3）。
 */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Sentry 会自动捕获（@sentry/nextjs 的 instrumentation hook 已挂）
    // 这里不重复上报，只 log 到 console 便于本地调试
    if (process.env.NODE_ENV !== "production") {
      // eslint-disable-next-line no-console
      console.error("[InkWild] global error boundary:", error);
    }
  }, [error]);

  return (
    <div
      className="lv-theme"
      style={{
        minHeight: "100dvh",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        background: "var(--lv-bg)",
        padding: "32px 24px",
        textAlign: "center",
      }}
    >
      <div
        style={{
          opacity: 0.35,
          marginBottom: 40,
          transform: "rotate(-8deg)",
        }}
      >
        <svg
          viewBox="0 0 100 120"
          width="88"
          height="106"
          fill="none"
          aria-hidden
        >
          <g stroke="var(--lv-ink)" strokeWidth="6" strokeLinecap="round">
            <path d="M 50 112 Q 50 84, 52 56 Q 54 32, 52 12" />
            <path d="M 51 84 Q 62 80, 76 70" />
            <path d="M 52 58 Q 40 52, 28 46" />
            <path d="M 52 28 Q 62 24, 72 18" />
            <path d="M 76 70 L 81 66" />
          </g>
        </svg>
      </div>

      <h1
        className="lv-t-h1"
        style={{
          fontFamily: "var(--lv-font-serif)",
          fontWeight: 500,
          color: "var(--lv-ink)",
          letterSpacing: "-0.015em",
          marginBottom: 12,
        }}
      >
        故事中断了
      </h1>

      <p
        className="lv-t-body"
        style={{
          color: "var(--lv-ink-3)",
          maxWidth: "32ch",
          lineHeight: 1.65,
          marginBottom: 32,
        }}
      >
        引擎遇到了一个意外。可以重试，或者回到首页选一个新的世界。
      </p>

      <div style={{ display: "flex", gap: 12, flexWrap: "wrap", justifyContent: "center" }}>
        <button
          onClick={reset}
          className="lv-btn lv-btn-primary lv-btn-lg"
          style={{ minWidth: 140 }}
        >
          重试
        </button>
        <Link
          href="/"
          className="lv-btn lv-btn-ghost lv-btn-lg"
          style={{ minWidth: 140 }}
        >
          回首页
        </Link>
      </div>

      {error.digest && (
        <code
          style={{
            marginTop: 28,
            fontFamily: "var(--lv-font-mono)",
            fontSize: 10,
            letterSpacing: "0.04em",
            color: "var(--lv-ink-5)",
            opacity: 0.5,
          }}
        >
          ref · {error.digest}
        </code>
      )}
    </div>
  );
}
