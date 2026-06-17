"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { motion } from "motion/react";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Camera, Check, ChevronRight, KeyRound, Loader2, LogOut, MessageSquare, PenLine, X } from "lucide-react";
import { useTranslations } from "next-intl";

import { AccountShell } from "@/components/account/AccountShell";
import { AccountProfile } from "@/components/account/AccountProfile";
import { ChangePasswordForm } from "@/components/account/ChangePasswordForm";
import { FeedbackDialog } from "@/components/feedback/FeedbackDialog";
import { NotificationBell } from "@/components/NotificationBell";
import { ProductNav } from "@/components/ProductNav";
import { Modal } from "@/components/ui/Modal";
import { apiFetch, isUnauthorizedError } from "@/lib/api";
import { updateProfile, uploadAvatar } from "@/lib/auth-api";
import { readAsDataUrl, validateImageFile } from "@/lib/avatar";
import { useGameHistory } from "@/lib/api/history";
import { buildLoginHref } from "@/lib/auth-redirect";
import {
  CREDIT_BALANCE_QUERY_KEY,
  balanceTone,
  creditLevel,
  fetchCreditBalance,
  fmtCredits,
} from "@/lib/credits";
import { parseBackendIso } from "@/lib/datetime";
import { lvStaggerContainer, lvStaggerItem } from "@/lib/motion";
import type { GameHistoryItem, GameSessionDetail } from "@/lib/types";
import { ossThumb } from "@/lib/oss-image";
import { useAuthStore } from "@/stores/auth";
import { useGameStore } from "@/stores/game";

type HistoryT = (key: string, values?: Record<string, string | number>) => string;

function badgeColor(game: GameHistoryItem): string {
  if (game.status !== "ended") return "var(--lv-accent)";
  switch (game.ending_type) {
    case "perfect":
      return "var(--lv-accent)";
    case "good":
      return "var(--lv-ink)";
    case "bad":
      return "#ef8276";
    default:
      return "var(--lv-ink-3)";
  }
}

function badgeLabel(game: GameHistoryItem, th: HistoryT): string {
  if (game.status !== "ended") {
    return game.status === "paused" ? th("statusPaused") : th("statusPlaying");
  }
  switch (game.ending_type) {
    case "perfect":
    case "good":
    case "bad":
    case "timeout":
    case "test_exit":
    case "abandoned":
      return th(`endingName.${game.ending_type}`);
    default:
      return th("endingFallback");
  }
}

function relTime(iso: string, th: HistoryT): string {
  const ts = parseBackendIso(iso).getTime();
  const m = Math.round((Date.now() - ts) / 60000);
  if (m < 1) return th("timeJustNow");
  if (m < 60) return th("timeMinutesAgo", { n: m });
  const h = Math.round(m / 60);
  if (h < 24) return th("timeHoursAgo", { n: h });
  const d = Math.round(h / 24);
  if (d < 7) return th("timeDaysAgo", { n: d });
  const date = parseBackendIso(iso);
  return `${date.getMonth() + 1}.${date.getDate()}`;
}

export default function MePage() {
  const t = useTranslations("mePage");
  const th = useTranslations("historyPage");
  const tc = useTranslations("credits");
  const tNav = useTranslations("nav");
  const ta = useTranslations("account");
  const tf = useTranslations("feedback");
  const router = useRouter();
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const setUser = useAuthStore((s) => s.setUser);
  const resumeGame = useGameStore((s) => s.resumeGame);
  const hydrateSessionDetail = useGameStore((s) => s.hydrateSessionDetail);

  const [busySession, setBusySession] = useState<string | null>(null);
  const [loggingOut, setLoggingOut] = useState(false);

  // 个人信息编辑（移动端）：头像上传 / 昵称内联编辑 / 改密码弹层
  const fileRef = useRef<HTMLInputElement>(null);
  const [avatarBusy, setAvatarBusy] = useState(false);
  const [avatarError, setAvatarError] = useState<string | null>(null);
  const [editingNick, setEditingNick] = useState(false);
  const [nickDraft, setNickDraft] = useState("");
  const [nickBusy, setNickBusy] = useState(false);
  const [pwOpen, setPwOpen] = useState(false);
  const [fbOpen, setFbOpen] = useState(false);

  const onPickAvatar = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    const bad = validateImageFile(file);
    if (bad) {
      setAvatarError(bad === "size" ? ta("avatarTooLarge") : ta("avatarBadType"));
      return;
    }
    setAvatarBusy(true);
    setAvatarError(null);
    try {
      setUser(await uploadAvatar(await readAsDataUrl(file)));
    } catch (err) {
      setAvatarError(err instanceof Error ? err.message : ta("updateFailed"));
    } finally {
      setAvatarBusy(false);
    }
  };

  const saveNick = async () => {
    const value = nickDraft.trim();
    if (value.length < 1 || value.length > 50) return;
    if (value === (user?.nickname?.trim() || "")) {
      setEditingNick(false);
      return;
    }
    setNickBusy(true);
    try {
      setUser(await updateProfile({ nickname: value }));
      setEditingNick(false);
    } catch {
      /* 错误时保持编辑态，用户可重试 */
    } finally {
      setNickBusy(false);
    }
  };

  useEffect(() => {
    void (async () => {
      const auth = useAuthStore.getState();
      const u = auth.hasLoaded ? auth.user : await auth.loadMe();
      if (!u) router.replace(buildLoginHref("/me"));
    })();
  }, [router]);

  const { data: balance } = useQuery({
    queryKey: CREDIT_BALANCE_QUERY_KEY,
    queryFn: fetchCreditBalance,
    staleTime: 30_000,
    enabled: !!user,
  });
  const { data: games = [] } = useGameHistory();

  const level = creditLevel(balance?.balance);
  const palette = balanceTone(level);
  const balanceColor = level === "normal" ? "var(--lv-ink)" : palette.color;
  const recent = useMemo(
    () =>
      [...games]
        .filter((game) => game.status === "playing" || game.status === "paused")
        .sort((a, b) => parseBackendIso(b.last_played_at).getTime() - parseBackendIso(a.last_played_at).getTime())
        .slice(0, 3),
    [games],
  );
  const stats = useMemo(
    () => ({
      plays: games.length,
      perfect: games.filter((g) => g.ending_type === "perfect").length,
      rounds: games.reduce((s, g) => s + (g.rounds_played ?? 0), 0),
    }),
    [games],
  );

  const displayName = user?.nickname || user?.identities.find((i) => i.email)?.email || t("fallbackName");
  const initial = (displayName.trim()[0] || "玩").toUpperCase();
  const hasPassword = user?.identities.some((i) => i.provider === "password") ?? false;

  const openGame = async (game: GameHistoryItem) => {
    if (busySession) return;
    setBusySession(game.session_id);
    try {
      const detail = await apiFetch<GameSessionDetail>(`/api/game/${game.session_id}/detail`);
      hydrateSessionDetail(detail);
      if (game.status === "paused") await resumeGame(game.session_id);
      router.push(`/play/${game.session_id}`);
    } catch (reason) {
      if (isUnauthorizedError(reason)) router.replace(buildLoginHref("/me"));
    } finally {
      setBusySession(null);
    }
  };

  const handleLogout = async () => {
    setLoggingOut(true);
    await logout();
    router.push("/");
  };

  return (
    <main className="lv-theme me-root">
      <div aria-hidden className="me-glow" />

      <ProductNav variant="solid" />
      <div className="me-mobile-notify">
        <NotificationBell />
      </div>

      {/* 桌面：账户中心 */}
      <AccountShell active="account">
        <AccountProfile />
      </AccountShell>

      {/* 移动：个人 hub */}
      <motion.div className="me-wrap me-mobile" variants={lvStaggerContainer} initial="hidden" animate="show">
        <motion.header className="me-profile" variants={lvStaggerItem}>
          <button
            type="button"
            className="me-avatar me-avatar-btn"
            onClick={() => fileRef.current?.click()}
            disabled={avatarBusy}
            aria-label={ta("editAvatar")}
          >
            {user?.avatar_url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={ossThumb(user.avatar_url, 72)} alt="" />
            ) : (
              <span>{initial}</span>
            )}
            <span className="me-avatar-cam" aria-hidden>
              {avatarBusy ? <Loader2 size={13} className="me-spin" /> : <Camera size={12} />}
            </span>
          </button>
          <input
            ref={fileRef}
            type="file"
            accept="image/png,image/jpeg,image/webp"
            hidden
            onChange={(e) => void onPickAvatar(e)}
          />
          <div className="me-profile-text">
            {editingNick ? (
              <div className="me-nick-edit">
                <input
                  className="me-nick-input"
                  value={nickDraft}
                  autoFocus
                  maxLength={50}
                  disabled={nickBusy}
                  placeholder={ta("nicknamePlaceholder")}
                  onChange={(e) => setNickDraft(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") void saveNick();
                    if (e.key === "Escape") setEditingNick(false);
                  }}
                />
                <button type="button" className="me-nick-icon" onClick={() => void saveNick()} disabled={nickBusy} aria-label={ta("save")}>
                  {nickBusy ? <Loader2 size={15} className="me-spin" /> : <Check size={15} />}
                </button>
                <button type="button" className="me-nick-icon" onClick={() => setEditingNick(false)} disabled={nickBusy} aria-label={ta("cancel")}>
                  <X size={15} />
                </button>
              </div>
            ) : (
              <div className="me-nick-row">
                <h1>{displayName}</h1>
                <button
                  type="button"
                  className="me-nick-pencil"
                  onClick={() => {
                    setNickDraft(user?.nickname?.trim() || "");
                    setEditingNick(true);
                  }}
                  aria-label={ta("edit")}
                >
                  <PenLine size={13} />
                </button>
              </div>
            )}
            {avatarError && <span className="me-avatar-err">{avatarError}</span>}
            {stats.plays > 0 && (
              <div className="me-stats">
                <span>
                  <b>{stats.plays}</b> {t("statPlays")}
                </span>
                <i />
                <span>
                  <b style={{ color: "var(--lv-accent)" }}>{stats.perfect}</b> {t("statPerfect")}
                </span>
                <i />
                <span>
                  <b>{stats.rounds}</b> {t("statRounds")}
                </span>
              </div>
            )}
          </div>
        </motion.header>

        <motion.section className="me-credit-card" variants={lvStaggerItem}>
          <div>
            <span className="lv-t-caps me-credit-label">{tc("title")}</span>
            <div className="me-credit-value" style={{ color: balanceColor }}>
              {balance ? fmtCredits(balance.balance) : "—"}
              <span>{tc("unit")}</span>
            </div>
          </div>
          <Link href="/me/credits" className="me-credit-action">
            {t("creditAction")}
            <ChevronRight size={14} />
          </Link>
        </motion.section>

        <motion.section className="me-section" variants={lvStaggerItem}>
          <div className="me-section-head">
            <h2>{t("historyTitle")}</h2>
            <Link href="/history">{t("seeAll")}</Link>
          </div>

          {recent.length > 0 ? (
            <div className="me-history-strip">
              {recent.map((game) => (
                <button
                  key={game.session_id}
                  type="button"
                  className="me-history-card"
                  onClick={() => void openGame(game)}
                  disabled={busySession === game.session_id}
                >
                  <span className="me-history-cover">
                    {game.cover_image && (
                      <span
                        className="me-history-img"
                        style={{ backgroundImage: `url(${ossThumb(game.cover_image, 180)})` }}
                        aria-hidden
                      />
                    )}
                    <span className="me-history-badge" style={{ color: badgeColor(game) }}>
                      {busySession === game.session_id ? t("enter") : badgeLabel(game, th)}
                    </span>
                  </span>
                  <span className="me-history-title">{game.world_name}</span>
                  <span className="me-history-meta">{relTime(game.last_played_at, th)}</span>
                </button>
              ))}
              <Link href="/history" className="me-history-all">
                <span className="me-history-all-box">
                  <ArrowRight size={17} />
                </span>
                <span className="me-history-title">{t("allHistory")}</span>
                <span className="me-history-meta">{t("allHistorySub")}</span>
              </Link>
            </div>
          ) : (
            <div className="me-empty">
              <p>{t("emptyText")}</p>
              <Link href="/discover">{t("emptyCta")}</Link>
            </div>
          )}
        </motion.section>

        <motion.section className="me-section" variants={lvStaggerItem}>
          <div className="me-section-head">
            <h2>{t("moreTitle")}</h2>
          </div>
          <div className="me-more">
            <Link href="/workshop" className="me-more-row">
              <span>
                <PenLine size={16} />
                {t("works")}
              </span>
              <ChevronRight size={15} />
            </Link>
            <button type="button" className="me-more-row" onClick={() => setPwOpen(true)}>
              <span>
                <KeyRound size={16} />
                {ta("changePassword")}
              </span>
              <ChevronRight size={15} />
            </button>
            <button type="button" className="me-more-row" onClick={() => setFbOpen(true)}>
              <span>
                <MessageSquare size={16} />
                {tf("entry")}
              </span>
              <ChevronRight size={15} />
            </button>
          </div>
        </motion.section>

        <motion.footer className="me-foot" variants={lvStaggerItem}>
          <button type="button" className="me-logout" onClick={() => void handleLogout()} disabled={loggingOut}>
            <LogOut size={14} />
            {loggingOut ? t("loggingOut") : tNav("logout")}
          </button>
        </motion.footer>
      </motion.div>

      <Modal open={pwOpen} onClose={() => setPwOpen(false)} title={ta("changePassword")} maxWidth={420}>
        <ChangePasswordForm hasPassword={hasPassword} onDone={() => setPwOpen(false)} />
      </Modal>

      <FeedbackDialog open={fbOpen} onClose={() => setFbOpen(false)} />

      <style jsx global>{`
        .me-root {
          background: var(--lv-bg);
          color: var(--lv-ink);
          min-height: 100dvh;
          overflow-x: hidden;
          position: relative;
          padding-bottom: calc(84px + env(safe-area-inset-bottom));
        }
        @media (min-width: 769px) {
          .me-root {
            padding-bottom: 0;
          }
          .me-mobile {
            display: none !important;
          }
        }
        .me-glow {
          position: absolute;
          top: -180px;
          left: 50%;
          transform: translateX(-50%);
          width: 760px;
          height: 520px;
          pointer-events: none;
          background: radial-gradient(ellipse 50% 50% at 50% 50%, rgba(223, 194, 144, 0.06), transparent 70%);
        }
        .me-mobile-notify {
          position: absolute;
          top: calc(env(safe-area-inset-top, 0px) + 14px);
          right: 20px;
          z-index: 5;
          display: none;
        }
        .me-wrap {
          position: relative;
          z-index: 2;
          max-width: 760px;
          margin: 0 auto;
          padding: 14px clamp(16px, 5vw, 28px) 0;
          display: flex;
          flex-direction: column;
          gap: 24px;
        }
        @media (max-width: 768px) {
          .me-mobile-notify {
            display: block;
          }
          .me-wrap {
            padding-top: calc(env(safe-area-inset-top, 0px) + 34px);
          }
        }
        .me-profile {
          display: flex;
          align-items: center;
          gap: 16px;
        }
        .me-avatar {
          width: 56px;
          height: 56px;
          border-radius: 50%;
          display: grid;
          place-items: center;
          overflow: hidden;
          background: rgba(245, 242, 235, 0.08);
          border: 1px solid var(--lv-line-2);
          box-shadow: 0 10px 24px rgba(0, 0, 0, 0.35);
          flex-shrink: 0;
        }
        .me-avatar img {
          width: 100%;
          height: 100%;
          object-fit: cover;
        }
        .me-avatar span {
          font-family: var(--lv-font-serif);
          font-size: 24px;
          font-weight: 500;
          color: var(--lv-ink);
        }
        .me-avatar-btn {
          padding: 0;
          cursor: pointer;
          position: relative;
        }
        .me-avatar-btn:disabled {
          cursor: wait;
        }
        .me-avatar-cam {
          position: absolute;
          left: 0;
          right: 0;
          bottom: 0;
          height: 19px;
          display: grid;
          place-items: center;
          background: rgba(0, 0, 0, 0.52);
          color: var(--lv-ink);
        }
        .me-spin {
          animation: me-spin 1s linear infinite;
        }
        @keyframes me-spin {
          to {
            transform: rotate(360deg);
          }
        }
        .me-profile-text {
          min-width: 0;
        }
        .me-nick-row {
          display: flex;
          align-items: center;
          gap: 8px;
        }
        .me-nick-pencil {
          width: 28px;
          height: 28px;
          flex-shrink: 0;
          border: 1px solid var(--lv-line-2);
          border-radius: 50%;
          background: rgba(255, 255, 255, 0.04);
          color: var(--lv-ink-3);
          display: grid;
          place-items: center;
          cursor: pointer;
          transition: color var(--lv-dur-fast) var(--lv-ease);
        }
        .me-nick-pencil:hover {
          color: var(--lv-ink);
        }
        .me-nick-edit {
          display: flex;
          align-items: center;
          gap: 6px;
        }
        .me-nick-input {
          height: 40px;
          flex: 1;
          min-width: 0;
          border-radius: var(--lv-r-pill);
          border: 1px solid rgba(255, 255, 255, 0.10);
          background: rgba(255, 255, 255, 0.045);
          color: var(--lv-ink);
          padding: 0 16px;
          font-family: var(--lv-font-sans);
          font-size: 13px;
          outline: none;
          transition:
            border-color var(--lv-dur-fast) var(--lv-ease),
            background var(--lv-dur-fast) var(--lv-ease);
        }
        .me-nick-input::placeholder {
          color: var(--lv-ink-3);
        }
        .me-nick-input:focus {
          border-color: rgba(255, 255, 255, 0.22);
          background: rgba(255, 255, 255, 0.07);
        }
        .me-nick-icon {
          width: 38px;
          height: 38px;
          flex-shrink: 0;
          border: 1px solid var(--lv-line-2);
          border-radius: 50%;
          background: rgba(255, 255, 255, 0.04);
          color: var(--lv-ink-2);
          display: grid;
          place-items: center;
          cursor: pointer;
        }
        .me-nick-icon:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }
        .me-avatar-err {
          display: block;
          margin-top: 4px;
          color: var(--lv-danger);
          font-size: var(--lv-t-meta);
        }
        .me-profile h1 {
          margin: 0;
          font-family: var(--lv-font-serif);
          font-size: 20px;
          font-weight: 500;
          line-height: 1.15;
          color: var(--lv-ink);
          word-break: break-word;
        }
        .me-stats {
          margin-top: 7px;
          display: flex;
          align-items: center;
          gap: 9px;
          font-size: var(--lv-t-meta);
          color: var(--lv-ink-3);
        }
        .me-stats b {
          color: var(--lv-ink);
          font-weight: 600;
          font-variant-numeric: tabular-nums;
        }
        .me-stats i {
          width: 1px;
          height: 11px;
          background: var(--lv-line-2);
        }
        .me-credit-card {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 16px;
          padding: 16px 18px;
          border-radius: var(--lv-r-card);
          border: 1px solid var(--lv-line);
          background:
            linear-gradient(180deg, rgba(255, 255, 255, 0.024), rgba(255, 255, 255, 0.012)),
            var(--lv-bg);
        }
        .me-credit-label {
          color: var(--lv-ink-3);
        }
        .me-credit-value {
          margin-top: 6px;
          display: flex;
          align-items: baseline;
          gap: 8px;
          font-size: 24px;
          font-weight: 600;
          font-variant-numeric: tabular-nums;
        }
        .me-credit-value span {
          color: var(--lv-ink-3);
          font-size: var(--lv-t-meta);
          font-weight: 400;
        }
        .me-credit-action {
          display: inline-flex;
          align-items: center;
          gap: 2px;
          min-height: 44px;
          padding: 0 14px;
          border-radius: var(--lv-r-pill);
          border: 1px solid var(--lv-line-2);
          background: transparent;
          color: var(--lv-ink-2);
          font-size: var(--lv-t-compact);
          font-weight: 600;
          text-decoration: none;
          flex-shrink: 0;
        }
        .me-section-head {
          display: flex;
          align-items: baseline;
          justify-content: space-between;
          gap: 12px;
          margin-bottom: 12px;
        }
        .me-section-head h2 {
          margin: 0;
          font-family: var(--lv-font-serif);
          font-size: 22px;
          font-weight: 500;
        }
        .me-section-head a {
          color: var(--lv-ink-3);
          font-size: var(--lv-t-meta);
          text-decoration: none;
        }
        .me-history-strip {
          display: flex;
          gap: 10px;
          overflow-x: auto;
          scroll-snap-type: x mandatory;
          /* 左边走正常盒模型让首卡与标题对齐（iOS Safari 下「scroll 容器内 padding 顶回」会失效→贴左）；右边保留出血给横滑手感 */
          margin: 0 calc(-1 * clamp(16px, 5vw, 28px)) 0 0;
          padding: 2px 0 4px;
          scrollbar-width: none;
        }
        .me-history-strip::-webkit-scrollbar {
          display: none;
        }
        .me-history-card,
        .me-history-all {
          flex: 0 0 120px;
          scroll-snap-align: start;
          min-width: 0;
          padding: 0;
          border: 0;
          background: transparent;
          color: inherit;
          text-align: left;
          text-decoration: none;
          cursor: pointer;
        }
        .me-history-card:disabled {
          opacity: 0.65;
          cursor: wait;
        }
        .me-history-cover,
        .me-history-all-box {
          position: relative;
          display: grid;
          place-items: center;
          aspect-ratio: 3 / 2;
          border-radius: 11px;
          overflow: hidden;
          box-shadow: 0 8px 18px rgba(0, 0, 0, 0.22);
        }
        .me-history-cover {
          border: 1px solid var(--lv-line);
          background:
            radial-gradient(ellipse at 60% 70%, rgba(223, 194, 144, 0.12), transparent 58%),
            linear-gradient(150deg, #15181d, #07080a);
        }
        .me-history-img {
          position: absolute;
          inset: 0;
          background-size: cover;
          background-position: center 30%;
        }
        .me-history-cover::after {
          content: "";
          position: absolute;
          inset: 0;
          background: linear-gradient(180deg, transparent 45%, rgba(0, 0, 0, 0.5));
        }
        .me-history-all-box {
          border: 1px solid rgba(223, 194, 144, 0.28);
          background:
            radial-gradient(ellipse at 50% 40%, rgba(223, 194, 144, 0.16), transparent 62%),
            linear-gradient(150deg, rgba(223, 194, 144, 0.08), rgba(255, 255, 255, 0.015));
          color: var(--lv-accent);
        }
        .me-history-badge {
          position: absolute;
          left: 6px;
          top: 6px;
          z-index: 2;
          height: 18px;
          display: inline-flex;
          align-items: center;
          padding: 0 7px;
          border-radius: var(--lv-r-pill);
          border: 1px solid rgba(255, 255, 255, 0.1);
          background: rgba(5, 5, 7, 0.7);
          backdrop-filter: blur(8px);
          font-family: var(--lv-font-mono);
          font-size: var(--lv-t-micro);
          letter-spacing: 0.06em;
        }
        .me-history-title {
          display: block;
          margin-top: 7px;
          color: var(--lv-ink);
          font-size: var(--lv-t-compact);
          font-weight: 500;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .me-history-meta {
          display: block;
          margin-top: 2px;
          color: var(--lv-ink-3);
          font-size: var(--lv-t-meta);
          font-variant-numeric: tabular-nums;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .me-empty {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 12px;
          padding: 16px;
          border-radius: var(--lv-r-card);
          border: 1px dashed var(--lv-line-2);
          color: var(--lv-ink-3);
          font-size: var(--lv-t-compact);
        }
        .me-empty a {
          color: var(--lv-ink);
          text-decoration: none;
          flex-shrink: 0;
        }
        .me-more {
          display: flex;
          flex-direction: column;
          gap: 9px;
        }
        .me-more-row {
          height: 52px;
          padding: 0 16px;
          border-radius: var(--lv-r-card);
          border: 1px solid var(--lv-line);
          background: rgba(255, 255, 255, 0.024);
          color: var(--lv-ink-2);
          text-decoration: none;
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 10px;
          font-size: var(--lv-t-compact);
          width: 100%;
          cursor: pointer;
        }
        .me-more-row span:first-child {
          display: inline-flex;
          align-items: center;
          gap: 10px;
        }
        .me-more-row.is-disabled {
          opacity: 0.6;
          cursor: default;
        }
        .me-soon {
          font-family: var(--lv-font-mono);
          font-size: 10px;
          letter-spacing: 0.1em;
          color: var(--lv-ink-4);
        }
        .me-foot {
          display: flex;
          justify-content: center;
          padding-top: 2px;
        }
        .me-logout {
          display: inline-flex;
          align-items: center;
          justify-content: center;
          gap: 8px;
          width: 100%;
          max-width: 280px;
          height: 44px;
          border-radius: var(--lv-r-card);
          border: 1px solid rgba(239, 130, 118, 0.18);
          background: rgba(239, 130, 118, 0.045);
          color: var(--lv-danger);
          font-size: var(--lv-t-compact);
          cursor: pointer;
        }
        @media (max-width: 420px) {
          .me-credit-card {
            align-items: stretch;
            flex-direction: column;
          }
          .me-credit-action {
            justify-content: center;
            height: 44px;
          }
        }
      `}</style>
    </main>
  );
}
