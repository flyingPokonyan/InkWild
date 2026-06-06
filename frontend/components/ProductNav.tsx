"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { useQuery } from "@tanstack/react-query";
import { ChevronDown, Clock3, Coins, Compass, Home, LogIn, PenLine, Search, UserRound } from "lucide-react";
import { useTranslations } from "next-intl";

import { LangChip } from "@/components/LangChip";
import { NotificationBell } from "@/components/NotificationBell";
import {
  CREDIT_BALANCE_QUERY_KEY,
  balanceTone,
  creditLevel,
  fetchCreditBalance,
  fmtCredits,
} from "@/lib/credits";
import { ossThumb } from "@/lib/oss-image";
import { useAuthStore } from "@/stores/auth";

type NavKey = "home" | "discover" | "history" | "create" | null;

interface ProductNavProps {
  variant?: "transparent" | "solid";
  active?: NavKey;
  search?: { value: string; onChange: (v: string) => void; placeholder?: string };
}

const TAB_DEFS = [
  { key: "home" as const, href: "/", Icon: Home, navKey: "home" as const },
  { key: "discover" as const, href: "/discover", Icon: Compass, navKey: "discover" as const },
  { key: "history" as const, href: "/history", Icon: Clock3, navKey: "history" as const },
  { key: "create" as const, href: "/workshop", Icon: PenLine, navKey: "create" as const },
];

export function ProductNav({ variant = "solid", active = null, search }: ProductNavProps) {
  const tNav = useTranslations("nav");
  const tDiscover = useTranslations("discoverPage");
  const tCredits = useTranslations("credits");
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const router = useRouter();

  const TABS = useMemo(
    () => TAB_DEFS.map((d) => ({ ...d, label: tNav(d.navKey) })),
    [tNav],
  );

  const [scrolled, setScrolled] = useState(variant === "solid");
  const [menuOpen, setMenuOpen] = useState(false);

  // 桌面积分入口收进头像下拉：只显示轻量余额，点击进入完整积分页面。
  const { data: creditBalance } = useQuery({
    queryKey: CREDIT_BALANCE_QUERY_KEY,
    queryFn: fetchCreditBalance,
    staleTime: 30_000,
    enabled: !!user,
  });
  const creditBalanceLevel = creditLevel(creditBalance?.balance);
  const creditPalette = balanceTone(creditBalanceLevel);
  const creditDisplayColor = creditBalanceLevel === "normal" ? "var(--lv-ink-2)" : creditPalette.color;
  const [visible, setVisible] = useState(true);
  const lastScrollRef = useRef(0);
  const tickingRef = useRef(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleScroll = () => {
      if (tickingRef.current) return;
      tickingRef.current = true;
      window.requestAnimationFrame(() => {
        const y = window.scrollY;
        const prev = lastScrollRef.current;
        if (variant === "transparent") {
          setScrolled((s) => {
            const next = y > 40;
            return s === next ? s : next;
          });
        }
        if (y > 80 && y > prev) {
          setVisible((v) => (v ? false : v));
        } else {
          setVisible((v) => (v ? v : true));
        }
        lastScrollRef.current = y;
        tickingRef.current = false;
      });
    };

    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => window.removeEventListener("scroll", handleScroll);
  }, [variant]);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const displayName = user?.nickname || user?.identities.find((i) => i.email)?.email || "玩家";
  const initial = (displayName.trim()[0] || "玩").toUpperCase();

  const handleLogout = async () => {
    setMenuOpen(false);
    await logout();
    router.push("/");
  };

  return (
    <motion.header
      className="pn-root"
      initial={{ y: 0 }}
      animate={{ y: visible ? 0 : -76 }}
      transition={{ type: "spring", stiffness: 260, damping: 26 }}
      style={{
        position: "fixed",
        inset: "0 0 auto",
        zIndex: 100,
        height: 68,
        background: scrolled ? "rgba(10, 10, 12, 0.5)" : "transparent",
        backdropFilter: scrolled ? "blur(28px) saturate(180%)" : "none",
        WebkitBackdropFilter: scrolled ? "blur(28px) saturate(180%)" : "none",
        borderBottom: scrolled ? "1px solid rgba(255, 255, 255, 0.06)" : "1px solid transparent",
        transition: "background var(--lv-dur-fast) var(--lv-ease), border var(--lv-dur-fast) var(--lv-ease)",
      }}
    >
      {/* 顶部柔化 scrim：高度 (110px) 大于 nav 自身 (68px)，渐变平滑收到 0，
          避免 0.75→0 在 nav 底边处斜率突变在亮底 hero 上形成横向 Mach 边线（首页那条"黑线"）。 */}
      <div
        aria-hidden
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          right: 0,
          height: 110,
          pointerEvents: "none",
          zIndex: 0,
          background:
            "linear-gradient(180deg, rgba(10, 10, 12, 0.72) 0%, rgba(10, 10, 12, 0.42) 38%, rgba(10, 10, 12, 0.16) 70%, rgba(10, 10, 12, 0) 100%)",
          opacity: scrolled ? 0 : 1,
          transition: "opacity var(--lv-dur-fast) var(--lv-ease)",
        }}
      />

      <div
        style={{
          position: "relative",
          zIndex: 1,
          maxWidth: "1440px",
          margin: "0 auto",
          height: "100%",
          padding: "0 clamp(20px, 4vw, 52px)",
          display: "flex",
          alignItems: "center",
          gap: "20px",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "28px", flex: "1 1 0", minWidth: 0 }}>
          <Link
            href="/"
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "10px",
              color: "var(--lv-ink)",
              textDecoration: "none",
            }}
          >
            <span
              aria-hidden
              style={{
                display: "grid",
                placeItems: "center",
                width: 30,
                height: 30,
                borderRadius: "var(--lv-r-pill)",
                border: "1.5px solid var(--lv-line-2)",
                background: "rgba(10, 10, 12, 0.6)",
              }}
            >
              <svg viewBox="0 0 100 120" width="14" height="17" fill="none">
                <g stroke="var(--lv-ink)" strokeWidth="7" strokeLinecap="round">
                  <path d="M 50 112 Q 50 84, 52 56 Q 54 32, 52 12"/>
                  <path d="M 51 84 Q 62 80, 76 70"/>
                  <path d="M 52 58 Q 40 52, 28 46"/>
                  <path d="M 52 28 Q 62 24, 72 18"/>
                  <path d="M 76 70 L 81 66"/>
                </g>
              </svg>
            </span>
            <span
              style={{
                fontFamily: "var(--lv-font-serif)",
                fontSize: "24px",
                fontWeight: 600,
                letterSpacing: "0.04em",
                color: "var(--lv-ink)",
                textShadow: "0 2px 10px rgba(0,0,0,0.5)",
              }}
            >
              InkWild
            </span>
          </Link>
        </div>

        <nav
          className="pn-tabs-desktop"
          style={{
            position: "relative",
            display: "flex",
            gap: "4px",
            alignItems: "center",
            padding: "4px",
            border: "1px solid rgba(255, 255, 255, 0.06)",
            borderRadius: "var(--lv-r-pill)",
            background: "rgba(255, 255, 255, 0.02)",
            backdropFilter: "blur(12px)",
            flex: "0 0 auto",
          }}
        >
          {TABS.map((tab) => {
            const isActive = active === tab.key;
            return (
              <Link
                key={tab.key}
                href={tab.href}
                prefetch
                className="pn-tab"
                data-active={isActive ? "true" : "false"}
                style={{
                  position: "relative",
                  padding: "8px 18px",
                  borderRadius: "var(--lv-r-pill)",
                  textDecoration: "none",
                  color: isActive ? "var(--lv-ink)" : "var(--lv-ink-2)",
                  fontSize: "13.5px",
                  fontWeight: 500,
                  transition: "color 220ms cubic-bezier(0.2, 0.8, 0.2, 1)",
                  zIndex: 1,
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "6px",
                }}
              >
                {isActive && (
                  <motion.span
                    aria-hidden
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ duration: 0.12, ease: "easeOut" }}
                    style={{
                      position: "absolute",
                      inset: 0,
                      borderRadius: "var(--lv-r-pill)",
                      background: "rgba(245, 242, 235, 0.08)",
                      border: "1px solid rgba(245, 242, 235, 0.12)",
                      boxShadow: "0 4px 12px rgba(0,0,0,0.25)",
                      zIndex: -1,
                    }}
                  />
                )}
                <tab.Icon size={14} className="pn-tab-icon" style={{ opacity: isActive ? 0.95 : 0.7, transition: "opacity 220ms ease" }} />
                <span>{tab.label}</span>
              </Link>
            );
          })}
        </nav>

        <div style={{ display: "flex", alignItems: "center", gap: "14px", flex: "1 1 0", minWidth: 0, justifyContent: "flex-end" }}>
          {search && (
            <label
              className="pn-search-box pn-desktop-only"
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "8px",
                width: "220px",
                height: "38px",
                padding: "0 14px",
                borderRadius: "var(--lv-r-pill)",
                color: "var(--lv-ink-3)",
                background: "rgba(255, 255, 255, 0.035)",
                border: "1px solid rgba(255, 255, 255, 0.06)",
                backdropFilter: "blur(8px)",
                transition: "border-color 240ms ease, background 240ms ease, box-shadow 240ms ease",
              }}
            >
              <Search size={14} className="pn-search-icon" style={{ opacity: 0.6, transition: "color 200ms ease, opacity 200ms ease" }} />
              <input
                value={search.value}
                onChange={(e) => search.onChange(e.target.value)}
                placeholder={search.placeholder ?? tDiscover("searchPlaceholder")}
                style={{
                  width: "100%",
                  border: 0,
                  outline: 0,
                  background: "transparent",
                  color: "var(--lv-ink)",
                  fontSize: "13px",
                }}
              />
            </label>
          )}

          <NotificationBell />

          <LangChip />

          {user ? (
            <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
              <div style={{ position: "relative" }} ref={menuRef}>
                <button
                  type="button"
                  onClick={() => setMenuOpen((v) => !v)}
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: "4px",
                    padding: "3px 6px 3px 3px",
                    borderRadius: "var(--lv-r-pill)",
                    background: "rgba(255, 255, 255, 0.03)",
                    border: "1px solid rgba(255, 255, 255, 0.05)",
                    cursor: "pointer",
                    color: "var(--lv-ink-2)",
                  }}
                >
                  {user.avatar_url ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={ossThumb(user.avatar_url, 56)}
                      alt=""
                      style={{ width: 28, height: 28, borderRadius: "50%", objectFit: "cover" }}
                    />
                  ) : (
                    <span
                      style={{
                        display: "grid",
                        placeItems: "center",
                        width: 28,
                        height: 28,
                        borderRadius: "50%",
                        background: "rgba(255, 255, 255, 0.12)",
                        color: "var(--lv-ink)",
                        fontWeight: 700,
                        fontSize: "12px",
                      }}
                    >
                      {initial}
                    </span>
                  )}
                  <ChevronDown size={12} style={{ opacity: 0.6 }} />
                </button>

                <AnimatePresence>
                  {menuOpen && (
                    <motion.div
                      initial={{ opacity: 0, y: 8, scale: 0.95 }}
                      animate={{ opacity: 1, y: 0, scale: 1 }}
                      exit={{ opacity: 0, y: 8, scale: 0.95 }}
                      transition={{ duration: 0.15, ease: "easeOut" }}
                      style={{
                        position: "absolute",
                        top: "calc(100% + 8px)",
                        right: 0,
                        width: "210px",
                        padding: "6px",
                        borderRadius: "var(--lv-r-card)",
                        background: "rgba(15, 15, 18, 0.96)",
                        border: "1px solid rgba(255, 255, 255, 0.08)",
                        backdropFilter: "blur(24px)",
                        boxShadow: "0 20px 40px rgba(0,0,0,0.6)",
                      }}
                    >
                      <div
                        style={{
                          padding: "10px 12px 12px",
                          borderBottom: "1px solid rgba(255, 255, 255, 0.06)",
                          marginBottom: "4px",
                        }}
                      >
                        <div
                          style={{
                            color: "var(--lv-ink)",
                            fontWeight: 600,
                            fontSize: "13.5px",
                            overflow: "hidden",
                            textOverflow: "ellipsis",
                            whiteSpace: "nowrap",
                          }}
                        >
                          {displayName}
                        </div>
                      </div>
                      <Link
                        href="/me"
                        className="pn-menu-item"
                        style={{
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "space-between",
                          gap: "10px",
                          width: "100%",
                          padding: "8px 12px",
                          borderRadius: "8px",
                          background: "transparent",
                          color: "var(--lv-ink-2)",
                          fontSize: "13px",
                          textAlign: "left",
                          cursor: "pointer",
                          transition: "color 200ms ease, background 200ms ease",
                          textDecoration: "none",
                        }}
                        onClick={() => setMenuOpen(false)}
                      >
                        <span style={{ display: "inline-flex", alignItems: "center", gap: "8px" }}>
                          <UserRound size={14} />
                          {tNav("account")}
                        </span>
                        <span style={{ color: "var(--lv-ink-4)" }}>›</span>
                      </Link>
                      <Link
                        href="/me/credits"
                        className="pn-menu-item"
                        style={{
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "space-between",
                          gap: "10px",
                          padding: "8px 12px",
                          borderRadius: "8px",
                          color: "var(--lv-ink-2)",
                          fontSize: "13px",
                          textDecoration: "none",
                          textAlign: "left",
                          transition: "color 200ms ease, background 200ms ease",
                        }}
                        onClick={() => setMenuOpen(false)}
                      >
                        <span style={{ display: "inline-flex", alignItems: "center", gap: "8px" }}>
                          <Coins size={14} />
                          {tCredits("title")}
                        </span>
                        <span style={{ color: creditDisplayColor, fontWeight: 500, fontVariantNumeric: "tabular-nums" }}>
                          {creditBalance ? fmtCredits(creditBalance.balance) : "—"}
                        </span>
                      </Link>
                      <button
                        type="button"
                        onClick={() => void handleLogout()}
                        className="pn-menu-item-danger"
                        style={{
                          display: "block",
                          width: "100%",
                          padding: "8px 12px",
                          borderRadius: "8px",
                          background: "transparent",
                          border: 0,
                          color: "var(--lv-danger)",
                          fontSize: "13px",
                          cursor: "pointer",
                          textAlign: "left",
                          transition: "background 200ms ease",
                        }}
                      >
                        {tNav("logout")}
                      </button>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            </div>
          ) : (
            <Link
              href="/login"
              className="pn-login-btn"
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "6px",
                height: "38px",
                padding: "0 18px",
                borderRadius: "var(--lv-r-pill)",
                background: "var(--lv-ink)",
                border: "1px solid var(--lv-ink)",
                color: "#0a0a0c",
                fontWeight: 600,
                fontSize: "13px",
                cursor: "pointer",
                textDecoration: "none",
                transition: "color 220ms ease, background 220ms ease, border-color 220ms ease",
              }}
            >
              <LogIn size={13} />
              <span>登录</span>
            </Link>
          )}
        </div>
      </div>

      <style jsx global>{`
        /* hover 反应统一：切象牙白文字，不切金（符合 GOLD WHITELIST）*/
        .pn-tab[data-active="false"]:hover {
          color: var(--lv-ink) !important;
        }
        .pn-tab[data-active="false"]:hover .pn-tab-icon {
          opacity: 1 !important;
        }
        .pn-login-btn:hover {
          transform: translateY(-1px);
          box-shadow: 0 8px 22px rgba(0, 0, 0, 0.45) !important;
        }
        .pn-menu-item:hover {
          color: var(--lv-ink) !important;
          background: rgba(255, 255, 255, 0.04) !important;
        }
        .pn-menu-item-danger:hover {
          background: rgba(255, 99, 99, 0.06) !important;
        }
        /* 搜索框 focus：中性白增强，配合 a11y 还有全局 :focus-visible outline 兜底 */
        .pn-search-box:focus-within {
          border-color: rgba(255, 255, 255, 0.16) !important;
          background: rgba(255, 255, 255, 0.06) !important;
        }
        .pn-search-box:focus-within .pn-search-icon {
          color: var(--lv-ink) !important;
          opacity: 1 !important;
        }
        /* 移动端：ProductNav 整体隐藏，由 MobileTopBar + BottomTabBar 接管 */
        @media (max-width: 768px) {
          .pn-root {
            display: none !important;
          }
          .pn-tabs-desktop {
            display: none !important;
          }
          .pn-desktop-only {
            display: none !important;
          }
        }
      `}</style>
    </motion.header>
  );
}
