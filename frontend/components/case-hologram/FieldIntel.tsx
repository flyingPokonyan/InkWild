"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";

import type { GameState } from "@/lib/types";

interface FieldIntelProps {
  gameState: GameState | null;
}

export function FieldIntel({ gameState }: FieldIntelProps) {
  const [open, setOpen] = useState(false);
  const t = useTranslations("play.case");

  if (!gameState) return null;

  const {
    current_location,
    current_time,
    round_number,
  } = gameState;
  const player_inventory = gameState.player_inventory ?? [];
  const visited_locations = gameState.visited_locations ?? [];

  return (
    <section style={{ display: "grid", gap: "var(--lv-s-3)" }}>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex w-full items-center justify-between"
        style={{ background: "transparent", border: 0, padding: 0 }}
      >
        <h2 className="lv-t-caps" style={{ color: "var(--lv-ink-3)" }}>
          {t("fieldIntel")}
        </h2>
        <svg
          width="12"
          height="12"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          style={{
            color: "var(--lv-ink-3)",
            transform: open ? "rotate(180deg)" : "rotate(0deg)",
            transition: "transform var(--lv-dur-fast) var(--lv-ease)",
          }}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {open && (
        <div style={{ display: "grid", gap: "var(--lv-s-4)" }}>
          {/* Location / Time / Round grid */}
          <div className="grid grid-cols-3" style={{ gap: "var(--lv-s-2)" }}>
            {current_location && (
              <Cell label={t("location")} value={current_location} />
            )}
            {current_time && <Cell label={t("time")} value={current_time} />}
            {round_number != null && (
              <Cell label={t("round")} value={String(round_number)} />
            )}
          </div>

          {player_inventory.length > 0 && (
            <div style={{ display: "grid", gap: "var(--lv-s-2)" }}>
              <h3 className="lv-t-caps" style={{ color: "var(--lv-ink-3)" }}>
                {t("inventory")}
              </h3>
              <div className="flex flex-wrap" style={{ gap: "var(--lv-s-1)" }}>
                {player_inventory.map((item) => (
                  <Tag key={item}>{item}</Tag>
                ))}
              </div>
            </div>
          )}

          {visited_locations.length > 0 && (
            <div style={{ display: "grid", gap: "var(--lv-s-2)" }}>
              <h3 className="lv-t-caps" style={{ color: "var(--lv-ink-3)" }}>
                {t("visited")}
              </h3>
              <div className="flex flex-wrap" style={{ gap: "var(--lv-s-1)" }}>
                {visited_locations.map((loc) => (
                  <Tag key={loc}>{loc}</Tag>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </section>
  );
}

function Cell({ label, value }: { label: string; value: string }) {
  return (
    <div
      style={{
        borderRadius: "var(--lv-r-card)",
        border: "1px solid var(--lv-line)",
        padding: "var(--lv-s-2) var(--lv-s-3)",
      }}
    >
      <div className="lv-t-caps" style={{ color: "var(--lv-ink-3)" }}>
        {label}
      </div>
      <div className="lv-t-body" style={{ marginTop: 2, color: "var(--lv-ink-2)" }}>
        {value}
      </div>
    </div>
  );
}

function Tag({ children }: { children: React.ReactNode }) {
  return (
    <span
      className="lv-t-meta"
      style={{
        borderRadius: "var(--lv-r-pill)",
        border: "1px solid var(--lv-line)",
        background: "rgba(255, 255, 255, 0.03)",
        padding: "2px var(--lv-s-2)",
        color: "var(--lv-ink-2)",
      }}
    >
      {children}
    </span>
  );
}
