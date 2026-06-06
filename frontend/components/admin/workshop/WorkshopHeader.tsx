"use client";

import { motion } from "motion/react";
import { useTranslations } from "next-intl";

import { lvFadeUp } from "@/lib/motion";

export type WorkshopTab = "worlds" | "scripts" | "models";

interface WorkshopHeaderProps {
  activeTab: WorkshopTab;
  onTabChange: (tab: WorkshopTab) => void;
  onCtaClick?: () => void;
  ctaDisabled?: boolean;
  showModels?: boolean;
}

const CTA_KEY: Record<WorkshopTab, "world" | "script" | "model"> = {
  worlds: "world",
  scripts: "script",
  models: "model",
};

export function WorkshopHeader({
  activeTab,
  onTabChange,
  onCtaClick,
  ctaDisabled,
  showModels = true,
}: WorkshopHeaderProps) {
  const t = useTranslations("admin.workshop");
  const tabs: WorkshopTab[] = showModels
    ? ["worlds", "scripts", "models"]
    : ["worlds", "scripts"];

  return (
    <header className="workshop-header">
      <div className="workshop-shell">
        <motion.div
          className="workshop-header-row"
          variants={lvFadeUp}
          initial="hidden"
          animate="show"
        >
          <div>
            <span className="lv-t-caps workshop-eyebrow">{t("eyebrow")}</span>
            <h1 className="lv-t-h1">{t("title")}</h1>
          </div>
          {onCtaClick ? (
            <button
              type="button"
              className="workshop-cta"
              onClick={onCtaClick}
              disabled={ctaDisabled}
            >
              <span className="workshop-cta-plus" aria-hidden>+</span>
              <span>{t(`cta.${CTA_KEY[activeTab]}`)}</span>
            </button>
          ) : null}
        </motion.div>
        <nav className="workshop-tabs" role="tablist" aria-label={t("title")}>
          {tabs.map((key) => (
            <button
              key={key}
              type="button"
              role="tab"
              className="workshop-tab"
              aria-selected={activeTab === key}
              onClick={() => onTabChange(key)}
            >
              {t(`tabs.${key}`)}
            </button>
          ))}
        </nav>
      </div>
    </header>
  );
}
