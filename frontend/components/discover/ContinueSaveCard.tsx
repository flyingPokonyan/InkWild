"use client";

import Link from "next/link";
import { useState } from "react";
import { Play } from "lucide-react";
import { useTranslations } from "next-intl";

import { ossThumb } from "@/lib/oss-image";
import type { GameHistoryItem } from "@/lib/types";

type ModeT = (k: "modeScript" | "modeFree" | "supportsBoth") => string;

function sessionModeLabel(item: GameHistoryItem, t: ModeT): string {
  if (item.mode === "script") return t("modeScript");
  if (item.mode === "free") return t("modeFree");
  return t("modeFree");
}

export function ContinueSaveCard({ save }: { save: GameHistoryItem }) {
  const [hovered, setHovered] = useState(false);
  const tWorlds = useTranslations("worlds");
  const tHistory = useTranslations("history");

  return (
    <Link
      href={`/play/${save.session_id}`}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        flex: "0 0 280px",
        display: "flex",
        textDecoration: "none",
        color: "inherit",
        borderRadius: "var(--lv-r-card)",
        border: hovered ? "var(--lv-card-border-hover)" : "var(--lv-card-border)",
        background: hovered ? "var(--lv-card-bg-hover)" : "var(--lv-card-bg)",
        backdropFilter: "blur(12px)",
        padding: "10px",
        gap: "12px",
        boxShadow: hovered ? "var(--lv-card-shadow-hover)" : "var(--lv-card-shadow)",
        transition: "border-color 300ms var(--lv-ease), background 300ms var(--lv-ease), box-shadow 300ms var(--lv-ease), transform 300ms var(--lv-ease)",
        transform: hovered ? "translateY(-2px)" : "translateY(0)",
      }}
    >
      <div
        style={{
          width: "66px",
          height: "88px",
          borderRadius: "6px",
          backgroundImage: save.cover_image ? `url(${ossThumb(save.cover_image, 96)})` : undefined,
          backgroundColor: save.cover_image ? undefined : "rgba(255, 255, 255, 0.02)",
          backgroundSize: "cover",
          backgroundPosition: "center",
          border: hovered ? "var(--lv-card-border-hover)" : "var(--lv-card-border)",
          flexShrink: 0,
          transition: "border-color 300ms var(--lv-ease)",
        }}
      />

      <div
        style={{
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          flex: 1,
          minWidth: 0,
        }}
      >
        <div>
          <span
            style={{
              fontSize: "10px",
              fontWeight: 600,
              color: "var(--lv-ink-2)",
              letterSpacing: "0.06em",
              background: "rgba(255, 255, 255, 0.02)",
              border: "1px solid rgba(255, 255, 255, 0.06)",
              padding: "1px 5px",
              borderRadius: "3px",
              display: "inline-block",
              transition: "border-color 300ms var(--lv-ease), background 300ms var(--lv-ease)",
            }}
          >
            {sessionModeLabel(save, tWorlds)}
          </span>

          <div
            style={{
              color: "var(--lv-ink)",
              fontWeight: 600,
              fontSize: "14px",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
              marginTop: "4px",
            }}
          >
            {save.world_name}
          </div>

          <div
            style={{
              fontSize: "12px",
              color: "var(--lv-ink-3)",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
              marginTop: "2px",
            }}
          >
            {save.character_name}
            {save.current_location ? ` · ${save.current_location}` : ""}
          </div>
        </div>

        <div
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "4px",
            fontSize: "11px",
            fontWeight: 600,
            fontVariantNumeric: "tabular-nums",
            color: hovered ? "var(--lv-ink)" : "var(--lv-ink-3)",
            transition: "color 0.2s",
          }}
        >
          <Play size={9} fill="currentColor" strokeWidth={0} />
          {save.rounds_played != null
            ? tHistory("round", { n: save.rounds_played })
            : tHistory("ctaContinue")}
        </div>
      </div>
    </Link>
  );
}
