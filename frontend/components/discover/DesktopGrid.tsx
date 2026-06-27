"use client";

import { useTranslations } from "next-intl";

import type { WorldListItem } from "@/lib/types";
import { DesktopProductCard } from "./DesktopProductCard";

export function DesktopGrid({
  mode,
  query,
  activeCategory,
  worlds,
}: {
  mode: "search" | "category";
  query: string;
  activeCategory: string;
  worlds: WorldListItem[];
}) {
  const t = useTranslations("discoverPage");

  const title =
    mode === "search"
      ? t("searchResults", { query })
      : activeCategory === "剧本"
        ? t("featuredScripts")
        : t("categoryGridTitle", { category: activeCategory });

  const emptyText =
    mode === "search" ? t("noSearchResults") : t("noCategoryContent");

  return (
    <div className={`product-grid-section ${mode === "search" ? "search-grid-section" : "category-grid-section"}`}>
      <h2>{title}</h2>
      <div className="product-grid">
        {worlds.length > 0 ? (
          worlds.map((w) => <DesktopProductCard key={w.id} world={w} />)
        ) : (
          <p className="empty-state">{emptyText}</p>
        )}
      </div>
    </div>
  );
}
