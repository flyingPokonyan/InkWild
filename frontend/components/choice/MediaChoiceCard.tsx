"use client";

/**
 * 媒体卡片选项 —— 用于角色 / 剧本选择。
 *
 * 3:4 aspect-ratio，只展示「图 + 名字」。结构化字段（chips / desc）由 CardDetailStrip
 * 在 carousel 下方常驻展示，跟随 hover（PC）/ scroll-snap 中心卡（移动端）切换。
 *
 * Hover 反馈：描边变亮（ink 灰阶） + 图（或 fallback 大字）放大 1.06。
 * 选中态当前流程不需要可视化（点击即 advance 到下一步）。
 */

import { useState } from "react";
import { motion } from "motion/react";

import { lvStaggerItem } from "@/lib/motion";

interface MediaChoiceCardProps {
  cardId: string;
  coverImage: string | null;
  title: string;
  selected: boolean; // 业务上的选中（目前大多为 false，点击直接进入下一步）
  isFocused?: boolean; // UI 上的高亮聚焦（Cover Flow 的中心）
  onSelect: () => void;
  /** 鼠标移入时触发；用于驱动 CardDetailStrip 和 3D Cover Flow */
  onFocus?: () => void;
  ariaLabel?: string;
}

function firstGlyph(s: string): string {
  return Array.from(s.trim())[0] ?? "·";
}

export function MediaChoiceCard({
  cardId,
  coverImage,
  title,
  selected,
  isFocused = false, // 默认不聚焦
  onSelect,
  onFocus,
  ariaLabel,
}: MediaChoiceCardProps) {
  const [imgError, setImgError] = useState(false);
  const showImage = coverImage && !imgError;

  return (
    <motion.button
      type="button"
      onClick={onSelect}
      onMouseEnter={onFocus}
      data-card-id={cardId}
      aria-pressed={selected}
      aria-label={ariaLabel ?? title}
      variants={lvStaggerItem}
      className={`lv-media-card${selected ? " is-selected" : ""}${isFocused ? " is-focused" : ""}`}
    >
      <div className="lv-media-card-scale-wrapper">
        <div className="lv-media-card-inner">
          {showImage ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={coverImage!}
              alt=""
              onError={() => setImgError(true)}
              className="lv-media-card-img"
            />
          ) : (
            <div aria-hidden className="lv-media-card-fallback">
              {firstGlyph(title)}
            </div>
          )}

          <div aria-hidden className="lv-media-card-scrim" />

          {/* 高级极简边框 */}
          <div aria-hidden className="lv-media-card-border" />

          <div className="lv-media-card-body">
            <h3 className="lv-media-card-title">{title}</h3>
          </div>
        </div>
      </div>

      <style jsx global>{`
        .lv-theme .lv-media-card {
          width: 100%;
          aspect-ratio: 3 / 4;
          background: transparent;
          border: none;
          padding: 0;
          cursor: pointer;
          outline: none;
          position: relative;
          text-align: left;
        }

        /* 将缩放和透明度的景深变化交给独立的 wrapper，避免与 framer-motion variants 冲突 */
        .lv-theme .lv-media-card-scale-wrapper {
          position: absolute;
          inset: 0;
          opacity: 0.4;
          transform: scale(0.88);
          transition: opacity 0.5s cubic-bezier(0.16, 1, 0.3, 1), transform 0.5s cubic-bezier(0.16, 1, 0.3, 1);
        }

        .lv-theme .lv-media-card.is-focused .lv-media-card-scale-wrapper {
          opacity: 1;
          transform: scale(1.0);
        }

        .lv-theme .lv-media-card-inner {
          position: absolute;
          inset: 0;
          border-radius: var(--lv-r-card, 16px);
          overflow: hidden;
          background: var(--lv-bg-2, #18181c);
          box-shadow: 0 10px 20px rgba(0,0,0,0.4);
          transition: transform var(--lv-dur-fast) var(--lv-ease);
        }

        /* 选中态（业务逻辑点击）轻微下沉 */
        .lv-theme .lv-media-card.is-selected .lv-media-card-inner {
          transform: translateY(2px);
        }

        .lv-theme .lv-media-card-img {
          position: absolute;
          inset: 0;
          width: 100%;
          height: 100%;
          object-fit: cover;
          /* 微调对比度，压暗，更有电影质感 */
          filter: brightness(0.95) contrast(1.05);
        }

        .lv-theme .lv-media-card-fallback {
          position: absolute;
          inset: 0;
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: clamp(48px, 8vw, 80px);
          font-family: var(--lv-font-serif);
          color: rgba(255,255,255,0.1);
          background: var(--lv-bg-1);
        }

        /* 极简遮罩，保证文字可读性但不过于突兀 */
        .lv-theme .lv-media-card-scrim {
          position: absolute;
          inset: 0;
          background: linear-gradient(
            to bottom,
            rgba(0,0,0,0) 40%,
            rgba(0,0,0,0.85) 100%
          );
          pointer-events: none;
        }

        /* 隐藏未选中卡片的边框，只给中心卡片强调，去 AI 味 */
        .lv-theme .lv-media-card-border {
          position: absolute;
          inset: 0;
          border-radius: var(--lv-r-card, 16px);
          border: 1px solid rgba(255, 255, 255, 0.0);
          pointer-events: none;
          transition: border-color 0.4s ease, box-shadow 0.4s ease;
        }

        /* 仅在聚焦（中心）时显示高级感微光边框 */
        .lv-theme .lv-media-card.is-focused .lv-media-card-border {
          border-color: rgba(255, 255, 255, 0.15);
          box-shadow: inset 0 1px 0 rgba(255,255,255,0.1);
        }

        .lv-theme .lv-media-card-body {
          position: absolute;
          bottom: 0;
          left: 0;
          right: 0;
          padding: var(--lv-s-4);
        }

        /* 标题强制使用优雅的衬线体，并加入克制的文字阴影 */
        .lv-theme .lv-media-card-title {
          font-family: var(--lv-font-serif);
          font-size: 22px;
          font-weight: 500;
          color: rgba(255,255,255,0.95);
          margin: 0;
          letter-spacing: 0.02em;
          text-shadow: 0 2px 4px rgba(0,0,0,0.6);
          transform: translateY(4px);
          opacity: 0.6;
          transition: opacity 0.4s ease, transform 0.4s ease;
        }

        .lv-theme .lv-media-card.is-focused .lv-media-card-title {
          transform: translateY(0);
          opacity: 1;
        }
      `}</style>
    </motion.button>
  );
}
