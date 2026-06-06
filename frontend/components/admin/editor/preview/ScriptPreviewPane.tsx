"use client";

import { useTranslations } from "next-intl";

import type { ScriptDraftPayload } from "@/lib/types";
import { isKnownEndingType } from "@/lib/draft-schemas";

import { PreviewBlock, PreviewCover, PreviewEmpty } from "./PreviewFrame";

interface ScriptPreviewPaneProps {
  payload: ScriptDraftPayload;
}

const ENDING_COLOR: Record<string, string> = {
  good: "var(--lv-accent)",
  normal: "var(--lv-ink-2)",
  bad: "var(--lv-danger)",
  hidden: "var(--lv-ink-3)",
  timeout: "var(--lv-warn)",
};

export function ScriptPreviewPane({ payload }: ScriptPreviewPaneProps) {
  const t = useTranslations("admin.editor.preview");
  const tEnd = useTranslations("admin.editor.script.endingType");

  const sortedEvents = [...payload.events].sort(
    (a, b) => (b.priority ?? 0) - (a.priority ?? 0),
  );
  const sortedEndings = [...payload.endings].sort(
    (a, b) => (b.priority ?? 0) - (a.priority ?? 0),
  );
  const clueCount = Object.keys(payload.clues).length;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--lv-s-8)" }}>
      <PreviewBlock caps={t("scriptCaps")}>
        <article
          style={{
            display: "flex",
            flexDirection: "column",
            gap: "var(--lv-s-3)",
            background: "var(--lv-bg-1)",
            border: "1px solid var(--lv-line)",
            borderRadius: "var(--lv-r-card)",
            padding: "var(--lv-s-3)",
          }}
        >
          {payload.cover_image && (
            <PreviewCover src={payload.cover_image} ratio="3/2" alt={payload.name || ""} />
          )}
          <div className="lv-t-caps" style={{ color: "var(--lv-ink-3)" }}>
            ◆ SCRIPT
          </div>
          <h3 className="lv-t-h3" style={{ margin: 0, color: "var(--lv-ink)" }}>
            {payload.name || t("untitledScript")}
          </h3>
          <p
            className="lv-t-body"
            style={{
              margin: 0,
              color: "var(--lv-ink-2)",
              display: "-webkit-box",
              WebkitLineClamp: 3,
              WebkitBoxOrient: "vertical",
              overflow: "hidden",
            }}
          >
            {payload.description || t("noDescription")}
          </p>
          <div className="lv-t-meta" style={{ color: "var(--lv-ink-3)" }}>
            {["★".repeat(payload.difficulty), payload.estimated_time, `clues · ${clueCount}`]
              .filter(Boolean)
              .join(" · ")}
          </div>
        </article>
      </PreviewBlock>

      <PreviewBlock caps={t("timelineCaps")}>
        {sortedEvents.length === 0 ? (
          <PreviewEmpty>{t("noEvents")}</PreviewEmpty>
        ) : (
          <ol
            style={{
              display: "flex",
              flexDirection: "column",
              gap: 0,
              margin: 0,
              padding: 0,
              listStyle: "none",
              borderLeft: "1px solid var(--lv-line-2)",
              paddingLeft: "var(--lv-s-4)",
            }}
          >
            {sortedEvents.slice(0, 12).map((event, i) => (
              <li
                key={`evt-${i}`}
                style={{
                  position: "relative",
                  paddingTop: "var(--lv-s-2)",
                  paddingBottom: "var(--lv-s-2)",
                }}
              >
                <span
                  aria-hidden
                  style={{
                    position: "absolute",
                    left: -19,
                    top: 14,
                    width: 6,
                    height: 6,
                    borderRadius: "50%",
                    background: "var(--lv-ink-3)",
                    border: "2px solid var(--lv-bg)",
                  }}
                />
                <div className="lv-t-meta" style={{ color: "var(--lv-ink-4)" }}>
                  {event.trigger_type}
                  {event.priority ? ` · p${event.priority}` : ""}
                </div>
                <div
                  className="lv-t-body"
                  style={{ color: "var(--lv-ink)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}
                >
                  {event.name || "—"}
                </div>
              </li>
            ))}
            {sortedEvents.length > 12 && (
              <li className="lv-t-meta" style={{ color: "var(--lv-ink-4)", paddingTop: "var(--lv-s-2)" }}>
                +{sortedEvents.length - 12}
              </li>
            )}
          </ol>
        )}
      </PreviewBlock>

      <PreviewBlock caps={t("endingsCaps")}>
        {sortedEndings.length === 0 ? (
          <PreviewEmpty>{t("noEndings")}</PreviewEmpty>
        ) : (
          <div style={{ display: "grid", gap: "var(--lv-s-2)", gridTemplateColumns: "1fr" }}>
            {sortedEndings.map((ending, i) => {
              const color = ENDING_COLOR[ending.ending_type] ?? "var(--lv-ink-3)";
              return (
                <div
                  key={`end-${i}`}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "var(--lv-s-3)",
                    padding: "var(--lv-s-3)",
                    background: "var(--lv-bg-1)",
                    border: "1px solid var(--lv-line)",
                    borderRadius: "var(--lv-r-card)",
                  }}
                >
                  <span
                    aria-hidden
                    style={{
                      width: 6,
                      height: 24,
                      background: color,
                      borderRadius: 3,
                      flexShrink: 0,
                    }}
                  />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div className="lv-t-body" style={{ color: "var(--lv-ink)" }}>
                      {ending.title || "—"}
                    </div>
                    <div className="lv-t-meta" style={{ color: "var(--lv-ink-3)" }}>
                      {isKnownEndingType(ending.ending_type) ? tEnd(ending.ending_type) : ending.ending_type}
                      {ending.priority ? ` · p${ending.priority}` : ""}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </PreviewBlock>
    </div>
  );
}
