"use client";

import { motion } from "motion/react";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { lvFadeUp, lvStaggerContainer } from "@/lib/motion";
import type {
  AdminScriptListResponse,
  AdminWorldPublishedItem,
} from "@/lib/types";

import { ScriptCard } from "./ScriptCard";

type Filter = "all" | "published" | "draft";

interface WorkshopScriptsPanelProps {
  worlds: AdminWorldPublishedItem[];
  hasAnyPublishedWorld: boolean;
  selectedWorldId: string | null;
  onSelectWorld: (id: string) => void;
  data: AdminScriptListResponse | null;
  loading: boolean;
  busyId: string | null;
  onOpenScript: (id: string) => void;
  onOpenDraft: (id: string) => void;
  onDeleteScript?: (id: string) => void;
  onDeleteDraft?: (id: string) => void;
  onCreateNew?: () => void;
  onSwitchToWorlds: () => void;
}

export function WorkshopScriptsPanel({
  worlds,
  hasAnyPublishedWorld,
  selectedWorldId,
  onSelectWorld,
  data,
  loading,
  busyId,
  onOpenScript,
  onOpenDraft,
  onDeleteScript,
  onDeleteDraft,
  onCreateNew,
  onSwitchToWorlds,
}: WorkshopScriptsPanelProps) {
  const t = useTranslations("admin.workshop");
  const [filter, setFilter] = useState<Filter>("all");

  if (!hasAnyPublishedWorld) {
    return (
      <div className="workshop-shell">
        <div className="workshop-empty">
          <span className="lv-t-h3">{t("scripts.needWorldTitle")}</span>
          <span className="lv-t-meta">{t("scripts.needWorldHint")}</span>
        </div>
      </div>
    );
  }

  if (worlds.length === 0) {
    return (
      <div className="workshop-shell">
        <div className="workshop-empty">
          <span className="lv-t-h3">{t("scripts.noScriptsTitle")}</span>
          <span className="lv-t-meta">{t("scripts.noScriptsHint")}</span>
          <button
            type="button"
            className="workshop-cta"
            onClick={onSwitchToWorlds}
          >
            <span>{t("scripts.noScriptsCta")}</span>
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="workshop-shell">
      <motion.nav
        className="workshop-pillbar"
        variants={lvFadeUp}
        initial="hidden"
        animate="show"
        aria-label={t("scripts.selectWorld")}
      >
        {worlds.map((w) => (
          <button
            key={w.id}
            type="button"
            className="workshop-pill"
            aria-pressed={selectedWorldId === w.id}
            onClick={() => onSelectWorld(w.id)}
          >
            <span>{w.name}</span>
            <span className="workshop-pill-count">{w.script_count}</span>
          </button>
        ))}
      </motion.nav>

      <ScriptsBody
        data={data}
        loading={loading}
        busyId={busyId}
        filter={filter}
        onFilterChange={setFilter}
        onOpenScript={onOpenScript}
        onOpenDraft={onOpenDraft}
        onDeleteScript={onDeleteScript}
        onDeleteDraft={onDeleteDraft}
        onCreateNew={onCreateNew}
        worldName={
          worlds.find((x) => x.id === selectedWorldId)?.name ?? ""
        }
      />
    </div>
  );
}

interface ScriptsBodyProps {
  data: AdminScriptListResponse | null;
  loading: boolean;
  busyId: string | null;
  filter: Filter;
  onFilterChange: (f: Filter) => void;
  onOpenScript: (id: string) => void;
  onOpenDraft: (id: string) => void;
  onDeleteScript?: (id: string) => void;
  onDeleteDraft?: (id: string) => void;
  onCreateNew?: () => void;
  worldName: string;
}

function ScriptsBody({
  data,
  loading,
  busyId,
  filter,
  onFilterChange,
  onOpenScript,
  onOpenDraft,
  onDeleteScript,
  onDeleteDraft,
  onCreateNew,
  worldName,
}: ScriptsBodyProps) {
  const t = useTranslations("admin.workshop");

  if (loading) {
    return <ScriptsSkeleton />;
  }

  const drafts = data?.drafts ?? [];
  const published = data?.published ?? [];
  const totalCount = drafts.length + published.length;

  if (totalCount === 0) {
    return (
      <div className="workshop-empty">
        <span className="lv-t-h3">{t("scripts.emptyTitle")}</span>
        <span className="lv-t-meta">{t("scripts.emptyHint")}</span>
        {onCreateNew && (
          <button type="button" className="workshop-cta" onClick={onCreateNew}>
            <span className="workshop-cta-plus" aria-hidden>+</span>
            <span>{t("scripts.emptyCta")}</span>
          </button>
        )}
      </div>
    );
  }

  const showPublished = filter === "all" || filter === "published";
  const showDrafts = filter === "all" || filter === "draft";

  return (
    <>
      <motion.div
        className="workshop-toolbar"
        variants={lvFadeUp}
        initial="hidden"
        animate="show"
      >
        <div className="workshop-toolbar-left">
          <span className="lv-t-caps">
            {t("scripts.captionWith", { worldName })}
          </span>
          <span className="lv-t-meta workshop-toolbar-count">
            {t("scripts.count", {
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
              onClick={() => onFilterChange(key)}
            >
              {t(`filters.${key}`)}
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
            <ScriptCard
              key={`draft-${d.id}`}
              kind="draft"
              draft={d}
              onClick={() => onOpenDraft(d.id)}
              onDelete={onDeleteDraft ? () => onDeleteDraft(d.id) : undefined}
            />
          ))}
        {showPublished &&
          published.map((s) => (
            <ScriptCard
              key={`script-${s.id}`}
              kind="published"
              script={s}
              busy={busyId === s.id}
              onClick={() => onOpenScript(s.id)}
              onDelete={onDeleteScript ? () => onDeleteScript(s.id) : undefined}
            />
          ))}
      </motion.div>
    </>
  );
}

function ScriptsSkeleton() {
  return (
    <div className="workshop-grid">
      {Array.from({ length: 4 }).map((_, i) => (
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
            style={{ height: 18, width: "60%", borderRadius: "var(--lv-r-pill)" }}
          />
          <div
            className="lv-skel"
            style={{ height: 12, width: "45%", borderRadius: "var(--lv-r-pill)" }}
          />
        </div>
      ))}
    </div>
  );
}
