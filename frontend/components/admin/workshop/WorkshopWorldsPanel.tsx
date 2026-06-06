"use client";

import { motion } from "motion/react";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { lvFadeUp, lvStaggerContainer } from "@/lib/motion";
import type { AdminWorldListResponse } from "@/lib/types";

import { WorldCard } from "./WorldCard";

type Filter = "all" | "published" | "draft";

interface WorkshopWorldsPanelProps {
  data: AdminWorldListResponse | null;
  loading: boolean;
  busyId: string | null;
  onOpenWorld: (id: string) => void;
  onOpenDraft: (id: string) => void;
  onDeleteWorld?: (id: string) => void;
  onDeleteDraft?: (id: string) => void;
  onCreateNew?: () => void;
}

export function WorkshopWorldsPanel({
  data,
  loading,
  busyId,
  onOpenWorld,
  onOpenDraft,
  onDeleteWorld,
  onDeleteDraft,
  onCreateNew,
}: WorkshopWorldsPanelProps) {
  const t = useTranslations("admin.workshop");
  const [filter, setFilter] = useState<Filter>("all");

  if (loading) {
    return (
      <div className="workshop-shell">
        <WorldsSkeleton />
      </div>
    );
  }

  const drafts = data?.drafts ?? [];
  const published = data?.published ?? [];
  const totalCount = drafts.length + published.length;

  if (totalCount === 0) {
    return (
      <div className="workshop-shell">
        <div className="workshop-empty">
          <span className="lv-t-h3">{t("worlds.emptyTitle")}</span>
          <span className="lv-t-meta">{t("worlds.emptyHint")}</span>
          {onCreateNew && (
            <button type="button" className="workshop-cta" onClick={onCreateNew}>
              <span className="workshop-cta-plus" aria-hidden>+</span>
              <span>{t("worlds.emptyCta")}</span>
            </button>
          )}
        </div>
      </div>
    );
  }

  const showPublished = filter === "all" || filter === "published";
  const showDrafts = filter === "all" || filter === "draft";

  return (
    <div className="workshop-shell">
      <motion.div
        className="workshop-toolbar"
        variants={lvFadeUp}
        initial="hidden"
        animate="show"
      >
        <div className="workshop-toolbar-left">
          <span className="lv-t-caps">{t("worlds.captionAll")}</span>
          <span className="lv-t-meta workshop-toolbar-count">
            {t("worlds.count", {
              total: published.length,
              drafts: drafts.length,
            })}
          </span>
        </div>
        <div
          className="workshop-filters"
          role="group"
          aria-label={t("filters.all")}
        >
          {(["all", "published", "draft"] as const).map((key) => (
            <button
              key={key}
              type="button"
              className="workshop-chip"
              aria-pressed={filter === key}
              onClick={() => setFilter(key)}
            >
              {t(`filters.${key === "all" ? "all" : key}`)}
            </button>
          ))}
        </div>
      </motion.div>

      <motion.div
        className="workshop-grid"
        variants={lvStaggerContainer}
        initial="hidden"
        animate="show"
        key={filter}
      >
        {showDrafts &&
          drafts.map((d) => (
            <WorldCard
              key={`draft-${d.id}`}
              kind="draft"
              draft={d}
              onClick={() => onOpenDraft(d.id)}
              onDelete={onDeleteDraft ? () => onDeleteDraft(d.id) : undefined}
            />
          ))}
        {showPublished &&
          published.map((w) => (
            <WorldCard
              key={`world-${w.id}`}
              kind="published"
              world={w}
              scriptCount={w.script_count}
              busy={busyId === w.id}
              onClick={() => onOpenWorld(w.id)}
              onDelete={onDeleteWorld ? () => onDeleteWorld(w.id) : undefined}
            />
          ))}
      </motion.div>
    </div>
  );
}

function WorldsSkeleton() {
  return (
    <div className="workshop-grid">
      {Array.from({ length: 8 }).map((_, i) => (
        <div key={i} className="workshop-card">
          <div
            className="lv-skel"
            style={{
              aspectRatio: "3 / 2",
              borderRadius: "var(--lv-r-card)",
            }}
          />
          <div
            className="lv-skel"
            style={{
              height: 18,
              width: "60%",
              borderRadius: "var(--lv-r-pill)",
            }}
          />
          <div
            className="lv-skel"
            style={{
              height: 12,
              width: "45%",
              borderRadius: "var(--lv-r-pill)",
            }}
          />
        </div>
      ))}
    </div>
  );
}
