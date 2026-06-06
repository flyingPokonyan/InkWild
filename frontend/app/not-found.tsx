import Link from "next/link";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "走丢了",
};

/**
 * 404 · 走丢了
 *
 * 视觉：黑底 + Branch mark（静态，opacity 0.4 暗示"枯枝"）+ 一行话 + 回首页 CTA。
 * 不写"页面不存在"这种系统术语，用"故事走丢了"叙事化文案。
 */
export default function NotFound() {
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
      <div style={{ opacity: 0.4, marginBottom: 40 }}>
        <svg
          viewBox="0 0 100 120"
          width="96"
          height="115"
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
        故事走丢了
      </h1>

      <p
        className="lv-t-body"
        style={{
          color: "var(--lv-ink-3)",
          maxWidth: "32ch",
          lineHeight: 1.65,
          marginBottom: 40,
        }}
      >
        这条小径没有通往任何世界。
      </p>

      <Link
        href="/"
        className="lv-btn lv-btn-primary lv-btn-lg"
        style={{ minWidth: 160 }}
      >
        回首页
      </Link>
    </div>
  );
}
