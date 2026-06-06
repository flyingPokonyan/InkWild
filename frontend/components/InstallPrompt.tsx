"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { AnimatePresence, motion } from "motion/react";
import { Share, X } from "lucide-react";

const DISMISS_KEY = "inkwild_install_dismissed_v1";

type BeforeInstallPromptEvent = Event & {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
};

/**
 * PWA「添加到主屏」引导。
 * - Android / Chrome：接住 beforeinstallprompt，点「添加」直接触发系统安装。
 * - iOS Safari：不触发该事件，改给一句「分享 → 添加到主屏幕」的手动提示。
 * 一次性、可关闭、记 localStorage，不打扰。沉浸/认证页不出现。
 */
export function InstallPrompt() {
  const pathname = usePathname();
  const [deferred, setDeferred] = useState<BeforeInstallPromptEvent | null>(null);
  const [iosHint, setIosHint] = useState(false);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const standalone =
      window.matchMedia("(display-mode: standalone)").matches ||
      (window.navigator as Navigator & { standalone?: boolean }).standalone === true;
    if (standalone) return;
    try {
      if (window.localStorage.getItem(DISMISS_KEY)) return;
    } catch {
      /* localStorage 不可用时照常引导 */
    }

    const onBeforeInstall = (e: Event) => {
      e.preventDefault();
      setDeferred(e as BeforeInstallPromptEvent);
      window.setTimeout(() => setVisible(true), 2500);
    };
    window.addEventListener("beforeinstallprompt", onBeforeInstall);

    const ua = window.navigator.userAgent;
    const isIOS = /iphone|ipad|ipod/i.test(ua);
    const isSafari = /safari/i.test(ua) && !/crios|fxios|edgios/i.test(ua);
    if (isIOS && isSafari) {
      setIosHint(true);
      window.setTimeout(() => setVisible(true), 3000);
    }

    return () => window.removeEventListener("beforeinstallprompt", onBeforeInstall);
  }, []);

  const dismiss = () => {
    setVisible(false);
    try {
      window.localStorage.setItem(DISMISS_KEY, "1");
    } catch {
      /* 忽略 */
    }
  };

  const install = async () => {
    if (!deferred) return;
    await deferred.prompt();
    await deferred.userChoice.catch(() => undefined);
    dismiss();
  };

  // 沉浸 / 认证页不出现
  const hidden =
    pathname.startsWith("/play/") ||
    pathname.includes("/start") ||
    pathname.startsWith("/login") ||
    pathname.startsWith("/reset-password") ||
    pathname.startsWith("/verify-email") ||
    pathname.startsWith("/admin");

  const show = visible && !hidden && (deferred || iosHint);

  return (
    <AnimatePresence>
      {show && (
        <motion.div
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 24 }}
          transition={{ type: "spring", stiffness: 320, damping: 32 }}
          role="dialog"
          aria-label="添加到主屏"
          style={{
            position: "fixed",
            left: 12,
            right: 12,
            bottom: "calc(68px + env(safe-area-inset-bottom))",
            zIndex: "var(--lv-z-toast)" as unknown as number,
            display: "flex",
            alignItems: "center",
            gap: 12,
            padding: "12px 14px",
            borderRadius: 16,
            border: "1px solid var(--lv-line-2)",
            background: "rgba(20, 20, 24, 0.92)",
            backdropFilter: "blur(20px) saturate(140%)",
            WebkitBackdropFilter: "blur(20px) saturate(140%)",
            boxShadow: "0 20px 48px rgba(0, 0, 0, 0.5)",
          }}
        >
          <span
            aria-hidden
            style={{
              flexShrink: 0,
              width: 38,
              height: 38,
              borderRadius: 10,
              display: "grid",
              placeItems: "center",
              background: "rgba(223, 194, 144, 0.12)",
              border: "1px solid rgba(223, 194, 144, 0.28)",
              color: "var(--lv-accent)",
              fontFamily: "var(--lv-font-serif)",
              fontSize: 20,
              fontWeight: 500,
            }}
          >
            ᛁ
          </span>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ color: "var(--lv-ink)", fontSize: 14, fontWeight: 600, lineHeight: 1.3 }}>
              把 InkWild 添加到主屏
            </div>
            <div style={{ color: "var(--lv-ink-3)", fontSize: 12, lineHeight: 1.4, marginTop: 2 }}>
              {iosHint ? (
                <>
                  点底部{" "}
                  <Share size={11} style={{ display: "inline", verticalAlign: -1, color: "var(--lv-ink-2)" }} />{" "}
                  分享 →「添加到主屏幕」，像 app 一样打开
                </>
              ) : (
                "全屏沉浸，像 app 一样随手就玩"
              )}
            </div>
          </div>
          {deferred && (
            <button
              type="button"
              onClick={install}
              data-pressable
              style={{
                flexShrink: 0,
                height: 34,
                padding: "0 16px",
                borderRadius: 999,
                border: 0,
                background: "var(--lv-accent)",
                color: "var(--lv-bg)",
                fontSize: 13,
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              添加
            </button>
          )}
          <button
            type="button"
            onClick={dismiss}
            aria-label="关闭"
            style={{
              flexShrink: 0,
              width: 30,
              height: 30,
              display: "grid",
              placeItems: "center",
              borderRadius: 999,
              border: 0,
              background: "transparent",
              color: "var(--lv-ink-3)",
              cursor: "pointer",
            }}
          >
            <X size={16} />
          </button>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
