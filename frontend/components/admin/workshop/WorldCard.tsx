"use client";

import { motion } from "motion/react";
import { useTranslations } from "next-intl";
import type { KeyboardEvent } from "react";

import { lvStaggerItem } from "@/lib/motion";
import type {
  AdminWorldDraftListItem,
  AdminWorldPublishedItem,
} from "@/lib/types";

import { WorkshopCardDeleteButton } from "./WorkshopCardDeleteButton";

type DraftStatus = "static" | "generating" | "failed";

function resolveDraftStatus(generationStatus?: string | null): DraftStatus {
  if (generationStatus === "pending" || generationStatus === "running") {
    return "generating";
  }
  if (generationStatus === "failed") return "failed";
  return "static";
}

interface PublishedProps {
  kind: "published";
  world: AdminWorldPublishedItem;
  scriptCount: number;
  busy?: boolean;
  onClick: () => void;
  onDelete?: () => void;
}

interface DraftProps {
  kind: "draft";
  draft: AdminWorldDraftListItem;
  onClick: () => void;
  onDelete?: () => void;
}

function handleActivate(
  e: KeyboardEvent<HTMLDivElement>,
  cb: () => void,
): void {
  if (e.key === "Enter" || e.key === " ") {
    e.preventDefault();
    cb();
  }
}

export function WorldCard(props: PublishedProps | DraftProps) {
  const t = useTranslations("admin.workshop.card");
  const tWorlds = useTranslations("admin.workshop.worlds");

  if (props.kind === "draft") {
    const status = resolveDraftStatus(props.draft.generation_status);
    const captionKey =
      status === "generating"
        ? "coverGenerating"
        : status === "failed"
          ? "coverFailed"
          : "coverPending";

    const statusLabelKey =
      status === "generating"
        ? "statusGenerating"
        : status === "failed"
          ? "statusFailed"
          : "statusDraft";

    return (
      <motion.div
        role="button"
        tabIndex={0}
        variants={lvStaggerItem}
        className="workshop-card"
        onClick={props.onClick}
        onKeyDown={(e) => handleActivate(e, props.onClick)}
      >
        <div
          className={`workshop-cover is-draft is-${status}`}
          aria-label={t(statusLabelKey)}
        >
          {status === "generating" ? (
            <div className="workshop-draft-skel lv-skel" aria-hidden />
          ) : props.draft.cover_image ? (
            // 草稿已有封面图 → 直接展示（之前只显示占位符，封面被埋没）
            <img
              className="workshop-cover-img"
              src={props.draft.cover_image}
              alt={props.draft.name || t("untitled")}
              loading="lazy"
            />
          ) : (
            <div className="workshop-draft-mark">
              <span className="workshop-draft-mark-icon" aria-hidden>
                {status === "failed" ? "!" : "+"}
              </span>
              <span className="lv-t-caps">{t(captionKey)}</span>
            </div>
          )}
          <span className={`workshop-status is-${status}`}>
            {t(statusLabelKey)}
          </span>
          {props.onDelete && (
            <WorkshopCardDeleteButton
              onDelete={props.onDelete}
              label={props.draft.name || t("untitled")}
            />
          )}
        </div>
        <div className="workshop-card-body">
          <h3 className="lv-t-h3 workshop-card-title">
            {props.draft.name || t("untitled")}
          </h3>
        </div>
      </motion.div>
    );
  }

  const w = props.world;
  return (
    <motion.div
      role="button"
      tabIndex={0}
      variants={lvStaggerItem}
      className="workshop-card"
      onClick={props.busy ? undefined : props.onClick}
      onKeyDown={(e) => !props.busy && handleActivate(e, props.onClick)}
      aria-disabled={props.busy ? true : undefined}
    >
      <div className="workshop-cover is-published">
        {w.cover_image ? (
          <img
            className="workshop-cover-img"
            src={w.cover_image}
            alt={w.name}
            loading="lazy"
          />
        ) : null}
        {props.onDelete && (
          <WorkshopCardDeleteButton
            onDelete={props.onDelete}
            label={w.name}
          />
        )}
      </div>
      <div className="workshop-card-body">
        <h3 className="lv-t-h3 workshop-card-title">{w.name}</h3>
        <div className="workshop-card-meta lv-t-meta">
          {w.genre ? <span>{w.genre}</span> : null}
          {w.genre ? <span className="workshop-card-meta-sep">·</span> : null}
          <span>{tWorlds("scriptCount", { count: props.scriptCount })}</span>
        </div>
      </div>
    </motion.div>
  );
}
