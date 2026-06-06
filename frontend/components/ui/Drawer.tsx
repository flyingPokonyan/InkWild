"use client";

import { ReactNode, useEffect, useState } from "react";
import { createPortal } from "react-dom";

import { MobileSheet } from "./MobileSheet";

interface DrawerProps {
  open: boolean;
  onClose: () => void;
  /** 标题，serif t-h2 */
  title?: ReactNode;
  children: ReactNode;
  /** 抽屉宽度（桌面右滑入），默认 480 */
  width?: number | string;
  /** 移动端用底部抽屉（max-width 768px 时生效） */
  mobileBottom?: boolean;
}

const MOBILE_BREAKPOINT = 768;

/**
 * 抽屉（§5 z-drawer=100）。
 * - 桌面：右侧滑入面板（CSS transform，Esc + backdrop 关闭）。
 * - 移动端（mobileBottom）：vaul 底部 sheet —— 抓手 + 下拉关闭 + 弹性物理。
 */
export function Drawer({ open, onClose, title, children, width = 480, mobileBottom = true }: DrawerProps) {
  const [mounted, setMounted] = useState(false);
  const [isMobile, setIsMobile] = useState(false);

  // eslint-disable-next-line react-hooks/set-state-in-effect -- mount 后才能读 window / 起 portal
  useEffect(() => setMounted(true), []);

  useEffect(() => {
    const sync = () => setIsMobile(window.innerWidth <= MOBILE_BREAKPOINT);
    sync();
    window.addEventListener("resize", sync);
    return () => window.removeEventListener("resize", sync);
  }, []);

  if (!mounted) return null;
  if (mobileBottom && isMobile) {
    return (
      <MobileSheet open={open} onClose={onClose} title={title}>
        {children}
      </MobileSheet>
    );
  }
  return (
    <DesktopSidePanel open={open} onClose={onClose} title={title} width={width}>
      {children}
    </DesktopSidePanel>
  );
}

/** 桌面右侧滑入面板（沿用原实现，移动端走 MobileSheet 不到这里）。 */
function DesktopSidePanel({
  open,
  onClose,
  title,
  children,
  width = 480,
}: Omit<DrawerProps, "mobileBottom">) {
  const [render, setRender] = useState(false);

  useEffect(() => {
    if (open) {
      setRender(true);
      document.body.style.overflow = "hidden";
      const handleKey = (e: KeyboardEvent) => {
        if (e.key === "Escape") onClose();
      };
      window.addEventListener("keydown", handleKey);
      return () => {
        document.body.style.overflow = "";
        window.removeEventListener("keydown", handleKey);
      };
    } else {
      const t = setTimeout(() => setRender(false), 200);
      return () => clearTimeout(t);
    }
  }, [open, onClose]);

  if (!open && !render) return null;

  return createPortal(
    <div
      style={{
        position: "fixed",
        inset: 0,
        zIndex: "var(--lv-z-drawer)" as unknown as number,
        display: "flex",
        justifyContent: "flex-end",
        pointerEvents: open ? "auto" : "none",
      }}
    >
      {/* backdrop */}
      <div
        onClick={onClose}
        style={{
          position: "absolute",
          inset: 0,
          background: "rgba(0, 0, 0, 0.5)",
          backdropFilter: "blur(4px)",
          opacity: open ? 1 : 0,
          transition: "opacity var(--lv-dur-fast) var(--lv-ease)",
        }}
      />

      {/* panel */}
      <aside
        role="dialog"
        aria-modal="true"
        className="lv-drawer-panel"
        style={
          {
            position: "relative",
            display: "flex",
            flexDirection: "column",
            width: typeof width === "number" ? `min(${width}px, 100vw)` : width,
            background: "var(--lv-bg-1)",
            borderLeft: "1px solid var(--lv-line)",
            transform: open ? "translateX(0)" : "translateX(100%)",
            transition: "transform var(--lv-dur-fast) var(--lv-ease)",
          } as React.CSSProperties
        }
      >
        {title && (
          <header
            style={{
              padding: "var(--lv-s-4) var(--lv-s-4)",
              borderBottom: "1px solid var(--lv-line)",
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
            }}
          >
            <h2 className="lv-t-h2" style={{ margin: 0 }}>
              {title}
            </h2>
            <button
              type="button"
              onClick={onClose}
              aria-label="关闭"
              style={{
                width: 32,
                height: 32,
                display: "grid",
                placeItems: "center",
                color: "var(--lv-ink-3)",
                background: "transparent",
                border: 0,
                borderRadius: "var(--lv-r-pill)",
                cursor: "pointer",
                transition: "color var(--lv-dur-fast) var(--lv-ease), background var(--lv-dur-fast) var(--lv-ease)",
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.color = "var(--lv-ink)";
                e.currentTarget.style.background = "rgba(255, 255, 255, 0.06)";
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.color = "var(--lv-ink-3)";
                e.currentTarget.style.background = "transparent";
              }}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
                <path d="M6 18L18 6M6 6l12 12" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>
          </header>
        )}
        <div style={{ flex: 1, overflowY: "auto", padding: "var(--lv-s-4)" }}>{children}</div>
      </aside>
    </div>,
    document.body,
  );
}
