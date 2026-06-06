"use client";

import { useTranslations } from "next-intl";
import { Play } from "lucide-react";
import type { GameHistoryItem } from "@/lib/types";
import { parseBackendIso } from "@/lib/datetime";

interface SavesCarouselCardProps {
  game: GameHistoryItem;
  busy: boolean;
  onOpen: () => void;
}

export function SavesCarouselCard({ game, busy, onOpen }: SavesCarouselCardProps) {
  const t = useTranslations("history");

  // Relative time helper
  const formatRelative = (iso: string): string => {
    const d = parseBackendIso(iso);
    const ts = d.getTime();
    const diff = Date.now() - ts;
    const m = Math.round(diff / 60000);
    if (m < 1) return "刚刚";
    if (m < 60) return `${m} 分钟前`;
    const h = Math.round(m / 60);
    if (h < 24) return `${h} 小时前`;
    const days = Math.round(h / 24);
    if (days < 7) return `${days} 天前`;
    return d.toLocaleDateString("zh-CN", { month: "short", day: "numeric" });
  };

  const subTitle = [
    game.character_name ? `角色: ${game.character_name}` : null,
    game.rounds_played != null && game.rounds_played > 0 ? `第 ${game.rounds_played} 轮` : null,
  ].filter(Boolean).join(" · ");

  const footerText = [
    formatRelative(game.last_played_at),
    game.current_location ? `@ ${game.current_location}` : null,
  ].filter(Boolean).join(" · ");

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => !busy && onOpen()}
      onKeyDown={(e) => {
        if ((e.key === "Enter" || e.key === " ") && !busy) {
          e.preventDefault();
          onOpen();
        }
      }}
      className="lv-save-premium-card"
      style={{
        display: "flex",
        gap: "var(--lv-s-3)",
        padding: "var(--lv-s-3)",
        background: "rgba(24, 24, 28, 0.45)",
        border: "1px solid rgba(255, 255, 255, 0.05)",
        borderRadius: "var(--lv-r-card)",
        cursor: busy ? "wait" : "pointer",
        opacity: busy ? 0.7 : 1,
        position: "relative",
        alignItems: "center",
        width: 320,
        flexShrink: 0,
        transition: "all var(--lv-dur-fast) var(--lv-ease)",
      }}
    >
      {/* 1:1 Rounded Square Cover Image */}
      <div
        style={{
          width: 80,
          height: 80,
          borderRadius: 12,
          overflow: "hidden",
          background: game.cover_image
            ? `url(${game.cover_image}) center/cover no-repeat`
            : "linear-gradient(135deg, rgba(255, 255, 255, 0.04), var(--lv-bg-2) 50%, var(--lv-bg-1))",
          position: "relative",
          flexShrink: 0,
          boxShadow: "0 4px 12px rgba(0, 0, 0, 0.3)",
        }}
      />

      {/* Save Information details */}
      <div
        style={{
          flex: 1,
          minWidth: 0,
          display: "flex",
          flexDirection: "column",
          gap: 3,
        }}
      >
        {/* World Name */}
        <h4
          className="lv-t-h3"
          style={{
            margin: 0,
            fontFamily: "var(--lv-font-serif)",
            fontWeight: 500,
            color: "var(--lv-ink)",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {game.world_name}
        </h4>

        {/* Character / Rounds info */}
        {subTitle && (
          <p
            className="lv-t-meta"
            style={{
              margin: 0,
              color: "var(--lv-accent)",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
              fontSize: "11px",
              fontFamily: "var(--lv-font-sans)",
            }}
          >
            {subTitle}
          </p>
        )}

        {/* Stop location / time info */}
        {footerText && (
          <p
            className="lv-t-meta"
            style={{
              margin: 0,
              color: "var(--lv-ink-3)",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
              fontFamily: "var(--lv-font-sans)",
            }}
          >
            {footerText}
          </p>
        )}
      </div>

      {/* Hover Resuming Golden Play Overlay Icon */}
      <div
        className="lv-save-card-play-overlay"
        style={{
          position: "absolute",
          right: "var(--lv-s-3)",
          background: "var(--lv-accent)",
          color: "#0c0c10",
          width: 32,
          height: 32,
          borderRadius: "50%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          boxShadow: "0 2px 8px rgba(201, 180, 138, 0.4)",
          opacity: 0,
          transform: "scale(0.8) translateX(5px)",
          transition: "all var(--lv-dur-fast) var(--lv-ease)",
        }}
      >
        <Play size={14} fill="currentColor" style={{ marginLeft: 1 }} />
      </div>

      <style jsx>{`
        .lv-save-premium-card:hover .lv-save-card-play-overlay {
          opacity: 1;
          transform: scale(1) translateX(0);
        }
        .lv-save-premium-card:hover {
          background: rgba(30, 30, 36, 0.75) !important;
          border-color: rgba(201, 180, 138, 0.3) !important;
          box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
        }
      `}</style>
    </div>
  );
}
