"use client";

import type { ReactNode } from "react";

import { CreditBalanceChip } from "@/components/CreditBalanceChip";
import { NotificationBell } from "@/components/NotificationBell";
import { useAuthStore } from "@/stores/auth";

type Variant = "default" | "transparent";

interface MobileTopBarProps {
  left?: ReactNode;
  right?: ReactNode;
  brand?: ReactNode | "InkWild" | null;
  variant?: Variant;
}

export function MobileTopBar({ left, right, brand = "InkWild", variant = "default" }: MobileTopBarProps) {
  const isTransparent = variant === "transparent";
  const user = useAuthStore((s) => s.user);
  // 页面没自定义 right 时，登录用户默认显示余额 chip（移动端全局可见）。
  // 页面传了 right（如世界详情的 ⋯）则尊重页面，不塞 chip。
  const resolvedRight =
    right !== undefined ? (
      right
    ) : user ? (
      <div style={{ display: "flex", alignItems: "center", gap: "2px" }}>
        <NotificationBell />
        <CreditBalanceChip />
      </div>
    ) : null;

  return (
    <header
      className="lv-mobile-topbar"
      data-variant={variant}
      style={{
        display: "grid",
        gridTemplateColumns: "42px 1fr 42px",
        alignItems: "center",
        gap: 10,
        padding: isTransparent
          ? "calc(env(safe-area-inset-top, 0px) + 14px) 16px 8px"
          : "calc(env(safe-area-inset-top, 0px) + 14px) 16px 10px",
        position: isTransparent ? "absolute" : "relative",
        top: isTransparent ? 0 : undefined,
        left: isTransparent ? 0 : undefined,
        right: isTransparent ? 0 : undefined,
        zIndex: isTransparent ? 10 : undefined,
        background: "transparent",
      }}
    >
      <div style={{ display: "flex", justifyContent: "flex-start" }}>{left ?? null}</div>
      <div
        style={{
          textAlign: "center",
          fontFamily: "var(--lv-font-serif)",
          fontSize: 24,
          fontWeight: 500,
          lineHeight: 1.1,
          color: "var(--lv-ink)",
          letterSpacing: "0.01em",
        }}
      >
        {brand === "InkWild" ? (
          <>
            <span
              aria-hidden
              style={{
                display: "inline-block",
                width: 6,
                height: 6,
                marginRight: 8,
                borderRadius: 999,
                background: "rgba(245,242,235,0.72)",
                verticalAlign: 4,
              }}
            />
            InkWild
          </>
        ) : (
          brand
        )}
      </div>
      <div style={{ display: "flex", justifyContent: "flex-end" }}>{resolvedRight}</div>

      <style jsx global>{`
        @media (min-width: 769px) {
          .lv-mobile-topbar {
            display: none !important;
          }
        }
      `}</style>
    </header>
  );
}

interface MobileIconButtonProps {
  "aria-label": string;
  onClick?: () => void;
  children: ReactNode;
  variant?: Variant;
  as?: "button" | "div";
}

export function MobileIconButton({
  "aria-label": ariaLabel,
  onClick,
  children,
  variant = "default",
  as = "button",
}: MobileIconButtonProps) {
  const isTransparent = variant === "transparent";
  const baseStyle = {
    width: 42,
    height: 42,
    minWidth: 44,
    minHeight: 44,
    borderRadius: 999,
    border: `1px solid ${isTransparent ? "rgba(255,255,255,0.12)" : "rgba(255,255,255,0.08)"}`,
    background: isTransparent ? "rgba(8,8,10,0.36)" : "rgba(255,255,255,0.035)",
    backdropFilter: isTransparent ? "blur(16px)" : undefined,
    WebkitBackdropFilter: isTransparent ? "blur(16px)" : undefined,
    color: isTransparent ? "var(--lv-ink)" : "var(--lv-ink-2)",
    display: "grid",
    placeItems: "center",
    cursor: onClick ? "pointer" : "default",
    padding: 0,
  } as const;

  if (as === "div") {
    return (
      <div role="button" aria-label={ariaLabel} onClick={onClick} style={baseStyle}>
        {children}
      </div>
    );
  }

  return (
    <button type="button" aria-label={ariaLabel} onClick={onClick} style={baseStyle}>
      {children}
    </button>
  );
}
