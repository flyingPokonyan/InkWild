"use client";

import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";

import { ActionInput } from "@/components/ActionInput";
import { CaseHologramPanel } from "@/components/case-hologram/CaseHologramPanel";
import { ChatPanel } from "@/components/ChatPanel";
import { UnifiedSidePanel } from "@/components/UnifiedSidePanel";
import { EndingCinematic } from "@/components/EndingCinematic";
import { GameHeader } from "@/components/GameHeader";
import { GameLoadingScreen } from "@/components/GameLoadingScreen";
import { PauseOverlay } from "@/components/PauseOverlay";
import { buildLoginHref } from "@/lib/auth-redirect";
import { apiFetch, isUnauthorizedError } from "@/lib/api";
import { resolveExitHref } from "@/lib/play-return";
import { getDrawerMode, type DrawerMode } from "@/lib/play-layout";
import { getInitialDrawerOpen, readDrawerPreference, writeDrawerPreference } from "@/lib/play-preferences";
import type { GameSessionDetail } from "@/lib/types";
import { useAuthStore } from "@/stores/auth";
import { useGameStore } from "@/stores/game";

// 案件板（剧本模式 CaseHologramPanel）/ 侧边抽屉（自由模式 UnifiedSidePanel）暂未开放，
// 还在开发中——隐藏 header 入口按钮 + 不渲染面板。开发好后置 true 即可整体恢复。
const PLAY_SIDE_PANEL_ENABLED = false;

export default function PlayPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const searchParams = useSearchParams();
  const exitHref = resolveExitHref(searchParams.get("return"));
  const ending = useGameStore((state) => state.ending);
  const mode = useGameStore((state) => state.mode);
  const gameState = useGameStore((state) => state.gameState);
  const sessionId = useGameStore((state) => state.sessionId);
  const messages = useGameStore((state) => state.messages);
  const isStreaming = useGameStore((state) => state.isStreaming);
  const error = useGameStore((state) => state.error);
  const worldName = useGameStore((state) => state.worldName);
  const scriptName = useGameStore((state) => state.scriptName);
  const characterName = useGameStore((state) => state.characterName);
  const processingHint = useGameStore((state) => state.processingHint);
  const hydrateSessionDetail = useGameStore((state) => state.hydrateSessionDetail);
  const resumeGame = useGameStore((state) => state.resumeGame);
  const hasHydratedSession = sessionId === id && !!gameState;

  const [loading, setLoading] = useState(() => !hasHydratedSession);
  const [pageError, setPageError] = useState<string | null>(null);
  const [showPause, setShowPause] = useState(false);
  const [drawerMode, setDrawerMode] = useState<DrawerMode>(() => {
    if (typeof window === "undefined") return "modal";
    return getDrawerMode(window.innerWidth);
  });
  const [drawerOpen, setDrawerOpen] = useState(() => {
    if (typeof window === "undefined") return false;
    return getInitialDrawerOpen(window.innerWidth, readDrawerPreference(window.sessionStorage));
  });

  // 开局导航已提前到 session_created（玩家在 play 页上看着开场旁白逐字流出来）。
  // 因此 play 页要等到「首句旁白到达」才揭舞台 —— 只看 gameState 的话，state_update
  // 一到就揭开，会露一帧没有正文的空舞台。openingNarrativeArrived = 出现带内容的
  // narrator 消息。
  const openingNarrativeArrived = messages.some(
    (m) => m.role === "narrator" && m.content.trim().length > 0,
  );
  // streaming 中、本会话、且（gameState 还没来 或 首句旁白还没到）→ 继续读条。
  const isInitialLoading =
    isStreaming && sessionId === id && (!gameState || !openingNarrativeArrived);
  // 开场流在出正文前就失败（导航已提前到 play 页）：明确报错 + 重试，不要露空舞台。
  // 注：session_created 之前的失败仍由 gate resolve(null) 留在 setup 页，不会走到这里。
  const openingFailed =
    sessionId === id && !!error && !isStreaming && !openingNarrativeArrived;

  useEffect(() => {
    if (typeof window === "undefined") return;
    writeDrawerPreference(window.sessionStorage, drawerOpen);
  }, [drawerOpen]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const sync = () => setDrawerMode(getDrawerMode(window.innerWidth));
    sync();
    window.addEventListener("resize", sync);
    return () => window.removeEventListener("resize", sync);
  }, []);

  useEffect(() => {
    let active = true;
    // 跳过 detail 拉取的两种情况：
    //  1. 已经 hydrate 过（gameState 在）
    //  2. 当前 zustand 正在流式且 sessionId 匹配 —— 说明刚从 start 跳过来，
    //     streaming 会负责把 state_update 推进 zustand，不需要冗余 fetch
    if (!id || hasHydratedSession || (sessionId === id && isStreaming)) {
      if (loading) setLoading(false);
      return;
    }

    const loadSession = async () => {
      const authStore = useAuthStore.getState();
      const user = authStore.hasLoaded ? authStore.user : await authStore.loadMe();
      const authError = useAuthStore.getState().error;

      if (!active) return;
      if (authError && !user) { setPageError(authError); setLoading(false); return; }
      if (!user) { router.replace(buildLoginHref(`/play/${id}`)); return; }

      try {
        const detail = await apiFetch<GameSessionDetail>(`/api/game/${id}/detail`);
        if (!active) return;
        hydrateSessionDetail(detail);
      } catch (reason) {
        if (!active) return;
        if (isUnauthorizedError(reason)) { router.replace(buildLoginHref(`/play/${id}`)); return; }
        setPageError(reason instanceof Error ? reason.message : "加载会话失败");
      } finally {
        if (active) setLoading(false);
      }
    };

    void loadSession();
    return () => { active = false; };
  }, [hasHydratedSession, hydrateSessionDetail, id, router, sessionId, isStreaming, loading]);

  if (!id) return <CenterMessage title="会话不存在" desc="缺少有效的会话编号，请返回首页重新开始。" showHome />;
  if (ending) return <EndingCinematic />;
  if (isInitialLoading) return <GameLoadingScreen worldName={worldName} scriptName={scriptName} characterName={characterName} processing={processingHint} />;
  if (openingFailed)
    return (
      <CenterMessage
        title="开场没能展开"
        desc={error || "故事开场生成失败了，重试一下试试。"}
        showHome
        onRetry={() => { void resumeGame(id); }}
        retryLabel="重试开场"
      />
    );
  if (!hasHydratedSession && loading) return <CenterMessage title="正在接入故事现场" desc="会话状态与时间线正在同步。" />;
  if (!hasHydratedSession || !gameState) return <CenterMessage title="会话未能恢复" desc={pageError || error || "请返回首页重新开始。"} showHome />;

  return (
    <div className="play-stage">
      {/* v2.2: 氛围层 —— 跟 GameLoadingScreen 视觉延续，10s 周期呼吸光 */}
      <div className="play-stage-aura" aria-hidden />
      <GameHeader
        drawerOpen={drawerOpen}
        onToggleDrawer={() => setDrawerOpen((o) => !o)}
        onPause={() => setShowPause(true)}
        exitHref={exitHref}
        showBoardButton={PLAY_SIDE_PANEL_ENABLED}
      />
      <ChatPanel />
      {error && (
        <div
          className="relative flex justify-center"
          style={{ zIndex: "var(--lv-z-toast)" as unknown as number, marginTop: "var(--lv-s-4)" }}
        >
          <div
            className="lv-t-meta"
            style={{
              borderRadius: "var(--lv-r-pill)",
              background: "rgba(184, 92, 92, 0.1)",
              border: "1px solid rgba(184, 92, 92, 0.3)",
              color: "var(--lv-danger)",
              padding: "var(--lv-s-2) var(--lv-s-4)",
              letterSpacing: "0.04em",
              backdropFilter: "blur(12px)",
              WebkitBackdropFilter: "blur(12px)",
            }}
          >
            {error}
          </div>
        </div>
      )}
      <ActionInput />
      {PLAY_SIDE_PANEL_ENABLED &&
        (mode === "script" ? (
          <CaseHologramPanel
            open={drawerOpen}
            mode={drawerMode}
            onToggle={() => setDrawerOpen((o) => !o)}
          />
        ) : (
          <UnifiedSidePanel
            open={drawerOpen}
            mode={drawerMode}
            onToggle={() => setDrawerOpen((o) => !o)}
          />
        ))}
      {showPause && sessionId && (
        <PauseOverlay sessionId={sessionId} onResume={() => setShowPause(false)} exitHref={exitHref} />
      )}
    </div>
  );
}

function CenterMessage({
  title,
  desc,
  showHome,
  onRetry,
  retryLabel,
}: {
  title: string;
  desc: string;
  showHome?: boolean;
  onRetry?: () => void;
  retryLabel?: string;
}) {
  const t = useTranslations("play");
  return (
    <div className="lv-theme flex min-h-dvh items-center justify-center px-4">
      <div className="max-w-md text-center">
        <div className="lv-t-h2" style={{ color: "var(--lv-ink)" }}>
          {title}
        </div>
        <div
          className="lv-t-body mt-3"
          style={{ color: "var(--lv-ink-2)" }}
        >
          {desc}
        </div>
        {(onRetry || showHome) && (
          <div className="mt-6 flex items-center justify-center gap-3">
            {onRetry && (
              <button
                type="button"
                onClick={onRetry}
                className="lv-btn lv-btn-primary lv-btn-lg inline-flex"
              >
                {retryLabel || "重试"}
              </button>
            )}
            {showHome && (
              <Link
                href="/"
                className={`lv-btn lv-btn-lg inline-flex ${onRetry ? "lv-btn-ghost" : "lv-btn-primary"}`}
              >
                {t("backHome")}
              </Link>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
