"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { Play, Search, ChevronRight, RefreshCw } from "lucide-react";
import { useTranslations } from "next-intl";

import { useQueryClient } from "@tanstack/react-query";

import { ProductNav } from "@/components/ProductNav";
import { MobileTopBar } from "@/components/MobileTopBar";
import { LoadingPulse } from "@/components/ui/LoadingPulse";
import { useConfirm } from "@/components/ui/ConfirmDialog";
import { apiFetch, isUnauthorizedError } from "@/lib/api";
import { abandonGameSession, gameHistoryQueryKeys, useGameHistory } from "@/lib/api/history";
import { buildLoginHref } from "@/lib/auth-redirect";
import { parseBackendIso } from "@/lib/datetime";
import type { GameHistoryItem, GameSessionDetail } from "@/lib/types";
import { ossThumb } from "@/lib/oss-image";
import { LazyCover } from "@/components/ui/LazyCover";
import { useAuthStore } from "@/stores/auth";
import { useGameStore } from "@/stores/game";

type FilterKey = "all" | "active" | "ended";

type HistoryT = {
  (key: string): string;
  (key: string, values: { n: number }): string;
};

function endingThemeColor(type: string | null): string {
  switch (type) {
    case "perfect":
      return "var(--lv-accent)";
    case "good":
      return "var(--lv-ink)";
    case "bad":
      return "#ef8276";
    case "timeout":
    default:
      return "var(--lv-ink-3)";
  }
}

function endingName(type: string | null, t: HistoryT): string {
  switch (type) {
    case "perfect":
      return t("endingName.perfect");
    case "good":
      return t("endingName.good");
    case "bad":
      return t("endingName.bad");
    case "timeout":
      return t("endingName.timeout");
    case "test_exit":
      return t("endingName.test_exit");
    case "abandoned":
      return t("endingName.abandoned");
    default:
      return t("endingFallback");
  }
}

function formatShortDate(iso: string): string {
  const d = parseBackendIso(iso);
  const month = d.getMonth() + 1;
  const day = d.getDate();
  if (d.getFullYear() === new Date().getFullYear()) return `${month}.${day}`;
  return `${String(d.getFullYear()).slice(2)}.${month}.${day}`;
}

function formatRelative(iso: string, t: HistoryT): string {
  const ts = parseBackendIso(iso).getTime();
  const diff = Date.now() - ts;
  const m = Math.round(diff / 60000);
  if (m < 1) return t("timeJustNow");
  if (m < 60) return t("timeMinutesAgo", { n: m });
  const h = Math.round(m / 60);
  if (h < 24) return t("timeHoursAgo", { n: h });
  const d = Math.round(h / 24);
  if (d < 7) return t("timeDaysAgo", { n: d });
  return formatShortDate(iso);
}

// 卡片元数据：把"进行中/暂停"和"结局名"统一抽象成 { label, color }
// 颜色绑定到 token，badge 边框 / 卡外 action 文字共用。
function cardBadge(
  game: GameHistoryItem,
  t: HistoryT,
): { label: string; color: string } {
  if (game.status === "ended") {
    return {
      label: endingName(game.ending_type, t),
      color: endingThemeColor(game.ending_type),
    };
  }
  return {
    label: game.status === "paused" ? t("statusPaused") : t("statusPlaying"),
    color: "var(--lv-accent)",
  };
}

export default function HistoryPage() {
  const t = useTranslations("historyPage");
  const router = useRouter();
  const confirm = useConfirm();
  const queryClient = useQueryClient();
  const resumeGame = useGameStore((state) => state.resumeGame);
  const hydrateSessionDetail = useGameStore((state) => state.hydrateSessionDetail);

  const [busySession, setBusySession] = useState<string | null>(null);
  const [endingSession, setEndingSession] = useState<string | null>(null);
  const [openError, setOpenError] = useState<string | null>(null);
  const [filter, setFilter] = useState<FilterKey>("all");
  const [searchQuery, setSearchQuery] = useState("");

  const { data: games = [], isLoading, isError, error, refetch } = useGameHistory();

  useEffect(() => {
    void (async () => {
      const auth = useAuthStore.getState();
      const user = auth.hasLoaded ? auth.user : await auth.loadMe();
      if (!user) router.replace(buildLoginHref("/history"));
    })();
  }, [router]);

  useEffect(() => {
    if (isError && isUnauthorizedError(error)) {
      router.replace(buildLoginHref("/history"));
    }
  }, [isError, error, router]);

  const handleOpen = async (game: GameHistoryItem) => {
    if (busySession) return;
    setBusySession(game.session_id);
    setOpenError(null);
    try {
      const detail = await apiFetch<GameSessionDetail>(
        `/api/game/${game.session_id}/detail`,
      );
      hydrateSessionDetail(detail);
      if (game.status === "paused") {
        await resumeGame(game.session_id);
      }
      router.push(`/play/${game.session_id}`);
    } catch (reason) {
      if (isUnauthorizedError(reason)) {
        router.replace(buildLoginHref("/history"));
        return;
      }
      setOpenError(reason instanceof Error ? reason.message : t("openError"));
    } finally {
      setBusySession(null);
    }
  };

  // 在历史页主动结束一局进行中的对局。二次确认 → /abandon → 失效 history 缓存：
  // 卡片随之从「继续游玩」移到「最近结束」，badge 变「已放弃」，即为给玩家的「表示」。
  const handleEnd = async (game: GameHistoryItem) => {
    if (busySession || endingSession) return;
    const ok = await confirm({
      title: t("endConfirmTitle"),
      message: t("endConfirmMessage", { world: game.world_name }),
      confirmText: t("endConfirmConfirm"),
      cancelText: t("endConfirmCancel"),
      danger: true,
    });
    if (!ok) return;
    setEndingSession(game.session_id);
    setOpenError(null);
    try {
      await abandonGameSession(game.session_id);
      await queryClient.invalidateQueries({ queryKey: gameHistoryQueryKeys.all });
    } catch (reason) {
      if (isUnauthorizedError(reason)) {
        router.replace(buildLoginHref("/history"));
        return;
      }
      setOpenError(reason instanceof Error ? reason.message : t("endError"));
    } finally {
      setEndingSession(null);
    }
  };

  const { activeGames, endedGames } = useMemo(
    () => ({
      activeGames: games.filter((g) => g.status === "playing" || g.status === "paused"),
      endedGames: games.filter((g) => g.status === "ended"),
    }),
    [games],
  );

  const q = searchQuery.trim().toLowerCase();
  const matchQ = (g: GameHistoryItem) =>
    !q ||
    g.world_name.toLowerCase().includes(q) ||
    (g.character_name || "").toLowerCase().includes(q) ||
    (g.current_location || "").toLowerCase().includes(q);

  const filteredActive = filter === "ended" ? [] : activeGames.filter(matchQ);
  const filteredEnded = filter === "active" ? [] : endedGames.filter(matchQ);

  const totalRounds = games.reduce((s, g) => s + (g.rounds_played ?? 0), 0);

  const errorMessage =
    isError && !isUnauthorizedError(error)
      ? error instanceof Error
        ? error.message
        : t("errorTitle")
      : null;

  return (
    <main
      className="lv-theme"
      style={{
        background: "var(--lv-bg)",
        color: "var(--lv-ink)",
        minHeight: "100dvh",
        overflowX: "hidden",
        position: "relative",
      }}
    >
      <ProductNav active="history" variant="solid" />

      <MobileHistoryView
        filter={filter}
        setFilter={setFilter}
        searchQuery={searchQuery}
        setSearchQuery={setSearchQuery}
        activeGames={filteredActive}
        endedGames={filteredEnded}
        busySession={busySession}
        endingSession={endingSession}
        onOpen={handleOpen}
        onEnd={handleEnd}
        isLoading={isLoading}
      />

      <div
        className="lv-history-desktop"
        style={{
          maxWidth: 1440,
          margin: "0 auto",
          padding: "100px clamp(20px, 4vw, 52px) 80px",
          position: "relative",
          zIndex: 2,
        }}
      >
        <header
          style={{
            display: "flex",
            alignItems: "flex-end",
            justifyContent: "space-between",
            gap: 24,
            paddingBottom: 18,
            borderBottom: "1px solid rgba(255,255,255,0.05)",
            flexWrap: "wrap",
          }}
        >
          <div>
            <div className="lv-t-caps" style={{ color: "var(--lv-ink-3)" }}>
              {t("eyebrow")}
            </div>
            <h1
              style={{
                margin: "6px 0 0",
                fontFamily: "var(--lv-font-serif), Georgia, serif",
                fontSize: "clamp(26px, 3.5vw, 36px)",
                fontWeight: 500,
                letterSpacing: "-0.01em",
              }}
            >
              {t("titleMain")}
            </h1>
          </div>

          {games.length > 0 && (
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 14,
                fontFamily: "var(--lv-font-mono)",
                fontSize: 11,
                letterSpacing: "0.14em",
                color: "var(--lv-ink-3)",
                textTransform: "uppercase",
              }}
            >
              <StatPair n={activeGames.length} word="active" />
              <span style={{ opacity: 0.3 }}>·</span>
              <StatPair n={endedGames.length} word="ended" />
              <span style={{ opacity: 0.3 }}>·</span>
              <StatPair n={totalRounds} word="rounds" />
            </div>
          )}
        </header>

        <section
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            gap: 20,
            marginTop: 28,
            flexWrap: "wrap",
          }}
        >
          <FilterPills
            filter={filter}
            setFilter={setFilter}
            counts={{ all: games.length, active: activeGames.length, ended: endedGames.length }}
            t={t}
          />

          <div
            style={{
              position: "relative",
              display: "inline-flex",
              alignItems: "center",
              width: 280,
              maxWidth: "100%",
            }}
          >
            <Search
              size={14}
              style={{
                position: "absolute",
                left: 14,
                color: "var(--lv-ink-3)",
                pointerEvents: "none",
              }}
            />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder={t("searchPlaceholder")}
              style={{
                width: "100%",
                height: 38,
                padding: "0 16px 0 38px",
                background: "rgba(255,255,255,0.015)",
                border: "1px solid rgba(255,255,255,0.05)",
                borderRadius: 100,
                color: "var(--lv-ink)",
                fontSize: 13,
                outline: 0,
                transition: "all 0.25s ease",
              }}
            />
          </div>
        </section>

        {(errorMessage || openError) && (
          <div
            style={{
              marginTop: 20,
              padding: "12px 18px",
              borderRadius: 8,
              background: "rgba(184, 92, 92, 0.08)",
              border: "1px solid rgba(184, 92, 92, 0.2)",
              color: "#f7aaaa",
              fontSize: 13,
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              gap: 12,
            }}
          >
            <span>{openError || errorMessage}</span>
            <button
              onClick={() => refetch()}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 6,
                background: "transparent",
                border: "1px solid rgba(247, 170, 170, 0.3)",
                color: "#f7aaaa",
                padding: "4px 12px",
                borderRadius: 100,
                fontSize: 12,
                cursor: "pointer",
              }}
            >
              <RefreshCw size={12} /> {t("retry")}
            </button>
          </div>
        )}

        {isLoading && (
          <div style={{ marginTop: 44, display: "flex", justifyContent: "center" }}>
            <LoadingPulse variant="block" />
          </div>
        )}

        {!isLoading && filteredActive.length > 0 && (
          <section style={{ marginTop: 44 }}>
            <SectionHeader title={t("activeSectionTitle")} hint={`${filteredActive.length} active`} />
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
                gap: 24,
              }}
            >
              <AnimatePresence mode="popLayout">
                {filteredActive.map((g, i) => (
                  <HistoryCard
                    key={g.session_id}
                    game={g}
                    index={i}
                    busy={busySession === g.session_id}
                    ending={endingSession === g.session_id}
                    onOpen={() => void handleOpen(g)}
                    onEnd={() => void handleEnd(g)}
                  />
                ))}
              </AnimatePresence>
            </div>
          </section>
        )}

        {!isLoading && filteredEnded.length > 0 && (
          <section style={{ marginTop: 60 }}>
            <SectionHeader title={t("endedSectionTitle")} hint={`${filteredEnded.length} ended`} />
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
                gap: 24,
              }}
            >
              {filteredEnded.map((g, i) => (
                <HistoryCard
                  key={g.session_id}
                  game={g}
                  index={i}
                  busy={busySession === g.session_id}
                  onOpen={() => void handleOpen(g)}
                />
              ))}
            </div>
          </section>
        )}

        {!isLoading && games.length === 0 && (
          <div
            style={{
              marginTop: 60,
              padding: "60px 24px",
              textAlign: "center",
              background: "rgba(255,255,255,0.01)",
              border: "1px dashed rgba(255,255,255,0.06)",
              borderRadius: 16,
            }}
          >
            <h3 style={{ fontSize: 16, color: "var(--lv-ink-2)" }}>{t("archiveEmptyTitle")}</h3>
            <p style={{ marginTop: 6, color: "var(--lv-ink-4)", fontSize: 13.5 }}>
              {t("archiveEmptyHint")}
            </p>
          </div>
        )}
      </div>

      <style jsx global>{`
        .lv-history-card {
          cursor: pointer;
          transition: transform 350ms cubic-bezier(0.16, 1, 0.3, 1);
        }
        .lv-history-card[data-busy="true"] {
          cursor: wait;
          opacity: 0.7;
        }
        .lv-history-card:hover {
          transform: translateY(-3px);
        }
        .lv-history-card:hover .lv-history-cover {
          border-color: rgba(255, 255, 255, 0.12);
          box-shadow: 0 16px 32px rgba(0, 0, 0, 0.45);
        }
        .lv-history-card:hover .lv-history-cover-img {
          transform: scale(1.04);
        }
        .lv-history-card:hover .lv-history-play {
          opacity: 1;
          transform: scale(1.08);
        }
        .lv-history-end-btn:hover {
          color: #ef8276 !important;
          border-color: rgba(239, 130, 118, 0.4) !important;
        }
        .lv-history-end-btn:disabled {
          cursor: wait;
        }
        @media (max-width: 768px) {
          .lv-history-desktop { display: none !important; }
        }
        @media (min-width: 769px) {
          .lv-history-mobile { display: none !important; }
        }
      `}</style>
    </main>
  );
}

// ---------- shared pieces ----------

function StatPair({ n, word }: { n: number; word: string }) {
  return (
    <span>
      <span style={{ color: "var(--lv-ink)" }}>{n}</span> {word}
    </span>
  );
}

function FilterPills({
  filter,
  setFilter,
  counts,
  t,
}: {
  filter: FilterKey;
  setFilter: (k: FilterKey) => void;
  counts: { all: number; active: number; ended: number };
  t: HistoryT;
}) {
  const items: { key: FilterKey; label: string; count: number }[] = [
    { key: "all", label: t("filterAll"), count: counts.all },
    { key: "active", label: t("filterActive"), count: counts.active },
    { key: "ended", label: t("filterEnded"), count: counts.ended },
  ];
  return (
    <div
      style={{
        display: "flex",
        gap: 4,
        padding: 4,
        background: "rgba(255,255,255,0.015)",
        border: "1px solid rgba(255,255,255,0.06)",
        borderRadius: 100,
        backdropFilter: "blur(8px)",
      }}
    >
      {items.map((item) => {
        const selected = filter === item.key;
        return (
          <button
            key={item.key}
            onClick={() => setFilter(item.key)}
            style={{
              position: "relative",
              padding: "6px 18px",
              borderRadius: 100,
              border: 0,
              background: "transparent",
              color: selected ? "var(--lv-bg)" : "var(--lv-ink-2)",
              fontSize: 13,
              fontWeight: 600,
              cursor: "pointer",
              transition: "color 0.25s ease",
              outline: 0,
              display: "inline-flex",
              alignItems: "center",
              gap: 6,
              zIndex: 1,
            }}
          >
            {selected && (
              <motion.div
                layoutId="history-filter-pill-bg"
                style={{
                  position: "absolute",
                  inset: 0,
                  borderRadius: 100,
                  background: "rgba(245, 242, 235, 0.90)",
                  boxShadow: "0 2px 8px rgba(0, 0, 0, 0.25)",
                  zIndex: -1,
                }}
                transition={{ type: "spring", stiffness: 380, damping: 30 }}
              />
            )}
            <span>{item.label}</span>
            <span
              style={{
                fontSize: 10,
                opacity: selected ? 0.85 : 0.5,
                fontFamily: "var(--lv-font-mono)",
                color: selected ? "#050507" : "inherit",
                fontWeight: 700,
                background: selected ? "rgba(5, 5, 7, 0.08)" : "rgba(255, 255, 255, 0.04)",
                padding: "1px 6px",
                borderRadius: 6,
              }}
            >
              {item.count}
            </span>
          </button>
        );
      })}
    </div>
  );
}

function SectionHeader({ title, hint }: { title: string; hint: string }) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "baseline",
        justifyContent: "space-between",
        marginBottom: 16,
      }}
    >
      <h2
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: 10,
          fontFamily: "var(--lv-font-serif)",
          fontSize: 20,
          fontWeight: 600,
          color: "var(--lv-ink)",
        }}
      >
        <span style={{ width: 3, height: 16, background: "var(--lv-accent)", borderRadius: 2 }} />
        {title}
      </h2>
      <span
        style={{
          fontFamily: "var(--lv-font-mono)",
          fontSize: 10,
          letterSpacing: "0.14em",
          textTransform: "uppercase",
          color: "var(--lv-ink-4)",
        }}
      >
        {hint}
      </span>
    </div>
  );
}

// ---------- desktop card ----------
// 结构对齐 discover/page.tsx 的 LobbyWorldCard：
//  - 3:2 封面 frame：hover 时 border 加亮 + 阴影下沉 + 内层图 scale(1.04)
//  - 左上角 badge：active=金色边、ended=结局色边
//  - 右下角 hover-only 圆形 play btn（opacity 0.92 → 1 + scale 1.08）
//  - 卡外标题 + 角色行 + 底部 meta row（border-top）

function HistoryCard({
  game,
  index,
  busy,
  ending = false,
  onOpen,
  onEnd,
}: {
  game: GameHistoryItem;
  index: number;
  busy: boolean;
  ending?: boolean;
  onOpen: () => void;
  onEnd?: () => void;
}) {
  const t = useTranslations("historyPage");
  const badge = cardBadge(game, t);
  // 剧本模式优先用剧本封面，回落到世界封面
  const cover = ossThumb(game.script_cover_image || game.cover_image, 480);
  const isEnded = game.status === "ended";
  const actionLabel = isEnded ? t("reviewAction") : t("continueAction");
  const timeLabel = formatRelative(game.last_played_at, t);
  const subtitle =
    [game.character_name, game.current_location && t("atPlace", { place: game.current_location })]
      .filter(Boolean)
      .join(" · ");

  return (
    <motion.article
      layout
      initial={{ opacity: 0, y: 15 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.97 }}
      transition={{ duration: 0.45, delay: Math.min(index * 0.03, 0.3) }}
      onClick={busy || ending ? undefined : onOpen}
      className="lv-history-card"
      data-busy={busy || ending}
    >
      {/* 封面 frame —— 完全对齐 LobbyWorldCard */}
      <div
        className="lv-history-cover"
        style={{
          position: "relative",
          aspectRatio: "3 / 2",
          borderRadius: 12,
          overflow: "hidden",
          background: "var(--lv-bg-1)",
          marginBottom: 10,
          border: "1px solid rgba(255, 255, 255, 0.06)",
          boxShadow: "0 6px 15px rgba(0, 0, 0, 0.2)",
          transition: "all 350ms cubic-bezier(0.16, 1, 0.3, 1)",
        }}
      >
        {cover && (
          <LazyCover
            className="lv-history-cover-img"
            url={cover}
            aria-hidden
            style={{
              position: "absolute",
              inset: 0,
              backgroundPosition: "center 30%",
              transition: "transform 600ms cubic-bezier(0.16, 1, 0.3, 1)",
            }}
          />
        )}
        <div
          aria-hidden
          style={{
            position: "absolute",
            inset: 0,
            background:
              "linear-gradient(to top, rgba(8, 8, 10, 0.28) 0%, transparent 35%)",
          }}
        />

        {/* badge 左上 —— 对齐 LobbyWorldCard 的 mode badge 位置 */}
        <span
          style={{
            position: "absolute",
            top: 8,
            left: 8,
            padding: "2px 8px",
            borderRadius: 4,
            background: "rgba(8, 8, 10, 0.72)",
            border: `1px solid ${badge.color}55`,
            color: badge.color,
            fontFamily: "var(--lv-font-mono)",
            fontSize: 9,
            fontWeight: 700,
            letterSpacing: "0.06em",
            textTransform: "uppercase",
            zIndex: 2,
            backdropFilter: "blur(8px)",
          }}
        >
          {badge.label}
        </span>

        {/* hover play btn —— 对齐 LobbyWorldCard 的 world-card-btn */}
        <span
          className="lv-history-play"
          aria-hidden
          style={{
            position: "absolute",
            inset: "auto 10px 10px auto",
            display: "grid",
            placeItems: "center",
            width: 34,
            height: 34,
            borderRadius: "50%",
            background: "rgba(245, 242, 235, 0.95)",
            color: "#08080a",
            zIndex: 2,
            boxShadow: "0 4px 12px rgba(0, 0, 0, 0.4)",
            opacity: 0.92,
            transition: "all 250ms cubic-bezier(0.16, 1, 0.3, 1)",
          }}
        >
          {busy ? (
            <RefreshCw size={12} className="spin-slow" />
          ) : (
            <Play size={12} fill="currentColor" strokeWidth={0} style={{ marginLeft: 1 }} />
          )}
        </span>
      </div>

      {/* 标题 */}
      <h3
        style={{
          margin: "0 0 4px",
          color: "var(--lv-ink)",
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
          fontFamily: "var(--lv-font-serif)",
          fontSize: 18,
          fontWeight: 500,
          transition: "color 200ms ease",
        }}
      >
        {game.world_name}
      </h3>

      {/* 角色 + 位置 —— 保留与 discover 卡片描述区一致的两行高度，避免卡片高低不一。 */}
      <p
        style={{
          margin: "0 0 10px",
          fontSize: 12.5,
          color: "var(--lv-ink-3)",
          lineHeight: 1.45,
          overflow: "hidden",
          textOverflow: "ellipsis",
          display: "-webkit-box",
          WebkitLineClamp: 2,
          WebkitBoxOrient: "vertical",
          height: 36,
        }}
      >
        {subtitle || "\u00a0"}
      </p>

      {/* meta row —— 对齐 LobbyWorldCard 底部 row（border-top + space-between） */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          color: "var(--lv-ink-3)",
          fontSize: 11.5,
          borderTop: "1px solid rgba(255, 255, 255, 0.04)",
          paddingTop: 8,
        }}
      >
        <span style={{ fontFamily: "var(--lv-font-mono)", letterSpacing: "0.04em" }}>
          {timeLabel}
          {game.rounds_played != null ? ` · R${game.rounds_played}` : ""}
        </span>
        <span style={{ display: "inline-flex", alignItems: "center", gap: 14 }}>
          {onEnd && !isEnded && (
            <button
              type="button"
              className="lv-history-end-btn"
              onClick={(e) => {
                e.stopPropagation();
                onEnd();
              }}
              disabled={ending}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 4,
                background: "transparent",
                border: 0,
                padding: 0,
                color: "var(--lv-ink-4)",
                fontWeight: 600,
                fontSize: 11.5,
                cursor: ending ? "wait" : "pointer",
                transition: "color 0.2s ease",
              }}
            >
              {ending ? <RefreshCw size={11} className="spin-slow" /> : t("endAction")}
            </button>
          )}
          <span
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 3,
              color: badge.color,
              fontWeight: 600,
            }}
          >
            {actionLabel} <ChevronRight size={11} />
          </span>
        </span>
      </div>
    </motion.article>
  );
}

// ---------- mobile ----------

interface MobileHistoryViewProps {
  filter: FilterKey;
  setFilter: (v: FilterKey) => void;
  searchQuery: string;
  setSearchQuery: (v: string) => void;
  activeGames: GameHistoryItem[];
  endedGames: GameHistoryItem[];
  busySession: string | null;
  endingSession: string | null;
  onOpen: (g: GameHistoryItem) => void;
  onEnd: (g: GameHistoryItem) => void;
  isLoading: boolean;
}

function MobileHistoryView({
  filter,
  setFilter,
  searchQuery,
  setSearchQuery,
  activeGames,
  endedGames,
  busySession,
  endingSession,
  onOpen,
  onEnd,
  isLoading,
}: MobileHistoryViewProps) {
  const t = useTranslations("historyPage");
  const showActive = filter !== "ended";
  const showEnded = filter !== "active";

  return (
    <div
      className="lv-history-mobile"
      style={{
        position: "relative",
        zIndex: 2,
        paddingBottom: "calc(76px + env(safe-area-inset-bottom))",
      }}
    >
      <MobileTopBar brand={t("titleMain")} />

      <div style={{ padding: "0 12px" }}>
        {/* search */}
        <div
          style={{
            position: "relative",
            display: "flex",
            alignItems: "center",
            margin: "10px 4px 4px",
          }}
        >
          <Search
            size={15}
            style={{ position: "absolute", left: 14, color: "var(--lv-ink-3)", pointerEvents: "none" }}
          />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder={t("searchPlaceholder")}
            aria-label={t("searchAria")}
            style={{
              width: "100%",
              height: 42,
              padding: "0 16px 0 40px",
              background: "rgba(255,255,255,0.035)",
              border: "1px solid rgba(255,255,255,0.08)",
              borderRadius: 999,
              color: "var(--lv-ink)",
              fontSize: 14,
              outline: 0,
            }}
          />
        </div>

        {/* segmented filter */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(3, 1fr)",
            gap: 4,
            padding: 4,
            margin: "8px 4px 14px",
            borderRadius: 999,
            border: "1px solid rgba(255,255,255,0.08)",
            background: "rgba(255,255,255,0.035)",
          }}
        >
          {(
            [
              { k: "all" as const, label: t("filterAll") },
              { k: "active" as const, label: t("filterActive") },
              { k: "ended" as const, label: t("filterEnded") },
            ]
          ).map((seg) => {
            const active = filter === seg.k;
            return (
              <button
                key={seg.k}
                type="button"
                onClick={() => setFilter(seg.k)}
                style={{
                  height: 34,
                  borderRadius: 999,
                  border: 0,
                  background: active ? "rgba(245,242,235,0.90)" : "transparent",
                  color: active ? "var(--lv-bg)" : "var(--lv-ink-3)",
                  fontFamily: "var(--lv-font-mono)",
                  fontSize: 9,
                  letterSpacing: "0.14em",
                  cursor: "pointer",
                }}
              >
                {seg.label}
              </button>
            );
          })}
        </div>

        {showActive && (
          <>
            <MobileSectionHead
              title={t("activeSectionTitle")}
              hint={`${activeGames.length} active`}
            />
            {activeGames.length === 0 ? (
              <MobileEmpty text={isLoading ? "" : t("emptyActiveDesc")} />
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 9, marginBottom: 4 }}>
                {activeGames.map((g) => (
                  <MobileHistoryRow
                    key={g.session_id}
                    game={g}
                    busy={busySession === g.session_id}
                    ending={endingSession === g.session_id}
                    onOpen={() => onOpen(g)}
                    onEnd={() => onEnd(g)}
                  />
                ))}
              </div>
            )}
          </>
        )}

        {showEnded && (
          <>
            <MobileSectionHead
              title={t("endedSectionTitle")}
              hint={`${endedGames.length} ended`}
            />
            {endedGames.length === 0 ? (
              <MobileEmpty text={isLoading ? "" : t("emptyEndedDesc")} />
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 9 }}>
                {endedGames.map((g) => (
                  <MobileHistoryRow
                    key={g.session_id}
                    game={g}
                    busy={busySession === g.session_id}
                    onOpen={() => onOpen(g)}
                  />
                ))}
                <div
                  style={{
                    textAlign: "center",
                    padding: "18px 0 2px",
                    color: "var(--lv-ink-4)",
                    fontSize: 12,
                  }}
                >
                  {t("bottomReached")}
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function MobileSectionHead({ title, hint }: { title: string; hint: string }) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "baseline",
        justifyContent: "space-between",
        padding: "12px 4px 10px",
      }}
    >
      <h2
        style={{
          fontFamily: "var(--lv-font-serif)",
          fontSize: 21,
          fontWeight: 500,
          color: "var(--lv-ink)",
        }}
      >
        {title}
      </h2>
      <span
        style={{
          fontFamily: "var(--lv-font-mono)",
          fontSize: 9,
          letterSpacing: "0.14em",
          color: "var(--lv-ink-4)",
        }}
      >
        {hint}
      </span>
    </div>
  );
}

function MobileEmpty({ text }: { text: string }) {
  return (
    <p
      style={{
        margin: "0 4px 12px",
        padding: "16px 14px",
        borderRadius: 16,
        border: "1px dashed rgba(255,255,255,0.08)",
        color: "var(--lv-ink-3)",
        fontSize: 12.5,
      }}
    >
      {text}
    </p>
  );
}

// 移动端列 —— 对齐 discover/MobileWorldRow 的 40/60 split
function MobileHistoryRow({
  game,
  busy,
  ending = false,
  onOpen,
  onEnd,
}: {
  game: GameHistoryItem;
  busy: boolean;
  ending?: boolean;
  onOpen: () => void;
  onEnd?: () => void;
}) {
  const t = useTranslations("historyPage");
  const badge = cardBadge(game, t);
  // 剧本模式优先用剧本封面，回落到世界封面
  const cover = ossThumb(game.script_cover_image || game.cover_image, 480);
  const isEnded = game.status === "ended";
  const actionLabel = isEnded ? t("reviewAction") : t("continueAction");
  const timeLabel = formatRelative(game.last_played_at, t);
  const subtitle =
    [game.character_name, game.current_location && t("atPlace", { place: game.current_location })]
      .filter(Boolean)
      .join(" · ");

  return (
    <article
      onClick={busy || ending ? undefined : onOpen}
      style={{
        display: "grid",
        gridTemplateColumns: "36% 1fr",
        minHeight: 132,
        borderRadius: 18,
        overflow: "hidden",
        border: "1px solid rgba(255,255,255,0.08)",
        background: "rgba(255,255,255,0.055)",
        cursor: busy || ending ? "wait" : "pointer",
        opacity: busy || ending ? 0.7 : 1,
      }}
    >
      <div
        style={{
          position: "relative",
          backgroundSize: "cover",
          backgroundPosition: "center",
          backgroundImage: cover
            ? `linear-gradient(180deg, rgba(0,0,0,0.05), rgba(0,0,0,0.36)), url(${cover})`
            : "linear-gradient(135deg, var(--lv-bg-1), var(--lv-bg-2))",
        }}
      >
        <span
          style={{
            position: "absolute",
            left: 8,
            top: 8,
            padding: "2px 8px",
            borderRadius: 4,
            background: "rgba(5,5,7,0.72)",
            border: `1px solid ${badge.color}55`,
            color: badge.color,
            fontFamily: "var(--lv-font-mono)",
            fontSize: 9,
            fontWeight: 700,
            letterSpacing: "0.06em",
            textTransform: "uppercase",
            backdropFilter: "blur(8px)",
          }}
        >
          {badge.label}
        </span>
      </div>
      <div style={{ minWidth: 0, padding: "12px 14px 11px 16px", display: "flex", flexDirection: "column" }}>
        <span
          style={{
            fontFamily: "var(--lv-font-mono)",
            fontSize: 9,
            letterSpacing: "0.14em",
            color: "var(--lv-ink-3)",
            marginBottom: 5,
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
          }}
        >
          {timeLabel}
          {game.rounds_played != null ? ` · R${game.rounds_played}` : ""}
        </span>
        <h3
          style={{
            fontFamily: "var(--lv-font-serif)",
            fontSize: 17,
            fontWeight: 500,
            lineHeight: 1.12,
            color: "var(--lv-ink)",
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
            marginBottom: 6,
          }}
        >
          {game.world_name}
        </h3>
        {subtitle && (
          <p
            style={{
              color: "var(--lv-ink-2)",
              fontSize: 11.5,
              lineHeight: 1.42,
              display: "-webkit-box",
              WebkitLineClamp: 2,
              WebkitBoxOrient: "vertical",
              overflow: "hidden",
              margin: 0,
            }}
          >
            {subtitle}
          </p>
        )}
        <div
          style={{
            marginTop: "auto",
            paddingTop: 9,
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 12,
          }}
        >
          {onEnd && !isEnded ? (
            <button
              type="button"
              className="lv-history-end-btn"
              onClick={(e) => {
                e.stopPropagation();
                onEnd();
              }}
              disabled={ending}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 4,
                padding: "7px 12px",
                borderRadius: 999,
                border: "1px solid rgba(255,255,255,0.1)",
                background: "transparent",
                color: "var(--lv-ink-3)",
                fontWeight: 600,
                fontSize: 12,
                cursor: ending ? "wait" : "pointer",
              }}
            >
              {ending ? <RefreshCw size={11} className="spin-slow" /> : t("endAction")}
            </button>
          ) : (
            <span />
          )}
          <span
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 4,
              color: badge.color,
              fontWeight: 600,
              fontSize: 12,
            }}
          >
            {busy ? <RefreshCw size={11} className="spin-slow" /> : null}
            {actionLabel} <ChevronRight size={12} />
          </span>
        </div>
      </div>
    </article>
  );
}
