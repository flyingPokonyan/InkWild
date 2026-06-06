"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";

import { CreditBalanceChip } from "@/components/CreditBalanceChip";
import { useGameStore } from "@/stores/game";

interface GameHeaderProps {
  drawerOpen: boolean;
  onToggleDrawer: () => void;
  onPause: () => void;
  /** 退出落点：来自 ?return=（工坊试玩等），缺省回首页。 */
  exitHref?: string;
  /** 案件板/侧边抽屉入口按钮。案件板未开放时由 play 页传 false 隐藏。 */
  showBoardButton?: boolean;
}

export function GameHeader({ drawerOpen, onToggleDrawer, onPause, exitHref = "/", showBoardButton = true }: GameHeaderProps) {
  const gameState = useGameStore((state) => state.gameState);
  const sessionId = useGameStore((state) => state.sessionId);
  const clueCount = gameState?.discovered_clues.length || 0;
  const t = useTranslations("play");
  const headerMeta = [
    gameState?.current_time,
    gameState?.round_number != null ? `第 ${gameState.round_number} 回合` : null,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <header className="play-header">
      <div className="play-header-inner">
        <div className="play-header-left">
          <Link
            href={exitHref}
            title={t("leaveWorld")}
            className="play-header-button play-header-icon-button"
            aria-label={t("leaveWorld")}
          >
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M19 12H5" />
              <path d="m12 19-7-7 7-7" />
            </svg>
          </Link>

          <div className="play-header-copy">
            {gameState?.current_location && (
              <span className="play-header-title">
                {gameState.current_location}
              </span>
            )}
            {headerMeta && (
              <span className="play-header-meta">
                {headerMeta}
              </span>
            )}
          </div>
        </div>

        <div className="play-header-right">
          <CreditBalanceChip variant="plain" scope="session" sessionId={sessionId ?? undefined} />

          <button
            type="button"
            onClick={onPause}
            title={t("pause")}
            aria-label={t("pause")}
            className="play-header-button play-header-icon-button"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
              <rect x="6" y="4" width="4" height="16" rx="1" />
              <rect x="14" y="4" width="4" height="16" rx="1" />
            </svg>
          </button>

          {showBoardButton && (
            <button
              type="button"
              onClick={onToggleDrawer}
              className="play-header-button play-header-board-button"
            >
              <span>{drawerOpen ? t("closePanel") : t("openCaseBoard")}</span>
              {clueCount > 0 && !drawerOpen && (
                <span className="play-header-clue-badge">
                  {clueCount}
                </span>
              )}
            </button>
          )}
        </div>
      </div>
    </header>
  );
}
