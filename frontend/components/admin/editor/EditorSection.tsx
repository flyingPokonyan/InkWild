"use client";

import { type ReactNode } from "react";

interface EditorSectionProps {
  id: string;
  index: number;
  eyebrow: string;
  title: string;
  meta?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
}

/**
 * 编辑器 section 容器（紧凑版）。
 * 序号 + eyebrow + 标题 + meta + 操作按钮压在一行 hairline 上方，
 * 不再渲染单独的描述行——节省纵向空间。
 */
export function EditorSection({
  id,
  index,
  eyebrow,
  title,
  meta,
  action,
  children,
}: EditorSectionProps) {
  return (
    <section
      id={id}
      className="lv-editor-section scroll-mt-24"
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "var(--lv-s-4)",
      }}
    >
      <header
        style={{
          display: "flex",
          alignItems: "center",
          gap: "var(--lv-s-3)",
          paddingBottom: "var(--lv-s-2)",
          borderBottom: "1px solid var(--lv-line)",
          flexWrap: "wrap",
        }}
      >
        <span className="lv-t-caps" style={{ color: "var(--lv-ink-4)", flexShrink: 0 }}>
          {String(index).padStart(2, "0")}
        </span>
        <span className="lv-t-caps" style={{ color: "var(--lv-ink-3)", flexShrink: 0 }}>
          {eyebrow}
        </span>
        <h2 className="lv-t-h3" style={{ margin: 0, color: "var(--lv-ink)" }}>
          {title}
        </h2>
        {meta !== undefined && meta !== null && meta !== "" && (
          <span className="lv-t-meta" style={{ color: "var(--lv-ink-3)" }}>
            · {meta}
          </span>
        )}
        {action && <div style={{ marginLeft: "auto", flexShrink: 0 }}>{action}</div>}
      </header>
      <div style={{ display: "flex", flexDirection: "column", gap: "var(--lv-s-4)" }}>
        {children}
      </div>
      <style jsx>{`
        @media (max-width: 767px) {
          .lv-editor-section {
            scroll-margin-top: 140px;
          }
        }
      `}</style>
    </section>
  );
}
