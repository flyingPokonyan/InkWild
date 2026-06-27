"use client";

import { useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";

import { ProductNav } from "@/components/ProductNav";
import { useWorldList } from "@/lib/api/worlds";
import { useGameHistory } from "@/lib/api/history";
import { pickFeaturedWorlds } from "@/lib/featured-worlds";
import { useAuthStore } from "@/stores/auth";
import type { WorldListItem } from "@/lib/types";

import { readUrlState, writeUrlState } from "@/components/discover/url-state";
import { DesktopView } from "@/components/discover/DesktopView";
import { MobileView } from "@/components/discover/MobileView";

export default function DiscoverPage() {
  const t = useTranslations("discoverPage");
  const user = useAuthStore((s) => s.user);

  // ── URL-synced state ──
  const [query, setQuery] = useState("");
  const [activeCategory, setActiveCategory] = useState("全部");

  // ── Data ──
  const { data: worldsData } = useWorldList();
  const worlds = useMemo(() => worldsData ?? [], [worldsData]);

  const { data: historyData } = useGameHistory();
  const activeSaves = useMemo(() => {
    if (!historyData) return [];
    return historyData.filter((h) => h.status !== "ended").slice(0, 3);
  }, [historyData]);

  // ── Mobile categories (dynamic from data) ──
  const mobileCategories = useMemo(() => {
    const set = new Set<string>();
    worlds.forEach((w) => {
      if (w.genre) set.add(w.genre);
    });
    return ["全部", ...Array.from(set)];
  }, [worlds]);

  // ── Spotlight ──
  const spotlightWorlds = useMemo<WorldListItem[]>(
    () => pickFeaturedWorlds(worlds, 4),
    [worlds],
  );

  // ── Display mode ──
  const isSearchMode = query.trim() !== "";
  const isCategoryMode = !isSearchMode && activeCategory !== "全部";
  const isGridMode = isSearchMode || isCategoryMode;

  // ── Mobile filtered worlds ──
  const mobileFilteredWorlds = useMemo(() => {
    const q = query.trim().toLowerCase();
    return worlds.filter((w) => {
      const matchCategory = activeCategory === "全部" || w.genre === activeCategory;
      const matchSearch =
        !q ||
        `${w.name} ${w.genre} ${w.era} ${w.description}`.toLowerCase().includes(q);
      return matchCategory && matchSearch;
    });
  }, [query, activeCategory, worlds]);

  // ── Desktop filtered grid ──
  const filteredGridWorlds = useMemo(() => {
    let result = worlds;
    const trimmedQuery = query.trim();
    if (trimmedQuery) {
      const lowerQuery = trimmedQuery.toLowerCase();
      result = result.filter(
        (w) =>
          (w.name || "").toLowerCase().includes(lowerQuery) ||
          (w.genre || "").toLowerCase().includes(lowerQuery) ||
          (w.description || "").toLowerCase().includes(lowerQuery),
      );
    } else if (activeCategory !== "全部") {
      if (activeCategory === "剧本") {
        result = result.filter((w) => w.has_script);
      } else {
        result = result.filter((w) => w.genre?.includes(activeCategory));
      }
    }
    return result;
  }, [worlds, query, activeCategory]);

  // ── Desktop handlers (scroll + URL sync) ──
  const handleDesktopSearchChange = (value: string) => {
    setQuery(value);
    setActiveCategory("全部");
    writeUrlState({ query: value, category: "全部" }, "replace");
    requestAnimationFrame(() => {
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
  };

  const handleDesktopCategoryClick = (cat: string) => {
    setQuery("");
    setActiveCategory(cat);
    writeUrlState({ query: "", category: cat }, "push");
    requestAnimationFrame(() => {
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
  };

  // ── Mobile handlers (URL sync only, no scroll) ──
  const handleMobileSearchChange = (value: string) => {
    setQuery(value);
    setActiveCategory("全部");
    writeUrlState({ query: value, category: "全部" }, "replace");
  };

  const handleMobileCategoryChange = (cat: string) => {
    setQuery("");
    setActiveCategory(cat);
    writeUrlState({ query: "", category: cat }, "replace");
  };

  // ── URL state sync on mount + popstate ──
  useEffect(() => {
    const syncUrlState = () => {
      const next = readUrlState();
      setQuery(next.query);
      setActiveCategory(next.category);
    };

    syncUrlState();

    const handlePopState = () => {
      syncUrlState();
    };

    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  return (
    <main className={`lv-theme product-discover-page ${isGridMode ? "is-grid-mode" : ""}`}>
      <ProductNav
        active="discover"
        variant={isGridMode ? "solid" : "transparent"}
        search={{
          value: query,
          onChange: handleDesktopSearchChange,
          placeholder: t("searchPlaceholder"),
        }}
      />

      <MobileView
        query={query}
        setQuery={handleMobileSearchChange}
        selectedCategory={activeCategory}
        setSelectedCategory={handleMobileCategoryChange}
        categories={mobileCategories}
        filteredWorlds={mobileFilteredWorlds}
        spotlightWorlds={spotlightWorlds}
      />

      <div className="lv-discover-desktop">
        <DesktopView
          worlds={worlds}
          activeCategory={activeCategory}
          query={query}
          isSearchMode={isSearchMode}
          isCategoryMode={isCategoryMode}
          isGridMode={isGridMode}
          filteredGridWorlds={filteredGridWorlds}
          activeSaves={activeSaves}
          isLoggedIn={!!user}
          onCategoryClick={handleDesktopCategoryClick}
        />
      </div>

      <style jsx global>{`
        /* ── Page root ── */
        .product-discover-page {
          min-height: 100dvh;
          background: var(--lv-bg);
          color: var(--lv-ink);
          position: relative;
        }

        .product-atmosphere {
          position: fixed;
          inset: 0;
          z-index: 0;
          pointer-events: none;
          background:
            radial-gradient(ellipse 80% 50% at 50% 0%, rgba(180,160,140,0.018) 0%, transparent 60%);
        }

        /* ── Responsive split ── */
        @media (max-width: 768px) {
          .lv-discover-desktop { display: none !important; }
        }
        @media (min-width: 769px) {
          .lv-discover-mobile { display: none !important; }
        }

        /* ── Shared ── */
        .carousel-track::-webkit-scrollbar {
          display: none;
        }
        .hover-accent-link:hover {
          color: var(--lv-ink) !important;
        }
        .lobby-play-btn:hover {
          transform: translateY(-1px);
          box-shadow: 0 10px 26px rgba(0, 0, 0, 0.5) !important;
        }

        /* ── Spotlight ── */
        .spotlight-section {
          overscroll-behavior-x: contain;
        }
        .spotlight-nav-btn {
          position: absolute;
          top: 50%;
          z-index: 4;
          width: 50px;
          height: 50px;
          border-radius: 999px;
          border: 1px solid rgba(255,255,255,0.08);
          background: rgba(8,8,10,0.32);
          color: rgba(245,242,235,0.72);
          backdrop-filter: blur(16px);
          display: grid;
          place-items: center;
          cursor: pointer;
          opacity: 0;
          transform: translateY(-50%) scale(0.96);
          transition: opacity 260ms ease, transform 260ms ease, background 200ms ease, border-color 200ms ease;
        }
        .spotlight-section:hover .spotlight-nav-btn,
        .spotlight-section:focus-within .spotlight-nav-btn {
          opacity: 0.85;
          transform: translateY(-50%) scale(1);
        }
        .spotlight-nav-btn.left {
          left: clamp(20px, 3vw, 44px);
        }
        .spotlight-nav-btn.right {
          right: clamp(20px, 3vw, 44px);
        }
        .spotlight-nav-btn:hover,
        .spotlight-nav-btn:focus-visible {
          opacity: 1;
          background: rgba(245,242,235,0.9);
          border-color: rgba(255,255,255,0.22);
          color: var(--lv-bg);
          outline: none;
        }

        /* ── Content container ── */
        .product-content-container {
          position: relative;
          z-index: 2;
        }
        .product-discover-page.is-grid-mode .category-rail-wrapper {
          margin-top: 68px;
        }

        .category-rail-wrapper {
          padding: 12px 0;
          position: relative;
          z-index: 10;
          background: rgba(8,8,10,0.94);
          backdrop-filter: blur(18px) saturate(120%);
          border-bottom: 1px solid rgba(255,255,255,0.04);
          margin-bottom: 28px;
        }
        .category-rail {
          display: flex;
          gap: 8px;
          overflow-x: auto;
          scrollbar-width: none;
          max-width: 1440px;
          margin: 0 auto;
          padding: 0 clamp(20px, 4vw, 60px);
        }
        .category-rail::-webkit-scrollbar {
          display: none;
        }
        .category-pill {
          background: transparent;
          border: 1px solid rgba(255,255,255,0.08);
          color: var(--lv-ink-3);
          min-height: 34px;
          padding: 6px 14px;
          border-radius: 999px;
          font-size: 13px;
          white-space: nowrap;
          cursor: pointer;
          transition: all 0.22s ease;
        }
        .category-pill:hover {
          background: rgba(255,255,255,0.06);
          border-color: rgba(255,255,255,0.14);
          color: var(--lv-ink);
        }
        .category-pill.active {
          background: var(--lv-ink);
          color: var(--lv-bg);
          border-color: var(--lv-ink);
          font-weight: 500;
        }

        /* ── Carousel rows ── */
        .product-carousels-section {
          padding-bottom: 72px;
        }
        .product-row {
          margin-bottom: 28px;
        }
        .product-row-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          max-width: 1440px;
          margin: 0 auto 16px;
          padding: 0 clamp(20px, 4vw, 60px);
        }
        .product-row-header h2 {
          font-size: 20px;
          font-weight: 500;
          margin: 0;
          display: flex;
          align-items: center;
          gap: 8px;
        }
        .row-icon {
          color: var(--lv-ink-3);
        }
        .carousel-nav-btn {
          position: absolute;
          top: 36%;
          width: 36px;
          height: 36px;
          border-radius: 999px;
          z-index: 10;
          display: flex;
          align-items: center;
          justify-content: center;
          color: rgba(245,242,235,0.72);
          border: 1px solid rgba(255,255,255,0.06);
          background: rgba(8,8,10,0.48);
          backdrop-filter: blur(14px);
          cursor: pointer;
          opacity: 0;
          pointer-events: none;
          transition: opacity 260ms ease, transform 260ms ease, background 200ms ease, border-color 200ms ease, color 200ms ease;
        }
        .carousel-nav-btn.left.visible {
          opacity: 0.75;
          pointer-events: auto;
          transform: translateY(-50%) translateX(0);
        }
        .carousel-nav-btn.right.visible {
          opacity: 0.75;
          pointer-events: auto;
          transform: translateY(-50%) translateX(0);
        }
        .carousel-nav-btn.left {
          left: clamp(8px, 1.2vw, 18px);
          transform: translateY(-50%) translateX(-6px);
        }
        .carousel-nav-btn.right {
          right: clamp(8px, 1.2vw, 18px);
          transform: translateY(-50%) translateX(6px);
        }
        .product-row:hover .carousel-nav-btn.visible {
          opacity: 1;
        }
        .carousel-nav-btn:hover,
        .carousel-nav-btn:focus-visible {
          opacity: 1 !important;
          background: rgba(245,242,235,0.9);
          border-color: rgba(255,255,255,0.22);
          color: var(--lv-bg);
          outline: none;
        }

        /* ── Product carousel ── */
        .product-carousel-container {
          position: relative;
          max-width: 1440px;
          margin: 0 auto;
        }
        .product-carousel {
          display: flex;
          gap: 20px;
          overflow-x: auto;
          padding: 0 0 18px;
          scrollbar-width: none;
        }
        .product-carousel::-webkit-scrollbar {
          display: none;
        }
        .product-carousel .product-card:first-child {
          margin-left: clamp(20px, 4vw, 60px);
        }
        .product-carousel .product-card:last-child {
          margin-right: clamp(20px, 4vw, 60px);
        }

        /* ── Product card ── */
        .product-card {
          flex: 0 0 280px;
          display: flex;
          flex-direction: column;
          text-decoration: none;
          transition: transform 320ms var(--lv-ease);
        }
        @media (min-width: 1024px) {
          .product-card {
            flex: 0 0 calc((100vw - 208px) / 4.5);
            max-width: 300px;
          }
        }
        .product-card:hover {
          transform: translateY(-3px);
        }
        .product-card:focus-visible {
          outline: 2px solid rgba(245, 242, 235, 0.72);
          outline-offset: 3px;
          border-radius: var(--lv-r-card);
        }

        .product-card-frame {
          position: relative;
          aspect-ratio: 3/2;
          border-radius: var(--lv-r-card);
          overflow: hidden;
          background: #111;
          box-shadow: var(--lv-card-shadow);
          transition: box-shadow 320ms var(--lv-ease);
        }
        .product-card:hover .product-card-frame {
          box-shadow: var(--lv-card-shadow-hover);
        }
        .product-card-cover {
          position: absolute;
          inset: 0;
          width: 100%;
          height: 100%;
          transform: scale(1);
          transition: transform 520ms var(--lv-ease);
        }
        .product-card:hover .product-card-cover {
          transform: scale(1.04);
        }
        .product-card-play-overlay {
          position: absolute;
          inset: 0;
          display: flex;
          align-items: center;
          justify-content: center;
          background: rgba(8,8,10,0.35);
          opacity: 0;
          transition: opacity 280ms var(--lv-ease);
          z-index: 2;
        }
        .product-card:hover .product-card-play-overlay {
          opacity: 1;
        }
        .product-card-play-btn {
          width: 48px;
          height: 48px;
          border-radius: 999px;
          background: rgba(245,242,235,0.92);
          color: var(--lv-bg);
          display: flex;
          align-items: center;
          justify-content: center;
          transform: scale(0.88);
          transition: transform 280ms var(--lv-ease), background 200ms ease;
          box-shadow: 0 4px 20px rgba(0,0,0,0.4);
        }
        .product-card:hover .product-card-play-btn {
          transform: scale(1);
        }
        .product-card-play-btn:hover {
          background: var(--lv-ink);
          color: var(--lv-bg);
        }

        .product-card-info {
          padding: 10px 2px 0;
        }
        .product-card-kicker {
          margin-bottom: 4px;
          color: var(--lv-ink-3);
          font-size: 11px;
          line-height: 1.2;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }
        .product-card-info h3 {
          margin: 0 0 3px;
          font-family: var(--lv-font-serif);
          font-size: var(--lv-t-h3);
          font-weight: 500;
          color: var(--lv-ink);
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .product-card-meta {
          font-size: 12px;
          color: var(--lv-ink-3);
          line-height: 1.2;
          white-space: nowrap;
          font-variant-numeric: tabular-nums;
        }

        /* ── Grid sections ── */
        .product-grid-section {
          max-width: 1440px;
          margin: 0 auto;
          padding: 24px clamp(20px, 4vw, 60px) 100px;
        }
        .product-grid-section.search-grid-section {
          padding-top: 24px;
        }
        .product-grid-section.category-grid-section {
          padding-top: 24px;
        }
        .product-grid-section h2 {
          font-size: var(--lv-t-h1);
          margin-bottom: 24px;
          font-weight: 500;
        }
        .product-grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
          gap: 28px 18px;
        }
        @media (min-width: 1024px) {
          .product-grid {
            grid-template-columns: repeat(5, minmax(0, calc((100vw - 120px - 72px) / 5)));
          }
        }
        @media (min-width: 1536px) {
          .product-grid {
            grid-template-columns: repeat(6, minmax(0, calc((100vw - 120px - 90px) / 6)));
          }
        }
        .product-grid .product-card {
          width: 100%;
          max-width: none;
          flex: initial;
        }
        .empty-state {
          grid-column: 1 / -1;
          padding: 60px 0;
          text-align: center;
          color: var(--lv-ink-4);
        }
      `}</style>
    </main>
  );
}
