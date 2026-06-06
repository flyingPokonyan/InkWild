"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { Coins, LogOut, UserRound } from "lucide-react";
import { useTranslations } from "next-intl";

import { CREDIT_BALANCE_QUERY_KEY, balanceTone, creditLevel, fetchCreditBalance, fmtCredits } from "@/lib/credits";
import { useAuthStore } from "@/stores/auth";

type Section = "account" | "credits";

/**
 * PC 账户中心壳：左栏（头像 + 名字 + 邮箱 + 导航 + 退出）+ 右内容。
 * 桌面专用，移动端各页另渲染自己的视图。账户 / 我的积分 两页共用这一层。
 */
export function AccountShell({ active, children }: { active: Section; children: ReactNode }) {
  const t = useTranslations("account");
  const tNav = useTranslations("nav");
  const router = useRouter();
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const [loggingOut, setLoggingOut] = useState(false);

  const { data: balance } = useQuery({
    queryKey: CREDIT_BALANCE_QUERY_KEY,
    queryFn: fetchCreditBalance,
    staleTime: 30_000,
    enabled: !!user,
  });
  const level = creditLevel(balance?.balance);
  const palette = balanceTone(level);
  const balanceColor = level === "normal" ? "var(--lv-ink-2)" : palette.color;

  const displayName = user?.nickname || user?.identities.find((i) => i.email)?.email || tNav("me");
  const email = user?.identities.find((i) => i.email)?.email ?? null;
  const initial = (displayName.trim()[0] || "我").toUpperCase();

  const handleLogout = async () => {
    setLoggingOut(true);
    await logout();
    router.push("/");
  };

  const nav: { key: Section; href: string; label: string; icon: ReactNode }[] = [
    { key: "account", href: "/me", label: t("navAccount"), icon: <UserRound size={16} /> },
    { key: "credits", href: "/me/credits", label: t("navCredits"), icon: <Coins size={16} /> },
  ];

  return (
    <div className="acct-shell acct-desktop">
      <aside className="acct-rail">
        <div className="acct-id">
          <div className="acct-avatar" aria-hidden>
            {user?.avatar_url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={user.avatar_url} alt="" />
            ) : (
              <span>{initial}</span>
            )}
          </div>
          <div className="acct-id-text">
            <div className="acct-name">{displayName}</div>
            {email && <div className="acct-email">{email}</div>}
          </div>
        </div>

        <nav className="acct-nav">
          {nav.map((item) => (
            <Link
              key={item.key}
              href={item.href}
              className={`acct-nav-item${active === item.key ? " is-active" : ""}`}
            >
              <span className="acct-nav-rule" aria-hidden />
              {item.icon}
              <span>{item.label}</span>
              {item.key === "credits" && (
                <span className="acct-nav-bal" style={{ color: balanceColor }}>
                  {balance ? fmtCredits(balance.balance) : ""}
                </span>
              )}
            </Link>
          ))}
        </nav>

        <button type="button" className="acct-logout" onClick={() => void handleLogout()} disabled={loggingOut}>
          <LogOut size={14} />
          {loggingOut ? tNav("loggingOut") : tNav("logout")}
        </button>
      </aside>

      <section className="acct-content">{children}</section>

      <style jsx global>{`
        @media (max-width: 768px) {
          .acct-desktop {
            display: none !important;
          }
        }
        .acct-shell {
          position: relative;
          z-index: 2;
          max-width: 1040px;
          margin: 0 auto;
          padding: 132px clamp(24px, 5vw, 52px) 80px;
          display: grid;
          grid-template-columns: 244px 1fr;
          gap: clamp(32px, 5vw, 64px);
          align-items: start;
        }
        .acct-rail {
          position: sticky;
          top: 116px;
          display: flex;
          flex-direction: column;
          gap: 22px;
        }
        .acct-id {
          display: flex;
          align-items: center;
          gap: 13px;
        }
        .acct-avatar {
          width: 50px;
          height: 50px;
          border-radius: 50%;
          flex-shrink: 0;
          display: grid;
          place-items: center;
          overflow: hidden;
          background: rgba(245, 242, 235, 0.08);
          border: 1px solid var(--lv-line-2);
          box-shadow: 0 8px 20px rgba(0, 0, 0, 0.35);
        }
        .acct-avatar img {
          width: 100%;
          height: 100%;
          object-fit: cover;
        }
        .acct-avatar span {
          font-family: var(--lv-font-serif);
          font-size: 21px;
          font-weight: 500;
          color: var(--lv-ink);
        }
        .acct-id-text {
          min-width: 0;
        }
        .acct-name {
          font-family: var(--lv-font-serif);
          font-size: 18px;
          font-weight: 500;
          color: var(--lv-ink);
          line-height: 1.2;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .acct-email {
          margin-top: 3px;
          font-size: 12px;
          color: var(--lv-ink-3);
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .acct-nav {
          display: flex;
          flex-direction: column;
          gap: 2px;
        }
        .acct-nav-item {
          position: relative;
          display: flex;
          align-items: center;
          gap: 10px;
          height: 42px;
          padding: 0 14px;
          border-radius: var(--lv-r-card);
          color: var(--lv-ink-3);
          text-decoration: none;
          font-size: var(--lv-t-compact);
          transition: color 200ms ease, background 200ms ease;
        }
        .acct-nav-rule {
          position: absolute;
          left: 0;
          top: 50%;
          transform: translateY(-50%);
          width: 2px;
          height: 0;
          border-radius: 2px;
          background: var(--lv-accent);
          transition: height 220ms cubic-bezier(0.16, 1, 0.3, 1);
        }
        .acct-nav-item:hover {
          color: var(--lv-ink);
          background: rgba(255, 255, 255, 0.03);
        }
        .acct-nav-item.is-active {
          color: var(--lv-ink);
          background: rgba(223, 194, 144, 0.07);
        }
        .acct-nav-item.is-active .acct-nav-rule {
          height: 18px;
        }
        .acct-nav-bal {
          margin-left: auto;
          font-size: var(--lv-t-meta);
          font-weight: 600;
          font-variant-numeric: tabular-nums;
        }
        .acct-logout {
          display: inline-flex;
          align-items: center;
          gap: 8px;
          align-self: flex-start;
          margin-top: 6px;
          padding: 9px 14px;
          border-radius: var(--lv-r-card);
          border: 1px solid transparent;
          background: transparent;
          color: var(--lv-ink-3);
          font-size: var(--lv-t-compact);
          cursor: pointer;
          transition: color 200ms ease, background 200ms ease, border-color 200ms ease;
        }
        .acct-logout:hover {
          color: var(--lv-danger);
          background: rgba(239, 130, 118, 0.05);
          border-color: rgba(239, 130, 118, 0.18);
        }
        .acct-content {
          min-width: 0;
        }
      `}</style>
    </div>
  );
}
