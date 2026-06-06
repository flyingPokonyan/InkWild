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
  selected: boolean;
  onSelect: () => void;
  /** 鼠标移入时触发；用于驱动 CardDetailStrip。 */
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
      className={`lv-media-card${selected ? " is-selected" : ""}`}
    >
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

      <div className="lv-media-card-body">
        <h3 className="lv-t-h3 lv-media-card-title">{title}</h3>
      </div>

      <style jsx global>{`
        .lv-theme .lv-media-card {
          position: relative;
          width: 100%;
          aspect-ratio: 3 / 4;
          display: flex;
          flex-direction: column;
          justify-content: flex-end;
          overflow: hidden;
          cursor: pointer;
          background: var(--lv-bg-1);
          border: 1px solid var(--lv-line);
          border-radius: var(--lv-r-card);
          text-align: left;
          color: var(--lv-ink);
          transition:
            border-color var(--lv-dur-fast) var(--lv-ease),
            transform var(--lv-dur-fast) var(--lv-ease);
        }
        .lv-theme .lv-media-card.is-selected {
          border-color: var(--lv-ink-2);
          box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.18);
          transform: translateY(-2px);
        }
        .lv-theme .lv-media-card-img {
          position: absolute;
          inset: 0;
          width: 100%;
          height: 100%;
          object-fit: cover;
          transition: transform 600ms cubic-bezier(0.16, 1, 0.3, 1);
        }
        .lv-theme .lv-media-card-fallback {
          position: absolute;
          inset: 0;
          background: var(--lv-bg-1);
          display: flex;
          align-items: center;
          justify-content: center;
          color: var(--lv-ink-4);
          font-family: var(--lv-font-serif);
          font-size: clamp(48px, 8vw, 80px);
          font-weight: 400;
          line-height: 1;
          letter-spacing: -0.02em;
          user-select: none;
          transition:
            transform 600ms cubic-bezier(0.16, 1, 0.3, 1),
            color var(--lv-dur-fast) var(--lv-ease);
        }
        .lv-theme .lv-media-card-scrim {
          position: absolute;
          inset: 0;
          background: linear-gradient(
            180deg,
            rgba(10, 10, 12, 0) 35%,
            rgba(10, 10, 12, 0.78) 68%,
            rgba(10, 10, 12, 0.96) 100%
          );
          pointer-events: none;
        }
        .lv-theme .lv-media-card-body {
          position: relative;
          padding: var(--lv-s-4);
        }
        .lv-theme .lv-media-card-title {
          margin: 0;
          color: var(--lv-ink);
        }
        @media (hover: hover) {
          .lv-theme .lv-media-card:hover {
            border-color: rgba(245, 242, 235, 0.32);
          }
          .lv-theme .lv-media-card:hover .lv-media-card-img,
          .lv-theme .lv-media-card:hover .lv-media-card-fallback {
            transform: scale(1.06);
          }
          .lv-theme .lv-media-card:hover .lv-media-card-fallback {
            color: var(--lv-ink-3);
          }
        }
      `}</style>
    </motion.button>
  );
}
