"use client";

/**
 * 紧凑列表选项 —— 用于 mode 选择 / IP 决策 / 未来无图二选一场景。
 *
 * grid: 38px 编号 + 1fr 标题描述 + 24px 箭头。
 * 选中态严格走 ink 灰阶（v2.2 §2.2）：bg rgba 0.06 + border ink-2 + 编号箭头 ink-2 + translateY(-1px)。
 * accent 仅允许出现在 badge（剧本 ◆ / 自由 ◇ 模式编码徽章）。
 */

import { motion } from "motion/react";

import { lvStaggerItem } from "@/lib/motion";

interface ListChoiceOptionProps {
  index: number;
  title: string;
  description: string;
  badge?: { glyph: string; tone: "accent" | "accent-2" };
  recommended?: boolean;
  recommendedLabel?: string;
  selected: boolean;
  disabled?: boolean;
  disabledNote?: string;
  onSelect: () => void;
  onHoverChange?: (hovered: boolean) => void;
}

export function ListChoiceOption({
  index,
  title,
  description,
  badge,
  recommended,
  recommendedLabel = "推荐",
  selected,
  disabled,
  disabledNote,
  onSelect,
  onHoverChange,
}: ListChoiceOptionProps) {
  const numberLabel = String(index).padStart(2, "0");

  const tone = badge?.tone === "accent-2" ? "var(--lv-accent-2)" : "var(--lv-accent)";
  const toneBg = badge?.tone === "accent-2" ? "rgba(127,176,145,0.10)" : "rgba(201,180,138,0.10)";

  return (
    <motion.button
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      disabled={disabled}
      variants={lvStaggerItem}
      onHoverStart={() => onHoverChange?.(true)}
      onHoverEnd={() => onHoverChange?.(false)}
      onFocus={() => onHoverChange?.(true)}
      onBlur={() => onHoverChange?.(false)}
      whileHover={!disabled ? { y: -1 } : undefined}
      style={{
        display: "grid",
        gridTemplateColumns: "38px 1fr 24px",
        alignItems: "center",
        gap: "var(--lv-s-4)",
        width: "100%",
        minHeight: 64,
        padding: "var(--lv-s-4) var(--lv-s-6)",
        textAlign: "left",
        cursor: disabled ? "not-allowed" : "pointer",
        background: selected ? "rgba(255,255,255,0.06)" : "rgba(255,255,255,0.012)",
        border: `1px solid ${selected ? "var(--lv-ink-2)" : "var(--lv-line)"}`,
        borderRadius: "var(--lv-r-card)",
        color: selected ? "var(--lv-ink)" : "var(--lv-ink-2)",
        opacity: disabled ? 0.5 : 1,
        transition:
          "background var(--lv-dur-fast) var(--lv-ease), border-color var(--lv-dur-fast) var(--lv-ease), transform var(--lv-dur-fast) var(--lv-ease)",
        transform: selected ? "translateY(-1px)" : undefined,
      }}
    >
      <span
        aria-hidden
        className="lv-t-micro"
        style={{
          fontFamily: "var(--lv-font-mono)",
          letterSpacing: "0.04em",
          color: selected ? "var(--lv-ink-2)" : "var(--lv-ink-4)",
          textAlign: "center",
          transition: "color var(--lv-dur-fast) var(--lv-ease)",
        }}
      >
        {numberLabel}
      </span>

      <span style={{ display: "flex", flexDirection: "column", gap: "var(--lv-s-1)", minWidth: 0 }}>
        <span
          className="lv-t-body"
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "var(--lv-s-2)",
            color: "inherit",
            fontWeight: 500,
          }}
        >
          {title}
          {badge && (
            <span
              aria-hidden
              style={{
                fontFamily: "var(--lv-font-sans)",
                fontSize: 10,
                lineHeight: 1,
                letterSpacing: "0.05em",
                padding: "2px 7px",
                borderRadius: "var(--lv-r-pill)",
                background: toneBg,
                color: tone,
              }}
            >
              {badge.glyph}
            </span>
          )}
          {recommended && (
            <span
              className="lv-t-micro"
              style={{
                fontFamily: "var(--lv-font-mono)",
                padding: "2px 7px",
                borderRadius: "var(--lv-r-pill)",
                background: "rgba(201,180,138,0.13)",
                color: "var(--lv-accent)",
                fontWeight: 500,
              }}
            >
              {recommendedLabel}
            </span>
          )}
          {disabled && disabledNote && (
            <span className="lv-t-meta" style={{ color: "var(--lv-ink-4)" }}>
              {disabledNote}
            </span>
          )}
        </span>
        <span
          className="lv-t-meta"
          style={{ color: "var(--lv-ink-3)", lineHeight: 1.55 }}
        >
          {description}
        </span>
      </span>

      <span
        aria-hidden
        style={{
          fontFamily: "var(--lv-font-sans)",
          fontSize: 16,
          color: selected ? "var(--lv-ink-2)" : "var(--lv-ink-4)",
          opacity: selected ? 1 : 0.5,
          textAlign: "center",
          transition: "color var(--lv-dur-fast) var(--lv-ease), opacity var(--lv-dur-fast) var(--lv-ease)",
        }}
      >
        →
      </span>
    </motion.button>
  );
}
