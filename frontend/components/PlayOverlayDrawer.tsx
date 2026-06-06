"use client";

import { type ReactNode, useEffect, useState } from "react";
import { AnimatePresence, motion } from "motion/react";

import { MobileSheet } from "@/components/ui/MobileSheet";

const WIDE_BREAKPOINT = 768;

/**
 * Play 页用的 overlay 抽屉外壳。
 * - 宽屏：右侧 440px 浮层面板（Framer 右滑）。
 * - 窄屏：vaul 底部 sheet（抓手 + 下拉关闭 + 弹性物理），玻璃质感对齐 play 浮层。
 * scrim 点击 / Esc 关闭。内容由调用方传入。
 */
export function PlayOverlayDrawer({
  open,
  onClose,
  title,
  children,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
}) {
  const [wide, setWide] = useState(true);

  useEffect(() => {
    const sync = () => setWide(window.innerWidth >= WIDE_BREAKPOINT);
    sync();
    window.addEventListener("resize", sync);
    return () => window.removeEventListener("resize", sync);
  }, []);

  if (!wide) {
    return (
      <MobileSheet open={open} onClose={onClose} title={title} tone="glass">
        {children}
      </MobileSheet>
    );
  }

  return (
    <AnimatePresence>
      {open && (
        <div className="lv-theme" style={{ position: "fixed", inset: 0, zIndex: "var(--lv-z-drawer)" as unknown as number }}>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.18 }}
            onClick={onClose}
            style={{
              position: "absolute",
              inset: 0,
              background: "rgba(6, 6, 10, 0.54)",
              backdropFilter: "blur(26px) brightness(0.5)",
              WebkitBackdropFilter: "blur(26px) brightness(0.5)",
            }}
          />
          <motion.aside
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ type: "spring", stiffness: 320, damping: 34 }}
            className="fixed flex flex-col"
            style={{
              background: "rgba(17, 17, 20, 0.86)",
              backdropFilter: "blur(28px) saturate(140%)",
              WebkitBackdropFilter: "blur(28px) saturate(140%)",
              border: "1px solid var(--lv-line)",
              overflow: "hidden",
              top: 0,
              right: 0,
              height: "100dvh",
              width: 440,
              maxWidth: "90vw",
              borderTopLeftRadius: "var(--lv-r-card)",
              borderBottomLeftRadius: "var(--lv-r-card)",
            }}
          >
            <header
              style={{
                flexShrink: 0,
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                padding: "16px 20px 12px",
              }}
            >
              <span style={{ color: "var(--lv-ink)", fontFamily: "var(--lv-font-serif)", fontSize: "18px", fontWeight: 500 }}>
                {title}
              </span>
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
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round">
                  <path d="M18 6 6 18M6 6l12 12" />
                </svg>
              </button>
            </header>
            <div style={{ flex: 1, overflowY: "auto", padding: "0 20px" }}>{children}</div>
          </motion.aside>
        </div>
      )}
    </AnimatePresence>
  );
}
