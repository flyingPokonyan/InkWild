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
 * 移动端底部 sheet（vaul）。原生 app 手感：抓手、下拉关闭、弹性物理、滚动到顶才接管拖拽。
 * 桌面侧滑面板仍由各自的 Drawer / PlayOverlayDrawer 处理，这个只管窄屏底部形态。
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
    background: tone === "glass" ? "rgba(17, 17, 20, 0.92)" : tone === "deep" ? "var(--lv-bg)" : "var(--lv-bg-1)",
    backdropFilter: tone === "glass" ? "blur(28px) saturate(140%)" : undefined,
    WebkitBackdropFilter: tone === "glass" ? "blur(28px) saturate(140%)" : undefined,
    borderTop: "1px solid var(--lv-line)",
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
    paddingBottom: "env(safe-area-inset-bottom)",
    outline: "none",
  };

  return (
    <Drawer.Root open={open} onOpenChange={(next) => { if (!next) onClose(); }} shouldScaleBackground={false}>
      <Drawer.Portal>
        <Drawer.Overlay
          style={{
            position: "fixed",
            inset: 0,
            zIndex: "var(--lv-z-drawer)" as unknown as number,
            background: "rgba(6, 6, 10, 0.55)",
            backdropFilter: "blur(6px)",
            WebkitBackdropFilter: "blur(6px)",
          }}
        />
        <Drawer.Content className="lv-sheet" style={contentStyle} aria-describedby={undefined}>
          {/* 抓手 —— 拖拽热区是整张 sheet（滚动到顶时接管），这里只作视觉提示 */}
          <div aria-hidden style={{ flexShrink: 0, display: "flex", justifyContent: "center", padding: "10px 0 2px" }}>
            <span style={{ width: 38, height: 4, borderRadius: 999, background: "rgba(255, 255, 255, 0.22)" }} />
          </div>
          <header
            style={{
              flexShrink: 0,
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              padding: "8px 20px 12px",
            }}
          >
            <Drawer.Title
              style={{
                margin: 0,
                color: "var(--lv-ink)",
                fontFamily: "var(--lv-font-serif)",
                fontSize: 18,
                fontWeight: 500,
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
                border: "1px solid var(--lv-line)",
                background: "transparent",
                color: "var(--lv-ink-2)",
                cursor: "pointer",
              }}
            >
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" aria-hidden>
                <path d="M18 6 6 18M6 6l12 12" />
              </svg>
            </button>
          </header>
          <div style={{ flex: 1, overflowY: "auto", padding: "0 20px 4px", overscrollBehavior: "contain" }}>{children}</div>
        </Drawer.Content>
      </Drawer.Portal>
    </Drawer.Root>
  );
}
