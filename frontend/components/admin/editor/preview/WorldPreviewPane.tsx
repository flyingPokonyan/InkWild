"use client";

import { useTranslations } from "next-intl";

import type { WorldDraftPayload } from "@/lib/types";

import { PreviewBlock, PreviewCover, PreviewEmpty } from "./PreviewFrame";

interface WorldPreviewPaneProps {
  payload: WorldDraftPayload;
}

/**
 * 玩家视角预览：
 * 1) discover 卡（cover 3:2 + 名称 + 类型 · 时代 + 难度）
 * 2) 世界详情头（hero 21:9 / 主标题 / 简介）
 * 3) 角色清单（playable 高亮）
 * 4) 地点清单
 */
export function WorldPreviewPane({ payload }: WorldPreviewPaneProps) {
  const t = useTranslations("admin.editor.preview");
  const playable = payload.world_characters.filter((c) => c.playable);
  const npcs = payload.world_characters.filter((c) => !c.playable);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--lv-s-8)" }}>
      <PreviewBlock caps={t("cardCaps")}>
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
          <PreviewCover
            src={payload.cover_image}
            ratio="3/2"
            alt={payload.name || t("untitledWorld")}
          />
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <h3 className="lv-t-h3" style={{ margin: 0, color: "var(--lv-ink)" }}>
              {payload.name || t("untitledWorld")}
            </h3>
            <p
              className="lv-t-body"
              style={{
                margin: 0,
                color: "var(--lv-ink-2)",
                display: "-webkit-box",
                WebkitLineClamp: 1,
                WebkitBoxOrient: "vertical",
                overflow: "hidden",
              }}
            >
              {payload.description || t("noDescription")}
            </p>
            <div className="lv-t-meta" style={{ color: "var(--lv-ink-3)" }}>
              {[payload.genre, payload.era, "★".repeat(payload.difficulty), payload.estimated_time]
                .filter(Boolean)
                .join(" · ")}
            </div>
          </div>
        </article>
      </PreviewBlock>

      <PreviewBlock caps={t("detailCaps")}>
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: "var(--lv-s-4)",
            background: "var(--lv-bg-1)",
            border: "1px solid var(--lv-line)",
            borderRadius: "var(--lv-r-card)",
            padding: "var(--lv-s-4)",
          }}
        >
          <PreviewCover
            src={payload.hero_image ?? payload.cover_image}
            ratio="21/9"
            alt={payload.name || t("untitledWorld")}
          />
          <h2 className="lv-t-h2" style={{ margin: 0, color: "var(--lv-ink)" }}>
            {payload.name || t("untitledWorld")}
          </h2>
          {payload.description && (
            <p
              className="lv-t-body-long"
              style={{ margin: 0, color: "var(--lv-ink-2)" }}
            >
              {payload.description}
            </p>
          )}
          {payload.base_setting && (
            <p
              className="lv-t-meta"
              style={{
                margin: 0,
                color: "var(--lv-ink-3)",
                display: "-webkit-box",
                WebkitLineClamp: 4,
                WebkitBoxOrient: "vertical",
                overflow: "hidden",
              }}
            >
              {payload.base_setting}
            </p>
          )}
        </div>
      </PreviewBlock>

      <PreviewBlock caps={t("characterCount", { n: playable.length })}>
        {playable.length === 0 ? (
          <PreviewEmpty>{t("noCharacters")}</PreviewEmpty>
        ) : (
          <ul style={{ display: "flex", flexDirection: "column", gap: "var(--lv-s-2)", margin: 0, padding: 0, listStyle: "none" }}>
            {playable.map((c, i) => (
              <li
                key={`p-${i}`}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "var(--lv-s-3)",
                  padding: "var(--lv-s-2) var(--lv-s-3)",
                  background: "var(--lv-bg-1)",
                  border: "1px solid var(--lv-line)",
                  borderRadius: "var(--lv-r-card)",
                }}
              >
                <Avatar src={c.avatar} name={c.name} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div className="lv-t-body" style={{ color: "var(--lv-ink)" }}>
                    {c.name || "—"}
                  </div>
                  {c.description && (
                    <div
                      className="lv-t-meta"
                      style={{
                        color: "var(--lv-ink-3)",
                        whiteSpace: "nowrap",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                      }}
                    >
                      {c.description}
                    </div>
                  )}
                </div>
              </li>
            ))}
            {npcs.length > 0 && (
              <li
                className="lv-t-meta"
                style={{ color: "var(--lv-ink-4)", padding: "var(--lv-s-2) var(--lv-s-3)" }}
              >
                + {npcs.length} NPC
              </li>
            )}
          </ul>
        )}
      </PreviewBlock>

      <PreviewBlock caps={t("locationCount", { n: payload.locations.length })}>
        {payload.locations.length === 0 ? (
          <PreviewEmpty>{t("noLocations")}</PreviewEmpty>
        ) : (
          <ul style={{ display: "flex", flexWrap: "wrap", gap: 6, margin: 0, padding: 0, listStyle: "none" }}>
            {payload.locations.slice(0, 16).map((l, i) => (
              <li
                key={`l-${i}`}
                className="lv-t-meta"
                style={{
                  padding: "4px 10px",
                  border: "1px solid var(--lv-line)",
                  borderRadius: "var(--lv-r-pill)",
                  color: "var(--lv-ink-2)",
                }}
              >
                {l.name || "—"}
              </li>
            ))}
            {payload.locations.length > 16 && (
              <li className="lv-t-meta" style={{ padding: "4px 10px", color: "var(--lv-ink-4)" }}>
                +{payload.locations.length - 16}
              </li>
            )}
          </ul>
        )}
      </PreviewBlock>
    </div>
  );
}

function Avatar({ src, name }: { src?: string | null; name: string }) {
  return (
    <div
      style={{
        width: 36,
        height: 36,
        borderRadius: "50%",
        flexShrink: 0,
        background: "var(--lv-bg-2)",
        border: "1px solid var(--lv-line)",
        overflow: "hidden",
        display: "grid",
        placeItems: "center",
      }}
    >
      {src ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={src} alt={name} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
      ) : (
        <span className="lv-t-caps" style={{ color: "var(--lv-ink-4)" }}>
          {name ? name.slice(0, 1) : "?"}
        </span>
      )}
    </div>
  );
}
