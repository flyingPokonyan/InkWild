"use client";

import { motion } from "motion/react";
import { useTranslations } from "next-intl";
import type { KeyboardEvent } from "react";

import { lvStaggerItem } from "@/lib/motion";
import type {
  AdminScriptDraftListItem,
  AdminScriptPublishedItem,
} from "@/lib/types";

import { ScriptCoverFallback } from "./ScriptCoverFallback";
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
  script: AdminScriptPublishedItem;
  coverImage?: string | null;
  busy?: boolean;
  onClick: () => void;
  onDelete?: () => void;
}

interface DraftProps {
  kind: "draft";
  draft: AdminScriptDraftListItem;
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

export function ScriptCard(props: PublishedProps | DraftProps) {
  const t = useTranslations("admin.workshop.card");

  if (props.kind === "draft") {
    const status = resolveDraftStatus(props.draft.generation_status);
    const statusLabelKey =
      status === "generating"
        ? "statusGenerating"
        : status === "failed"
          ? "statusFailed"
          : "statusDraft";
    const draftName = props.draft.name || t("untitled");

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
          className="workshop-cover is-published"
          aria-label={t(statusLabelKey)}
        >
          <ScriptCoverFallback name={draftName} />
          {status === "generating" && (
            <div
              className="workshop-draft-skel lv-skel"
              aria-hidden
              style={{ position: "absolute", inset: 0 }}
            />
          )}
          <span className={`workshop-status is-${status}`}>
            {t(statusLabelKey)}
          </span>
          {props.onDelete && (
            <WorkshopCardDeleteButton onDelete={props.onDelete} label={draftName} />
          )}
        </div>
        <div className="workshop-card-body">
          <h3 className="lv-t-h3 workshop-card-title">{draftName}</h3>
        </div>
      </motion.div>
    );
  }

  const s = props.script;
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
        {props.coverImage ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            className="workshop-cover-img"
            src={props.coverImage}
            alt={s.name}
            loading="lazy"
          />
        ) : (
          <ScriptCoverFallback
            name={s.name}
            difficulty={s.difficulty}
            estimatedTime={s.estimated_time}
          />
        )}
        {props.onDelete && (
          <WorkshopCardDeleteButton onDelete={props.onDelete} label={s.name} />
        )}
      </div>
      <div className="workshop-card-body">
        <h3 className="lv-t-h3 workshop-card-title">{s.name}</h3>
        {s.description ? (
          <div
            className="workshop-card-meta lv-t-meta"
            style={{
              display: "-webkit-box",
              WebkitBoxOrient: "vertical",
              WebkitLineClamp: 1,
              overflow: "hidden",
            }}
          >
            <span>{s.description}</span>
          </div>
        ) : null}
      </div>
    </motion.div>
  );
}
