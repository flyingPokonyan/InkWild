"use client";

/**
 * 媒体卡 carousel 下方的详情条。
 *
 * PC：跟随 hover；移动端：跟随 scroll-snap 中心卡（IntersectionObserver 在父组件里）。
 * 结构：label-value 元数据行（mono caps + sans 值）+ 一行简介。
 *
 * 不让 strip 高度跳动 → min-height 锁定 96px，单卡信息少时空着也比抖动好。
 */

import { AnimatePresence, motion } from "motion/react";

export interface DetailEntry {
  label: string;
  value: string;
}

interface CardDetailStripProps {
  cardKey: string;
  entries: DetailEntry[];
  description?: string;
  /** trim 字符上限，超过的部分截断带 …；CSS 还有 line-clamp 3 兜底视觉行数。默认 200。 */
  descriptionMaxChars?: number;
}

function trim(s: string | undefined, max: number): string {
  if (!s) return "";
  const arr = Array.from(s.trim());
  if (arr.length <= max) return arr.join("");
  return arr.slice(0, max).join("") + "…";
}

export function CardDetailStrip({
  cardKey,
  entries,
  description,
  descriptionMaxChars = 200,
}: CardDetailStripProps) {
  const desc = trim(description, descriptionMaxChars);

  return (
    <div className="lv-detail-strip">
      <AnimatePresence mode="wait">
        <motion.div
          key={cardKey}
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -4 }}
          transition={{ duration: 0.18, ease: [0.2, 0.7, 0.2, 1] }}
          className="lv-detail-strip-inner"
        >
          {entries.length > 0 && (
            <div className="lv-detail-strip-meta">
              {entries.map((entry, i) => (
                <span key={entry.label} className="lv-detail-strip-meta-item">
                  <span className="lv-detail-strip-meta-label">{entry.label}</span>
                  <span className="lv-detail-strip-meta-value">{entry.value}</span>
                  {i < entries.length - 1 && (
                    <span aria-hidden className="lv-detail-strip-meta-sep">·</span>
                  )}
                </span>
              ))}
            </div>
          )}
          {desc && <p className="lv-detail-strip-desc">{desc}</p>}
        </motion.div>
      </AnimatePresence>

      <style jsx global>{`
        .lv-theme .lv-detail-strip {
          width: 100%;
          max-width: 600px; /* 收窄宽度以保持阅读舒适度 */
          margin: 0 auto;
          padding: 8px 16px 0;
          min-height: 120px;
          position: relative;
        }
        .lv-theme .lv-detail-strip-inner {
          display: flex;
          flex-direction: column;
          gap: 12px;
          align-items: center;
          text-align: center;
        }
        .lv-theme .lv-detail-strip-meta {
          display: flex;
          flex-wrap: wrap;
          justify-content: center;
          row-gap: 6px;
          column-gap: 12px;
          align-items: center;
        }
        .lv-theme .lv-detail-strip-meta-item {
          display: inline-flex;
          align-items: center;
          gap: 6px;
        }
        .lv-theme .lv-detail-strip-meta-label {
          display: none; /* 隐藏 Label 让界面更极简（只看值即可） */
        }
        .lv-theme .lv-detail-strip-meta-value {
          font-family: var(--lv-font-mono);
          font-size: 11px;
          color: var(--lv-ink-3);
          letter-spacing: 0.1em;
          text-transform: uppercase;
        }
        .lv-theme .lv-detail-strip-meta-sep {
          margin-left: 6px;
          color: var(--lv-ink-4);
          font-size: 11px;
        }
        .lv-theme .lv-detail-strip-desc {
          margin: 0 auto;
          font-family: var(--lv-font-sans);
          font-size: 14px;
          line-height: 1.8;
          color: var(--lv-ink-2);
          max-width: 60ch;
          display: -webkit-box;
          -webkit-line-clamp: 3;
          -webkit-box-orient: vertical;
          overflow: hidden;
        }
        @media (max-width: 768px) {
          .lv-theme .lv-detail-strip {
            padding: 4px 16px 0;
            min-height: 104px;
          }
          .lv-theme .lv-detail-strip-inner {
            gap: 8px;
          }
          .lv-theme .lv-detail-strip-meta {
            column-gap: 8px;
          }
          .lv-theme .lv-detail-strip-meta-value {
            font-size: 10px;
          }
          .lv-theme .lv-detail-strip-desc {
            font-size: 13px;
            line-height: 1.6;
          }
        }
      `}</style>
    </div>
  );
}
