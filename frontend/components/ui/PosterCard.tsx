"use client";

import Link from "next/link";

interface PosterCardProps {
  href: string;
  /** 世界名 — serif t-h3，weight 400，1 行 clamp */
  title: string;
  /** 题材 — meta 行第 1 项 */
  genre: string;
  /** 时代 — meta 行第 2 项 */
  era?: string | null;
  /** @deprecated 描述 hook 已从卡片移除（2026-05-09 简化），保留 prop 兼容旧调用方。详细描述去详情页看。 */
  description?: string;
  /** 3:2 封面图 URL（服务端从 21:9 hero 中心裁切），无图时用径向渐变占位 */
  coverImage?: string | null;
  /** 难度 1-5 — meta 行第 3 项 */
  difficulty: number;
  /** @deprecated 时长从卡片移除，详情页展示 */
  estimatedTime?: string;
  /** @deprecated 模式角标已从卡片移除（2026-05-09），prop 保留兼容旧调用方。模式信息在详情页展示。 */
  hasScript?: boolean;
  /** NEW / HOT 类徽章（封面左上），可选 */
  badge?: string;
}

/**
 * 世界封面卡片（§7.1 简化版 2026-05-09，3:2 升级 2026-05-12）。
 * 三层结构：[3:2 封面 + 可选 NEW/HOT 徽章] / [serif h3 标题 weight 400] / [题材 · 时代 · 难度 X meta]
 * 描述 hook + 时长 + 模式角标从卡片移除（详情页展示），减少视觉臃肿。
 */
export function PosterCard({
  href,
  title,
  genre,
  era,
  coverImage,
  difficulty,
  badge,
}: PosterCardProps) {
  // meta 3 项一致结构
  const metaParts = [genre, era, difficulty != null ? `难度 ${difficulty}` : null].filter(Boolean);

  return (
    <Link
      href={href}
      style={{
        display: "flex",
        flexDirection: "column",
        textDecoration: "none",
      }}
    >
      {/* 3:2 封面 */}
      <div
        style={{
          position: "relative",
          aspectRatio: "3 / 2",
          borderRadius: "var(--lv-r-card)",
          overflow: "hidden",
          background: coverImage
            ? `url(${coverImage}) center/cover no-repeat`
            : "radial-gradient(ellipse at 50% 50%, var(--lv-bg-2), var(--lv-bg) 75%)",
          marginBottom: "var(--lv-s-3)",
        }}
      >
        {/* 可选 NEW/HOT 徽章（左上）— ink 灰阶不要 accent */}
        {badge && (
          <span
            className="lv-t-caps"
            style={{
              position: "absolute",
              top: "var(--lv-s-2)",
              left: "var(--lv-s-2)",
              padding: "var(--lv-s-1) var(--lv-s-2)",
              borderRadius: "var(--lv-r-pill)",
              background: "rgba(0, 0, 0, 0.5)",
              backdropFilter: "blur(8px)",
              color: "var(--lv-ink)",
            }}
          >
            {badge}
          </span>
        )}
      </div>

      {/* 标题 — serif h3 weight 400，editorial restraint */}
      <h3
        className="lv-t-h3"
        style={{
          margin: 0,
          marginBottom: "var(--lv-s-1)",
          fontFamily: "var(--lv-font-serif)",
          fontWeight: 400,
          color: "var(--lv-ink)",
          letterSpacing: "-0.005em",
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
        }}
      >
        {title}
      </h3>

      {/* meta — 时代 · 时长（无 era 时退到 题材 · 时长），始终 1-2 项 */}
      <div className="lv-t-meta" style={{ color: "var(--lv-ink-3)" }}>{metaParts.join(" · ")}</div>
    </Link>
  );
}
