"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";

import type { NpcDynamicEntry } from "@/lib/types";

interface NpcDynamicListProps {
  npcDynamic: Record<string, NpcDynamicEntry> | undefined;
  /** NPC names to exclude (e.g. those already rendered in SuspectProfiles). */
  excludeNames?: readonly string[];
}

/**
 * Tier 1 NPC 状态-关系图：每个 NPC 一张卡，可展开看 last_shift_reason。
 */
const PREVIEW_COUNT = 4;

export function NpcDynamicList({ npcDynamic, excludeNames }: NpcDynamicListProps) {
  const [expanded, setExpanded] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(false);
  const t = useTranslations("play.case");

  const exclude = new Set(excludeNames ?? []);
  const entries = Object.entries(npcDynamic ?? {}).filter(
    ([name]) => !exclude.has(name),
  );
  if (entries.length === 0) return null;

  const visible = showAll ? entries : entries.slice(0, PREVIEW_COUNT);
  const hiddenCount = entries.length - visible.length;

  return (
    <section style={{ display: "grid", gap: "var(--lv-s-3)" }}>
      <div className="flex items-center justify-between">
        <h2 className="lv-t-caps" style={{ color: "var(--lv-ink-3)" }}>
          {t("npcDynamic")}
        </h2>
        <span className="lv-t-meta" style={{ color: "var(--lv-ink-3)" }}>
          {entries.length}
        </span>
      </div>
      <div style={{ display: "grid", gap: "var(--lv-s-2)" }}>
        {visible.map(([name, entry]) => {
          const isOpen = expanded === name;
          const trust = entry.trust;
          const trustPct =
            typeof trust === "number" ? Math.max(0, Math.min(10, trust)) * 10 : null;

          return (
            <button
              key={name}
              type="button"
              onClick={() => setExpanded(isOpen ? null : name)}
              style={{
                width: "100%",
                borderRadius: "var(--lv-r-card)",
                border: "1px solid var(--lv-line)",
                background: "transparent",
                padding: "var(--lv-s-3) var(--lv-s-4)",
                textAlign: "left",
                transition: "background var(--lv-dur-fast) var(--lv-ease)",
              }}
            >
              <div className="flex items-center justify-between">
                <span className="lv-t-body" style={{ color: "var(--lv-ink)" }}>
                  {name}
                </span>
                {entry.current_stance && (
                  <span className="lv-t-meta" style={{ color: "var(--lv-ink-3)" }}>
                    {entry.current_stance}
                  </span>
                )}
              </div>

              <div
                className="flex flex-wrap"
                style={{
                  marginTop: "var(--lv-s-2)",
                  gap: "var(--lv-s-3)",
                  alignItems: "center",
                }}
              >
                {trustPct != null && (
                  <div className="flex items-center" style={{ gap: "var(--lv-s-2)" }}>
                    <span className="lv-t-caps" style={{ color: "var(--lv-ink-3)" }}>
                      {t("trust")}
                    </span>
                    <span
                      aria-hidden="true"
                      style={{
                        position: "relative",
                        display: "inline-block",
                        width: 60,
                        height: 3,
                        borderRadius: "var(--lv-r-pill)",
                        background: "rgba(255, 255, 255, 0.08)",
                      }}
                    >
                      <span
                        style={{
                          position: "absolute",
                          inset: 0,
                          right: `${100 - trustPct}%`,
                          background: "var(--lv-accent)",
                          borderRadius: "var(--lv-r-pill)",
                        }}
                      />
                    </span>
                    <span className="lv-t-meta" style={{ color: "var(--lv-ink-2)" }}>
                      {trust}
                    </span>
                  </div>
                )}
                {entry.mood && (
                  <div className="lv-t-meta" style={{ color: "var(--lv-ink-3)" }}>
                    {t("mood")}{" "}
                    <span style={{ color: "var(--lv-ink-2)" }}>{entry.mood}</span>
                  </div>
                )}
              </div>

              {isOpen && entry.last_shift_reason && (
                <p
                  className="lv-t-meta"
                  style={{
                    marginTop: "var(--lv-s-3)",
                    paddingTop: "var(--lv-s-3)",
                    borderTop: "1px solid var(--lv-line)",
                    color: "var(--lv-ink-3)",
                    lineHeight: 1.6,
                  }}
                >
                  {entry.last_shift_reason}
                </p>
              )}
            </button>
          );
        })}
      </div>
      {hiddenCount > 0 && (
        <button
          type="button"
          onClick={() => setShowAll(true)}
          className="lv-t-meta"
          style={{
            alignSelf: "flex-start",
            background: "transparent",
            border: 0,
            padding: "var(--lv-s-1) 0",
            color: "var(--lv-accent)",
            cursor: "pointer",
          }}
        >
          {t("showMore", { n: hiddenCount })}
        </button>
      )}
      {showAll && entries.length > PREVIEW_COUNT && (
        <button
          type="button"
          onClick={() => setShowAll(false)}
          className="lv-t-meta"
          style={{
            alignSelf: "flex-start",
            background: "transparent",
            border: 0,
            padding: "var(--lv-s-1) 0",
            color: "var(--lv-ink-3)",
            cursor: "pointer",
          }}
        >
          {t("collapse")}
        </button>
      )}
    </section>
  );
}
