"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Compass, Feather, UserRound } from "lucide-react";
import { useTranslations } from "next-intl";

import { buildLoginHref } from "@/lib/auth-redirect";
import { MOBILE_BOTTOM_TABS, getActiveMobileTab, type MobileTabKey } from "@/lib/mobile-nav";
import { useAuthStore } from "@/stores/auth";

type TabItem = {
  href: string;
  label: string;
  Icon?: typeof Compass;
  key: MobileTabKey;
  authRequired?: boolean;
};

const TAB_ICONS: Partial<Record<MobileTabKey, typeof Compass>> = {
  discover: Compass,
  create: Feather,
  me: UserRound,
};

export function BottomTabBar() {
  const pathname = usePathname();
  const user = useAuthStore((s) => s.user);
  const tn = useTranslations("nav");

  // 沉浸态隐藏（play / 世界进入 / admin / 创作工坊编辑器）
  if (pathname.startsWith("/play/")) return null;
  if (pathname.includes("/start")) return null;
  if (pathname.startsWith("/login")) return null;
  if (pathname.startsWith("/reset-password")) return null;
  if (pathname.startsWith("/verify-email")) return null;
  if (pathname.startsWith("/admin")) return null;
  if (
    pathname.startsWith("/workshop/worlds/") ||
    pathname.startsWith("/workshop/scripts/") ||
    pathname.startsWith("/workshop/generate")
  )
    return null;

  const activeKey = getActiveMobileTab(pathname);
  const tabs: TabItem[] = MOBILE_BOTTOM_TABS.map((tab) => ({
    ...tab,
    label:
      tab.key === "discover"
        ? tn("mobileDiscover")
        : tab.key === "create"
          ? tn("mobileCreate")
          : tn(tab.key),
    Icon: TAB_ICONS[tab.key],
  }));

  return (
    <nav
      aria-label="移动端导航"
      className="lv-tab-bar"
      style={{
        position: "fixed",
        left: 0,
        right: 0,
        bottom: 0,
        zIndex: "var(--lv-z-sticky)" as unknown as number,
        borderTop: "1px solid var(--lv-line)",
        background: "rgba(8,8,10,0.92)",
        backdropFilter: "blur(20px)",
        WebkitBackdropFilter: "blur(20px)",
        height: "calc(56px + env(safe-area-inset-bottom))",
        paddingBottom: "env(safe-area-inset-bottom)",
        display: "grid",
        gridTemplateColumns: "repeat(4, 1fr)",
      }}
    >
      {tabs.map((tab) => {
        const active = activeKey === tab.key;
        const { Icon } = tab;
        const href = tab.authRequired && !user ? buildLoginHref(tab.href) : tab.href;
        const content = (
          <span
            style={{
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              gap: 4,
              height: 56,
              minHeight: 44,
              color: active ? "var(--lv-ink)" : "var(--lv-ink-3)",
              transition: "color var(--lv-dur-fast) var(--lv-ease)",
            }}
          >
            <span
              style={{
                display: "flex",
                width: 26,
                height: 24,
                alignItems: "center",
                justifyContent: "center",
                transform: active ? "translateY(-2px) scale(1.06)" : "translateY(0) scale(1)",
                transition: "transform var(--lv-dur-fast) var(--lv-ease)",
              }}
            >
              {tab.key === "home" ? (
                <span className="lv-tab-home-mark" aria-hidden />
              ) : Icon ? (
                <Icon size={21} strokeWidth={active ? 1.9 : 1.5} />
              ) : null}
            </span>
            <span
              style={{
                fontFamily: "var(--lv-font-mono)",
                fontSize: 9,
                letterSpacing: "0.04em",
                color: "inherit",
                lineHeight: 1,
              }}
            >
              {tab.label}
            </span>
          </span>
        );
        return (
          <Link key={`tab-${tab.key}`} href={href} style={{ textDecoration: "none" }}>
            {content}
          </Link>
        );
      })}
      <style jsx global>{`
        .lv-tab-home-mark {
          position: relative;
          display: block;
          width: 20px;
          height: 18px;
        }
        .lv-tab-home-mark::before {
          content: "";
          position: absolute;
          left: 3px;
          top: 7px;
          width: 14px;
          height: 10px;
          border: 1.7px solid currentColor;
          border-top: 0;
          border-radius: 2px 2px 3px 3px;
        }
        .lv-tab-home-mark::after {
          content: "";
          position: absolute;
          left: 4px;
          top: 1px;
          width: 12px;
          height: 12px;
          border-left: 1.7px solid currentColor;
          border-top: 1.7px solid currentColor;
          transform: rotate(45deg);
          border-radius: 2px 0 0 0;
        }
      `}</style>
    </nav>
  );
}
