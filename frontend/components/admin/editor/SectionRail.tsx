"use client";

import { type ReactNode } from "react";

export interface RailSection {
  id: string;
  label: string;
  count?: number;
}

interface SectionRailProps {
  sections: RailSection[];
  activeId: string;
  /** 顶端 sticky 偏移，对应 strip 高度 */
  stickyTop?: number;
}

/**
 * 桌面端：左侧固定索引栏。每个 section 一行：序号 (mono caps) + 标题 (h3) + 数量 (meta)。
 * Active 用 2px 暖金竖线指示。
 *
 * 组件本身只负责桌面端展示。移动端由 SectionRailMobile 接管。
 */
export function SectionRail({ sections, activeId, stickyTop = 72 }: SectionRailProps) {
  const click = (id: string) => {
    const el = document.getElementById(id);
    if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <nav
      aria-label="Sections"
      style={{
        position: "sticky",
        top: stickyTop,
        display: "flex",
        flexDirection: "column",
        gap: "var(--lv-s-1)",
        paddingTop: "var(--lv-s-6)",
      }}
    >
      {sections.map((section, idx) => {
        const active = section.id === activeId;
        return (
          <button
            key={section.id}
            type="button"
            onClick={() => click(section.id)}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "var(--lv-s-3)",
              padding: "var(--lv-s-2) var(--lv-s-3)",
              border: 0,
              background: "transparent",
              cursor: "pointer",
              textAlign: "left",
              minHeight: 44,
              position: "relative",
              transition: "background var(--lv-dur-fast) var(--lv-ease)",
            }}
          >
            <span
              aria-hidden
              style={{
                position: "absolute",
                left: 0,
                top: "50%",
                transform: "translateY(-50%)",
                width: 2,
                height: active ? 16 : 0,
                background: "var(--lv-accent)",
                transition: "height var(--lv-dur-fast) var(--lv-ease)",
              }}
            />
            <span
              className="lv-t-caps"
              style={{
                color: active ? "var(--lv-ink-2)" : "var(--lv-ink-4)",
                width: 22,
                flexShrink: 0,
              }}
            >
              {String(idx + 1).padStart(2, "0")}
            </span>
            <span
              className="lv-t-body"
              style={{
                color: active ? "var(--lv-ink)" : "var(--lv-ink-3)",
                flex: 1,
                minWidth: 0,
                whiteSpace: "nowrap",
                overflow: "hidden",
                textOverflow: "ellipsis",
                fontWeight: active ? 500 : 400,
              }}
            >
              {section.label}
            </span>
            {section.count !== undefined && (
              <span
                className="lv-t-meta"
                style={{ color: "var(--lv-ink-4)", flexShrink: 0 }}
              >
                {section.count}
              </span>
            )}
          </button>
        );
      })}
    </nav>
  );
}

interface SectionRailMobileProps {
  sections: RailSection[];
  activeId: string;
  /** 顶端 sticky 偏移（draft strip 高度） */
  stickyTop?: number;
  /** 右侧附加节点（如 preview 唤起按钮） */
  trailing?: ReactNode;
}

/**
 * 移动端：横向 sticky pill 条，贴在 strip 下方。
 * 触摸目标 ≥ 44px，pill 形选中态走 ink。
 */
export function SectionRailMobile({
  sections,
  activeId,
  stickyTop = 56,
  trailing,
}: SectionRailMobileProps) {
  const click = (id: string) => {
    const el = document.getElementById(id);
    if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <div
      className="lv-editor-mobile-rail"
      style={{
        position: "sticky",
        top: stickyTop,
        zIndex: "var(--lv-z-sticky)" as unknown as number,
        background: "rgba(8,8,10,0.96)",
        borderBottom: "1px solid var(--lv-line)",
      }}
    >
      <div
        className="lv-editor-mobile-rail-scroll"
        style={{
          display: "flex",
          alignItems: "center",
          gap: "var(--lv-s-2)",
          padding: "var(--lv-s-2) var(--lv-pad-x)",
        }}
      >
        <div
          className="lv-editor-mobile-rail-tabs"
          style={{
            display: "flex",
            alignItems: "center",
            gap: "var(--lv-s-2)",
            flex: 1,
            minWidth: 0,
            overflowX: "auto",
            scrollbarWidth: "none",
            WebkitOverflowScrolling: "touch",
          }}
        >
          {sections.map((section) => {
            const active = section.id === activeId;
            return (
              <button
                key={section.id}
                type="button"
                onClick={() => click(section.id)}
                className="lv-t-meta"
                style={{
                  minHeight: 44,
                  padding: "0 var(--lv-s-3)",
                  whiteSpace: "nowrap",
                  borderRadius: "var(--lv-r-pill)",
                  border: "1px solid",
                  borderColor: active ? "rgba(245,242,235,0.14)" : "transparent",
                  background: active ? "rgba(255,255,255,0.08)" : "transparent",
                  color: active ? "var(--lv-ink)" : "var(--lv-ink-3)",
                  cursor: "pointer",
                  fontWeight: active ? 500 : 400,
                  transition:
                    "background var(--lv-dur-fast) var(--lv-ease), border-color var(--lv-dur-fast) var(--lv-ease), color var(--lv-dur-fast) var(--lv-ease)",
                }}
              >
                {section.label}
                {section.count !== undefined && (
                  <span style={{ marginLeft: 6, color: "var(--lv-ink-4)" }}>
                    {section.count}
                  </span>
                )}
              </button>
            );
          })}
        </div>
        {trailing && <div style={{ flexShrink: 0 }}>{trailing}</div>}
      </div>
      <style jsx>{`
        .lv-editor-mobile-rail {
          -webkit-backdrop-filter: saturate(120%);
          backdrop-filter: saturate(120%);
        }

        .lv-editor-mobile-rail-tabs::-webkit-scrollbar {
          display: none;
        }
      `}</style>
    </div>
  );
}
