"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { ChevronLeft } from "lucide-react";

import type { AutosaveState } from "./hooks/use-autosave";

interface DraftStripProps {
  kind: "world" | "script";
  title: string;
  /** 模式编码字符（◆ 剧本 / ◇ 自由），仅 script 页传入 */
  modeGlyph?: "◆" | "◇";
  /** 返回链接目标，默认 "/workshop" */
  backTo?: string;
  state: AutosaveState;
  saving: boolean;
  publishing: boolean;
  discarding: boolean;
  isDirty: boolean;
  onManualSave: () => void;
  onPublish: () => void;
  onDiscard: () => void;
  /** Optional intercept for the back link. Return true to swallow navigation
   * (e.g. to show a "unsaved changes" confirm dialog). */
  onBackAttempt?: () => boolean;
}

/**
 * 顶端 sticky masthead：模式徽 + 标题 + 自动保存指示 + 操作。
 * 视觉位列在编辑器最上方，56px 高，仅 1px hairline 收边，无 blur 无 glow。
 */
export function DraftStrip({
  kind,
  title,
  modeGlyph,
  backTo = "/workshop",
  state,
  saving,
  publishing,
  discarding,
  isDirty,
  onManualSave,
  onPublish,
  onDiscard,
  onBackAttempt,
}: DraftStripProps) {
  const t = useTranslations("admin.editor");
  const kindLabel = kind === "world" ? t("kindWorld") : t("kindScript");
  const glyphColor =
    modeGlyph === "◆"
      ? "var(--lv-accent)"
      : modeGlyph === "◇"
        ? "var(--lv-accent-2)"
        : undefined;

  return (
    <div
      className="lv-editor-strip"
      style={{
        position: "sticky",
        top: 0,
        zIndex: "var(--lv-z-sticky)" as unknown as number,
        background: "rgba(8,8,10,0.96)",
        borderBottom: "1px solid var(--lv-line)",
      }}
    >
      <div
        className="lv-editor-strip-inner"
        style={{
          display: "flex",
          alignItems: "center",
          gap: "var(--lv-s-4)",
          padding: "var(--lv-s-3) var(--lv-pad-x)",
          maxWidth: "var(--lv-max-w)",
          margin: "0 auto",
          minHeight: 56,
        }}
      >
        <Link
          href={backTo}
          onClick={(e) => {
            if (onBackAttempt?.()) {
              e.preventDefault();
            }
          }}
          className="lv-t-meta"
          aria-label={t("back")}
          style={{
            color: "var(--lv-ink-3)",
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            gap: "var(--lv-s-2)",
            minWidth: 44,
            minHeight: 44,
            paddingLeft: 0,
            paddingRight: 0,
            textDecoration: "none",
          }}
        >
          <ChevronLeft size={18} strokeWidth={1.75} aria-hidden />
          <span className="lv-editor-strip-back-label">{t("back")}</span>
        </Link>

        <span
          className="lv-editor-strip-divider"
          aria-hidden
          style={{ width: 1, height: 24, background: "var(--lv-line)", flexShrink: 0 }}
        />

        <div className="lv-editor-strip-title">
          <span className="lv-t-caps" style={{ color: "var(--lv-ink-3)" }}>
            {kindLabel} · {t("draftLabel")}
          </span>

          <div className="lv-editor-strip-heading">
            {modeGlyph && (
              <span
                className="lv-t-body lv-editor-strip-glyph"
                style={{ color: glyphColor }}
                aria-hidden
              >
                {modeGlyph}
              </span>
            )}

            <h1
              className="lv-t-h3"
              style={{
                margin: 0,
                color: "var(--lv-ink)",
                minWidth: 0,
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
              title={title}
            >
              {title}
            </h1>
          </div>
        </div>

        <SaveIndicator state={state} />

        <div
          className="lv-editor-strip-actions"
          style={{
            display: "flex",
            gap: "var(--lv-s-2)",
            alignItems: "center",
            flexShrink: 0,
          }}
        >
          <button
            type="button"
            onClick={onDiscard}
            disabled={discarding}
            className="lv-btn lv-btn-sm"
            style={{
              color: "var(--lv-ink-3)",
              borderColor: "var(--lv-line)",
            }}
          >
            {discarding ? t("discarding") : t("discard")}
          </button>
          <button
            type="button"
            onClick={onManualSave}
            disabled={saving || (!isDirty && state.status !== "error")}
            className="lv-btn lv-btn-sm"
          >
            {saving ? t("saving") : t("manualSave")}
          </button>
          <button
            type="button"
            onClick={onPublish}
            disabled={publishing}
            className="lv-btn lv-btn-primary lv-btn-sm"
          >
            {publishing ? t("publishing") : t("publish")}
          </button>
        </div>
      </div>
      <style jsx>{`
        .lv-editor-strip {
          -webkit-backdrop-filter: saturate(120%);
          backdrop-filter: saturate(120%);
        }

        .lv-editor-strip-title {
          display: flex;
          flex: 1;
          min-width: 0;
          flex-direction: row;
          align-items: center;
          gap: var(--lv-s-3);
        }

        .lv-editor-strip-heading {
          display: flex;
          min-width: 0;
          align-items: center;
          gap: var(--lv-s-2);
        }

        .lv-editor-strip-glyph {
          line-height: 1;
          flex-shrink: 0;
        }

        @media (max-width: 767px) {
          .lv-editor-strip-inner {
            min-height: 68px !important;
            gap: var(--lv-s-2) !important;
            padding: var(--lv-s-2) var(--lv-pad-x) !important;
          }

          .lv-editor-strip-back-label,
          .lv-editor-strip-divider,
          .lv-editor-strip-actions {
            display: none !important;
          }

          .lv-editor-strip-title {
            flex-direction: column;
            align-items: flex-start;
            gap: 2px;
          }

          .lv-editor-strip-heading {
            width: 100%;
          }

          .lv-editor-strip-heading h1 {
            max-width: 100%;
          }
        }
      `}</style>
    </div>
  );
}

function SaveIndicator({ state }: { state: AutosaveState }) {
  const t = useTranslations("admin.editor");
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (state.lastSavedAt === null) return;
    const id = setInterval(() => setNow(Date.now()), 30_000);
    return () => clearInterval(id);
  }, [state.lastSavedAt]);

  const dotColor = (() => {
    switch (state.status) {
      case "saving":
      case "dirty":
        return "var(--lv-accent)";
      case "error":
        return "var(--lv-danger)";
      case "saved":
      case "idle":
      default:
        return "var(--lv-ink-4)";
    }
  })();

  const label = (() => {
    switch (state.status) {
      case "saving":
        return t("saving");
      case "dirty":
        return t("dirty");
      case "error":
        return t("saveError");
      case "saved":
      case "idle":
      default:
        if (!state.lastSavedAt) return null;
        return t("saved", { time: relativeTime(now, state.lastSavedAt) });
    }
  })();

  if (!label) return null;

  return (
    <div
      className="lv-editor-save-indicator"
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "var(--lv-s-2)",
        flexShrink: 0,
      }}
    >
      <span
        className={state.status === "saving" || state.status === "dirty" ? "lv-loading-pulse" : ""}
        aria-hidden
        style={{
          display: "inline-block",
          width: 8,
          height: 8,
          borderRadius: "50%",
          background: dotColor,
        }}
      />
      <span className="lv-t-meta lv-editor-save-label" style={{ color: "var(--lv-ink-3)" }}>
        {label}
      </span>
      <style jsx>{`
        @media (max-width: 767px) {
          .lv-editor-save-indicator {
            gap: 0 !important;
          }

          .lv-editor-save-label {
            display: none !important;
          }
        }
      `}</style>
    </div>
  );
}

function relativeTime(nowMs: number, then: Date): string {
  const diff = Math.floor((nowMs - then.getTime()) / 1000);
  if (diff < 30) return "刚刚";
  if (diff < 60) return `${diff} 秒前`;
  if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`;
  return then.toLocaleString("zh-CN");
}
