"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";

import type { ClueDTO } from "@/lib/types";

interface CluesListProps {
  clues: ClueDTO[];
}

const PREVIEW_COUNT = 6;

/**
 * 已发现线索清单，按 game_state.discovered_clues 倒序渲染（最新在上）。
 * 长 session 容易堆几十条，默认只展示最新 6 条，余下点开。
 */
export function CluesList({ clues }: CluesListProps) {
  const [expanded, setExpanded] = useState(false);
  const t = useTranslations("play.case");
  if (clues.length === 0) return null;

  const ordered = [...clues].reverse();
  const visible = expanded ? ordered : ordered.slice(0, PREVIEW_COUNT);
  const hiddenCount = ordered.length - visible.length;

  return (
    <section style={{ display: "grid", gap: "var(--lv-s-3)" }}>
      <div className="flex items-center justify-between">
        <h2 className="lv-t-caps" style={{ color: "var(--lv-ink-3)" }}>
          {t("clues")}
        </h2>
        <span className="lv-t-meta" style={{ color: "var(--lv-ink-3)" }}>
          {clues.length}
        </span>
      </div>
      <ul style={{ display: "grid", gap: "var(--lv-s-2)" }}>
        {visible.map((c) => (
          <li
            key={c.id}
            style={{
              borderRadius: "var(--lv-r-card)",
              border: "1px solid var(--lv-line)",
              padding: "var(--lv-s-3) var(--lv-s-4)",
              display: "grid",
              gap: "var(--lv-s-1)",
            }}
          >
            <p
              className="lv-t-body"
              style={{ color: "var(--lv-ink-2)", lineHeight: 1.7 }}
            >
              {c.content}
            </p>
            {c.found_at && (
              <span className="lv-t-meta" style={{ color: "var(--lv-ink-3)" }}>
                {c.found_at}
              </span>
            )}
          </li>
        ))}
      </ul>
      {hiddenCount > 0 && (
        <button
          type="button"
          onClick={() => setExpanded(true)}
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
      {expanded && clues.length > PREVIEW_COUNT && (
        <button
          type="button"
          onClick={() => setExpanded(false)}
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
