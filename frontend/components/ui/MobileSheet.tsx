"use client";

import { type CSSProperties, type ReactNode } from "react";
import { Drawer } from "vaul";

interface MobileSheetProps {
  open: boolean;
  onClose: () => void;
  /** 标题，serif 18px；不传则渲染一个可访问的隐藏标题 */
  title?: ReactNode;
  children: ReactNode;
  /** solid = 实底（积分 / 通知）；glass = 半透模糊（play 浮层）；deep = 高级纯黑 */
  tone?: "solid" | "glass" | "deep";
  /** 内容区最大高度，默认 72dvh —— 控制「别太大」 */
  maxHeight?: string;
}

/**
 * 移动端底部 sheet（基于 vaul 原生能力，物理回弹极佳）。
 * 移除了过去为了绕过 Safari touch-action 冲突而加入的 hack，
 * 直接信任 vaul 内部对 Pointer Events 的原生处理，恢复了流畅的滑动体验。
 */
export function MobileSheet({ open, onClose, title, children, tone = "solid", maxHeight = "72dvh" }: MobileSheetProps) {
  const contentStyle: CSSProperties = {
    position: "fixed",
    left: 0,
    right: 0,
    bottom: 0,
    zIndex: "var(--lv-z-drawer)" as unknown as number,
    display: "flex",
    flexDirection: "column",
    maxHeight,
    // 材质调整：增加高级感
    background: tone === "glass" ? "rgba(17, 17, 20, 0.76)" : tone === "deep" ? "var(--lv-bg)" : "var(--lv-bg-1)",
    backdropFilter: tone === "glass" ? "blur(32px) saturate(180%)" : undefined,
    WebkitBackdropFilter: tone === "glass" ? "blur(32px) saturate(180%)" : undefined,
    borderTop: "1px solid rgba(255, 255, 255, 0.12)",
    boxShadow: "0 -8px 40px rgba(0, 0, 0, 0.4)",
    borderTopLeftRadius: 28,
    borderTopRightRadius: 28,
    paddingBottom: "env(safe-area-inset-bottom)",
    outline: "none",
    willChange: "transform",
  };

  return (
    <Drawer.Root open={open} onOpenChange={(next) => { if (!next) onClose(); }} shouldScaleBackground={false}>
      <Drawer.Portal>
        <Drawer.Overlay
          style={{
            position: "fixed",
            inset: 0,
            zIndex: "var(--lv-z-drawer)" as unknown as number,
            background: "rgba(0, 0, 0, 0.75)",
            backdropFilter: "blur(12px)",
            WebkitBackdropFilter: "blur(12px)",
          }}
        />
        <Drawer.Content className="lv-sheet" style={contentStyle} aria-describedby={undefined}>
          {/* 抓手 —— 高级感设计的悬浮短横线 */}
          <div aria-hidden style={{ flexShrink: 0, display: "flex", justifyContent: "center", padding: "12px 0 4px", touchAction: "none" }}>
            <span style={{
              width: 36,
              height: 5,
              borderRadius: 999,
              background: "rgba(255, 255, 255, 0.35)",
              boxShadow: "0 1px 2px rgba(0,0,0,0.15)"
            }} />
          </div>
          <header
            style={{
              flexShrink: 0,
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              padding: "12px 24px 16px",
              touchAction: "none",
            }}
          >
            <Drawer.Title
              style={{
                margin: 0,
                color: "var(--lv-ink)",
                fontFamily: "var(--lv-font-serif)",
                fontSize: 20,
                fontWeight: 500,
                letterSpacing: "0.02em",
                ...(title ? null : { position: "absolute", width: 1, height: 1, overflow: "hidden", clip: "rect(0 0 0 0)" }),
              }}
            >
              {title ?? "面板"}
            </Drawer.Title>
            <button
              type="button"
              onClick={onClose}
              aria-label="关闭"
              style={{
                width: 32,
                height: 32,
                display: "grid",
                placeItems: "center",
                borderRadius: "var(--lv-r-pill)",
                border: "none",
                background: "rgba(255, 255, 255, 0.08)",
                color: "var(--lv-ink-2)",
                cursor: "pointer",
                transition: "background var(--lv-dur-fast) var(--lv-ease), color var(--lv-dur-fast) var(--lv-ease)",
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = "rgba(255, 255, 255, 0.15)";
                e.currentTarget.style.color = "var(--lv-ink)";
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = "rgba(255, 255, 255, 0.08)";
                e.currentTarget.style.color = "var(--lv-ink-2)";
              }}
            >
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" aria-hidden>
                <path d="M18 6 6 18M6 6l12 12" />
              </svg>
            </button>
          </header>
          <div style={{ flex: 1, overflowY: "auto", padding: "0 24px 12px", overscrollBehavior: "contain" }}>{children}</div>
        </Drawer.Content>
      </Drawer.Portal>
    </Drawer.Root>
  );
}
