"use client";

import Link from "next/link";
import { Play } from "lucide-react";

interface PosterCardProps {
  href: string;
  title: string;
  genre: string;
  era?: string | null;
  description?: string;
  coverImage?: string | null;
  difficulty: number;
  estimatedTime?: string;
  hasScript?: boolean;
  badge?: string;
}

export function PosterCardDemo({
  href,
  title,
  genre,
  era,
  coverImage,
  difficulty,
  hasScript = true,
  badge,
}: PosterCardProps) {
  const metaParts = [era, difficulty != null ? `难度 ${difficulty}` : null].filter(Boolean);

  return (
    <Link href={href} style={{ display: "block", textDecoration: "none", color: "inherit" }}>
      <div className="lv-clean-card">
        {/* 1. 封面图片区域 (3:2 rounded, with zoom & subtle hover glow) */}
        <div className="lv-clean-card-image-wrapper">
          {coverImage ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={coverImage}
              alt={title}
              className="lv-clean-card-image"
            />
          ) : (
            <div
              className="lv-clean-card-image"
              style={{
                background: "linear-gradient(135deg, rgba(201, 180, 138, 0.15), #111113 50%, rgba(127, 176, 145, 0.08))",
              }}
            />
          )}

          {/* 可选角标 (左上) */}
          {badge && (
            <span className="lv-clean-card-badge">
              {badge}
            </span>
          )}

          {/* 模式角标 (右上) */}
          <span className={`lv-clean-card-mode-badge ${!hasScript ? "is-free" : ""}`}>
            {hasScript ? "◆ 剧本" : "◇ 自由"}
          </span>

          {/* 居中 Play 悬浮播放按钮 */}
          <div className="lv-clean-card-play-overlay">
            <div className="lv-clean-card-play-btn">
              <Play size={20} fill="currentColor" style={{ marginLeft: 2 }} />
            </div>
          </div>
        </div>

        {/* 2. 底部文字内容 (无界、呼吸感、高对比度) */}
        <div className="lv-clean-card-info">
          {/* A. 题材分类 */}
          <div className="lv-clean-card-genre">{genre}</div>

          {/* B. 标题 - 经典衬线体 */}
          <h3 className="lv-clean-card-title">{title}</h3>

          {/* C. 时代与难度 */}
          <div className="lv-clean-card-meta">
            {metaParts.join(" · ")}
          </div>
        </div>
      </div>
    </Link>
  );
}
