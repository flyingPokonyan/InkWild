"use client";

import Link from "next/link";
import { useMemo } from "react";
import { motion } from "motion/react";
import { Play, Flame, Sparkles, BookOpen } from "lucide-react";
import { useTranslations } from "next-intl";

import { pickFeaturedWorlds } from "@/lib/featured-worlds";
import type { GameHistoryItem, WorldListItem } from "@/lib/types";
import {
  excludeWorldIds,
  idsOf,
  takeRowWorlds,
  worldCompletenessScore,
  worldHotScore,
} from "./world-ranking";
import { DesktopSpotlight } from "./DesktopSpotlight";
import { DesktopCarouselRow } from "./DesktopCarouselRow";
import { DesktopCategoryBar } from "./DesktopCategoryBar";
import { DesktopGrid } from "./DesktopGrid";
import { ContinueSaveCard } from "./ContinueSaveCard";

export interface DesktopViewProps {
  worlds: WorldListItem[];
  activeCategory: string;
  query: string;
  isSearchMode: boolean;
  isCategoryMode: boolean;
  isGridMode: boolean;
  filteredGridWorlds: WorldListItem[];
  activeSaves: GameHistoryItem[];
  isLoggedIn: boolean;
  onCategoryClick: (cat: string) => void;
}

export function DesktopView({
  worlds,
  activeCategory,
  query,
  isSearchMode,
  isCategoryMode,
  isGridMode,
  filteredGridWorlds,
  activeSaves,
  isLoggedIn,
  onCategoryClick,
}: DesktopViewProps) {
  const t = useTranslations("discoverPage");

  const spotlightWorlds = useMemo(() => pickFeaturedWorlds(worlds, 4), [worlds]);
  const featured = useMemo(() => pickFeaturedWorlds(worlds, 16), [worlds]);
  const hero = spotlightWorlds[0] ?? featured[0] ?? worlds[0];

  const rankedWorlds = useMemo(
    () => [...worlds].sort((a, b) => worldCompletenessScore(b) - worldCompletenessScore(a)),
    [worlds],
  );
  const hotRankedWorlds = useMemo(
    () => [...worlds].sort((a, b) => worldHotScore(b) - worldHotScore(a)),
    [worlds],
  );

  const popularWorlds = useMemo(
    () => takeRowWorlds(hotRankedWorlds.filter((w) => w.id !== hero?.id), featured, 8),
    [featured, hero?.id, hotRankedWorlds],
  );
  const popularIds = useMemo(() => idsOf(popularWorlds, [hero?.id]), [hero?.id, popularWorlds]);
  const featuredWorlds = useMemo(
    () => takeRowWorlds(excludeWorldIds(featured, popularIds), rankedWorlds, 8),
    [featured, popularIds, rankedWorlds],
  );
  const shelfIds = useMemo(
    () => idsOf([...popularWorlds, ...featuredWorlds], [hero?.id]),
    [featuredWorlds, hero?.id, popularWorlds],
  );
  const scriptWorlds = useMemo(
    () =>
      takeRowWorlds(
        excludeWorldIds(rankedWorlds.filter((w) => w.has_script), shelfIds),
        rankedWorlds.filter((w) => w.has_script),
        8,
      ),
    [rankedWorlds, shelfIds],
  );

  return (
    <>
      <div className="product-atmosphere" aria-hidden />

      {!isGridMode && spotlightWorlds.length > 0 && (
        <DesktopSpotlight worlds={spotlightWorlds} />
      )}

      <div className="product-content-container">
        <DesktopCategoryBar active={activeCategory} onClick={onCategoryClick} />

        {isSearchMode ? (
          <DesktopGrid mode="search" query={query} activeCategory={activeCategory} worlds={filteredGridWorlds} />
        ) : isCategoryMode ? (
          <DesktopGrid mode="category" query={query} activeCategory={activeCategory} worlds={filteredGridWorlds} />
        ) : (
          <>
            {isLoggedIn && activeSaves.length > 0 && (
              <motion.section
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.6, delay: 0.1 }}
                style={{ padding: "0 clamp(20px, 4vw, 60px)", marginBottom: "36px", maxWidth: "1440px", margin: "0 auto 36px" }}
              >
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    marginBottom: "18px",
                  }}
                >
                  <h2
                    style={{
                      fontFamily: "var(--lv-font-serif)",
                      fontSize: "var(--lv-t-h2)",
                      fontWeight: 600,
                      color: "var(--lv-ink)",
                      display: "flex",
                      alignItems: "center",
                      gap: "10px",
                    }}
                  >
                    <span
                      style={{
                        width: 4,
                        height: 16,
                        background: "var(--lv-ink)",
                        borderRadius: 2,
                        display: "inline-block",
                      }}
                    />
                    {t("continueTitle")}
                  </h2>
                  <Link
                    href="/history"
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      gap: "4px",
                      color: "var(--lv-ink-3)",
                      fontSize: "13px",
                      textDecoration: "none",
                      transition: "color 0.25s ease",
                    }}
                    className="hover-accent-link"
                  >
                    {t("viewAll")} <Play size={10} style={{ transform: "rotate(-45deg)" }} />
                  </Link>
                </div>

                <div
                  style={{
                    display: "flex",
                    gap: "18px",
                    overflowX: "auto",
                    paddingBottom: "10px",
                    scrollbarWidth: "none",
                  }}
                  className="carousel-track"
                >
                  {activeSaves.map((save) => (
                    <ContinueSaveCard key={save.session_id} save={save} />
                  ))}
                </div>
              </motion.section>
            )}

            <div className="product-carousels-section">
              <DesktopCarouselRow title={t("hotExplore")} icon={Flame} worlds={popularWorlds} />
              <DesktopCarouselRow title={t("featuredWorlds")} icon={Sparkles} worlds={featuredWorlds} />
              <DesktopCarouselRow title={t("featuredScripts")} icon={BookOpen} worlds={scriptWorlds} />
            </div>
          </>
        )}
      </div>
    </>
  );
}
