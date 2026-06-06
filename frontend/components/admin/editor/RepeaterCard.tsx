"use client";

import { type ReactNode, useState } from "react";
import { useTranslations } from "next-intl";

interface RepeaterCardProps {
  /** 折叠态显示的标题（角色名 / 事件名等） */
  title: ReactNode;
  /** 折叠态副标题（如 personality 截断） */
  subtitle?: ReactNode;
  /** 标题旁的小标签（如 "可扮演"、trigger_type） */
  badges?: ReactNode;
  /** 折叠态额外的右侧 meta（如 priority、count） */
  trailingMeta?: ReactNode;
  /** 头像 / 序号 */
  leading?: ReactNode;
  /** 展开后渲染的内容 */
  children: ReactNode;
  /** 移除回调（展开态最下方） */
  onRemove: () => void;
  /** 移除按钮文案（"移除事件" 等） */
  removeLabel: string;
  /** 默认是否展开 */
  defaultExpanded?: boolean;
}

/**
 * 折叠卡（角色 / 事件 / 结局通用）。
 * 折叠态：1px hairline + bg-1，hover 升 bg-2
 * 展开态：左缘 4px 暖金竖线 + bg-1，作为唯一强调
 */
export function RepeaterCard({
  title,
  subtitle,
  badges,
  trailingMeta,
  leading,
  children,
  onRemove,
  removeLabel,
  defaultExpanded = false,
}: RepeaterCardProps) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const t = useTranslations("admin.editor.section");

  return (
    <article
      style={{
        position: "relative",
        background: "var(--lv-bg-1)",
        border: "1px solid var(--lv-line)",
        borderRadius: "var(--lv-r-card)",
        overflow: "hidden",
        transition: "border-color var(--lv-dur-fast) var(--lv-ease)",
      }}
    >
      {expanded && (
        <span
          aria-hidden
          style={{
            position: "absolute",
            top: 0,
            bottom: 0,
            left: 0,
            width: 3,
            background: "var(--lv-accent)",
          }}
        />
      )}

      {/* Header: leading (avatar) and badges may host their own interactive
          children, so the outer wrapper can't be a <button>. The title region
          is the toggle; badges/chevron sit as siblings so they can carry their
          own click handlers. */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "var(--lv-s-4)",
          padding: "var(--lv-s-4)",
          minHeight: 64,
        }}
      >
        {leading && <div style={{ flexShrink: 0 }}>{leading}</div>}
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          aria-expanded={expanded}
          style={{
            flex: 1,
            minWidth: 0,
            display: "flex",
            flexDirection: "column",
            gap: 4,
            background: "transparent",
            border: 0,
            padding: 0,
            cursor: "pointer",
            textAlign: "left",
            color: "inherit",
          }}
        >
          <span className="lv-t-h3" style={{ color: "var(--lv-ink)" }}>
            {title}
          </span>
          {!expanded && subtitle && (
            <span
              className="lv-t-meta"
              style={{ color: "var(--lv-ink-3)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}
            >
              {subtitle}
            </span>
          )}
        </button>
        {badges && (
          <div style={{ flexShrink: 0, display: "inline-flex", alignItems: "center", gap: "var(--lv-s-2)" }}>
            {badges}
          </div>
        )}
        {!expanded && trailingMeta && (
          <span className="lv-t-meta" style={{ color: "var(--lv-ink-3)", flexShrink: 0 }}>
            {trailingMeta}
          </span>
        )}
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          aria-expanded={expanded}
          className="lv-t-caps"
          style={{
            flexShrink: 0,
            color: "var(--lv-ink-3)",
            minHeight: 32,
            display: "inline-flex",
            alignItems: "center",
            padding: "0 var(--lv-s-3)",
            background: "transparent",
            border: 0,
            cursor: "pointer",
          }}
        >
          {expanded ? t("collapse") : t("expand")}
        </button>
      </div>

      {expanded && (
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: "var(--lv-s-6)",
            padding: "var(--lv-s-6)",
            paddingTop: 0,
            borderTop: "1px solid var(--lv-line)",
          }}
        >
          {children}
          <div
            style={{
              display: "flex",
              justifyContent: "flex-end",
              paddingTop: "var(--lv-s-4)",
              borderTop: "1px solid var(--lv-line)",
            }}
          >
            <button
              type="button"
              onClick={onRemove}
              className="lv-btn lv-btn-sm"
              style={{ color: "var(--lv-danger)", borderColor: "rgba(184,92,92,0.3)" }}
            >
              {removeLabel}
            </button>
          </div>
        </div>
      )}
    </article>
  );
}
