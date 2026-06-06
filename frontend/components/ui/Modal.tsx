"use client";

import { ReactNode, useEffect } from "react";
import { createPortal } from "react-dom";

interface ModalProps {
  open: boolean;
  onClose: () => void;
  /** 标题，serif t-h2 */
  title?: ReactNode;
  /** modal 主体 */
  children: ReactNode;
  /** 底部操作区（按钮组） */
  footer?: ReactNode;
  /** 内容最大宽，默认 480 */
  maxWidth?: number | string;
  /** 阻止点击背景 + Esc 关闭（仅在不可关闭流程用，如必须确认的破坏性操作） */
  dismissable?: boolean;
}

/**
 * 中央 modal（§5 z-modal=200）。
 * 默认背景点击 + Esc 关闭，dismissable=false 时禁用以强制行动。
 * Body scroll lock 自动应用。
 */
export function Modal({
  open,
  onClose,
  title,
  children,
  footer,
  maxWidth = 480,
  dismissable = true,
}: ModalProps) {
  useEffect(() => {
    if (!open) return;
    document.body.style.overflow = "hidden";

    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && dismissable) onClose();
    };
    window.addEventListener("keydown", handleKey);

    return () => {
      document.body.style.overflow = "";
      window.removeEventListener("keydown", handleKey);
    };
  }, [open, dismissable, onClose]);

  if (!open || typeof document === "undefined") return null;

  return createPortal(
    <div
      role="dialog"
      aria-modal="true"
      style={{
        position: "fixed",
        inset: 0,
        zIndex: "var(--lv-z-modal)" as unknown as number,
        display: "grid",
        placeItems: "center",
        padding: "var(--lv-s-4)",
        background: "rgba(0, 0, 0, 0.6)",
        backdropFilter: "blur(8px)",
        animation: `fade-in var(--lv-dur-fast) var(--lv-ease)`,
      }}
      onClick={() => dismissable && onClose()}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: "100%",
          maxWidth,
          background: "var(--lv-bg-1)",
          border: "1px solid var(--lv-line)",
          borderRadius: "var(--lv-r-card)",
          padding: "var(--lv-s-6)",
          display: "flex",
          flexDirection: "column",
          gap: "var(--lv-s-4)",
        }}
      >
        {title && (
          <h2 className="lv-t-h2" style={{ margin: 0 }}>
            {title}
          </h2>
        )}
        <div className="lv-t-body-long">{children}</div>
        {footer && (
          <div style={{ display: "flex", justifyContent: "flex-end", gap: "var(--lv-s-2)" }}>
            {footer}
          </div>
        )}
      </div>
    </div>,
    document.body,
  );
}
