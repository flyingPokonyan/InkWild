"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { motion } from "motion/react";
import { Play, Sparkles, Search, SlidersHorizontal, LayoutGrid, List as ListIcon } from "lucide-react";
import { useTranslations } from "next-intl";

import { ProductNav } from "@/components/ProductNav";
import { difficultyLevel } from "@/lib/difficulty";
import { useWorldList } from "@/lib/api/worlds";
import { useGameHistory } from "@/lib/api/history";
import { pickFeaturedWorlds } from "@/lib/featured-worlds";
import { ossThumb } from "@/lib/oss-image";
import { LazyCover } from "@/components/ui/LazyCover";
import { useAuthStore } from "@/stores/auth";
import type { GameHistoryItem, WorldListItem } from "@/lib/types";

type ModeT = (k: "modeScript" | "modeFree" | "supportsBoth") => string;

function worldModeLabel(world: WorldListItem, t: ModeT): string {
  return world.has_script ? t("supportsBoth") : t("modeFree");
}

function sessionModeLabel(item: GameHistoryItem, t: ModeT): string {
  if (item.mode === "script") return t("modeScript");
  if (item.mode === "free") return t("modeFree");
  return t("modeFree");
}

export default function DiscoverPage() {
  const t = useTranslations("discoverPage");
  const user = useAuthStore((s) => s.user);
  const [query, setQuery] = useState("");
  const [selectedCategory, setSelectedCategory] = useState("全部");

  const { data: worldsData, isLoading: worldsLoading } = useWorldList();
  const worlds = useMemo(() => worldsData ?? [], [worldsData]);
  const showSkeleton = worldsLoading && worlds.length === 0;

  const { data: historyData } = useGameHistory();
  const activeSaves = useMemo(() => {
    if (!historyData) return [];
    return historyData.filter((h) => h.status !== "ended").slice(0, 3);
  }, [historyData]);

  const categories = useMemo(() => {
    const set = new Set<string>();
    worlds.forEach((w) => {
      if (w.genre) set.add(w.genre);
    });
    return ["全部", ...Array.from(set)];
  }, [worlds]);

  const spotlightWorlds = useMemo<WorldListItem[]>(
    () => pickFeaturedWorlds(worlds, 4),
    [worlds],
  );

  const filteredWorlds = useMemo(() => {
    const q = query.trim().toLowerCase();
    return worlds.filter((w) => {
      const matchCategory = selectedCategory === "全部" || w.genre === selectedCategory;
      const matchSearch =
        !q ||
        `${w.name} ${w.genre} ${w.era} ${w.description}`.toLowerCase().includes(q);
      return matchCategory && matchSearch;
    });
  }, [query, selectedCategory, worlds]);

  // spotlight 展示中（非搜索、未筛选、有精选）：导航栏走透明叠在封面上，封面全屏出血到顶，
  // 不再被实色黑条压住顶部。搜索/筛选态没有 hero，导航栏回到 solid。
  const showingSpotlight = !query && selectedCategory === "全部" && spotlightWorlds.length > 0;

  return (
    <main
      className="lv-theme"
      style={{
        background: "var(--lv-bg)",
        color: "var(--lv-ink)",
        minHeight: "100dvh",
        overflowX: "hidden",
        position: "relative",
      }}
    >
      <ProductNav
        active="discover"
        variant={showingSpotlight ? "transparent" : "solid"}
        search={{
          value: query,
          onChange: setQuery,
          placeholder: t("searchPlaceholder"),
        }}
      />

      {/* 移动端单独 view —— 桌面 hidden via CSS */}
      <MobileDiscoverView
        query={query}
        setQuery={setQuery}
        selectedCategory={selectedCategory}
        setSelectedCategory={setSelectedCategory}
        worlds={worlds}
        categories={categories}
        filteredWorlds={filteredWorlds}
        spotlightWorlds={spotlightWorlds}
      />

      <div className="lv-discover-desktop">
      {showingSpotlight && <SpotlightSection worlds={spotlightWorlds} />}

      <div
        style={{
          maxWidth: "1440px",
          margin: "0 auto",
          padding: showingSpotlight
            ? "56px clamp(20px, 4vw, 52px) 80px"
            : "100px clamp(20px, 4vw, 52px) 80px",
          position: "relative",
          zIndex: 2,
        }}
      >
        {user && !query && activeSaves.length > 0 && (
          <motion.section
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.1 }}
            style={{ marginTop: 0 }}
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
                  fontSize: "22px",
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

        <section style={{ marginTop: "56px" }}>
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "flex-end",
              gap: "20px",
              flexWrap: "wrap",
              borderBottom: "1px solid rgba(255, 255, 255, 0.04)",
              paddingBottom: "14px",
              marginBottom: "28px",
            }}
          >
            <div>
              <div className="lv-t-caps" style={{ color: "var(--lv-ink-3)" }}>
                {t("sectionEyebrow")}
              </div>
              <h2
                style={{
                  marginTop: "4px",
                  fontFamily: "var(--lv-font-serif)",
                  fontSize: "26px",
                  fontWeight: 600,
                  color: "var(--lv-ink)",
                }}
              >
                {query ? t("sectionTitleSearch") : t("sectionTitleDefault")}
              </h2>
            </div>
            <div style={{ color: "var(--lv-ink-3)", fontSize: "13px" }}>
              {t.rich("foundCount", {
                count: filteredWorlds.length,
                strong: (chunks) => (
                  <span style={{ color: "var(--lv-ink)", fontWeight: 600 }}>{chunks}</span>
                ),
              })}
            </div>
          </div>

          {!query && categories.length > 1 && (
            <div
              style={{
                display: "flex",
                gap: "8px",
                overflowX: "auto",
                paddingBottom: "12px",
                scrollbarWidth: "none",
                marginBottom: "24px",
              }}
              className="carousel-track"
            >
              {categories.map((cat) => {
                const isSelected = selectedCategory === cat;
                return (
                  <button
                    key={cat}
                    onClick={() => setSelectedCategory(cat)}
                    className={"filter-pill" + (isSelected ? " selected" : "")}
                    style={{
                      position: "relative",
                      padding: "6px 18px",
                      borderRadius: "100px",
                      border: "1px solid rgba(255, 255, 255, 0.04)",
                      background: "rgba(255, 255, 255, 0.015)",
                      color: isSelected ? "var(--lv-bg)" : "var(--lv-ink-2)",
                      fontSize: "13px",
                      fontWeight: 600,
                      cursor: "pointer",
                      transition: "color 0.25s ease",
                      outline: 0,
                      zIndex: 1,
                      whiteSpace: "nowrap",
                    }}
                  >
                    {isSelected && (
                      <motion.div
                        layoutId="discover-filter-indicator"
                        style={{
                          position: "absolute",
                          inset: -1,
                          borderRadius: "100px",
                          background: "rgba(245, 242, 235, 0.90)",
                          boxShadow: "0 2px 8px rgba(0, 0, 0, 0.25)",
                          zIndex: -1,
                        }}
                        transition={{ type: "spring", stiffness: 380, damping: 30 }}
                      />
                    )}
                    {cat}
                  </button>
                );
              })}
            </div>
          )}

          {showSkeleton ? (
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
                gap: "24px",
              }}
            >
              {Array.from({ length: 6 }).map((_, i) => (
                <LobbyWorldCardSkeleton key={i} />
              ))}
            </div>
          ) : filteredWorlds.length > 0 ? (
            <motion.div
              layout
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
                gap: "24px",
              }}
            >
              {filteredWorlds.map((world, idx) => (
                <LobbyWorldCard key={world.id} world={world} index={idx} />
              ))}
            </motion.div>
          ) : (
            <div
              style={{
                padding: "60px 0",
                textAlign: "center",
                background: "rgba(255, 255, 255, 0.01)",
                border: "1px dashed rgba(255, 255, 255, 0.06)",
                borderRadius: "12px",
              }}
            >
              <h3 style={{ fontSize: "16px", color: "var(--lv-ink-2)" }}>{t("emptyTitle")}</h3>
              <p style={{ marginTop: "6px", color: "var(--lv-ink-4)", fontSize: "13.5px" }}>
                {t("emptyHint")}
              </p>
            </div>
          )}
        </section>
      </div>
      </div>

      <style jsx global>{`
        .carousel-track::-webkit-scrollbar {
          display: none;
        }
        @media (max-width: 768px) {
          .lv-discover-desktop { display: none !important; }
        }
        @media (min-width: 769px) {
          .lv-discover-mobile { display: none !important; }
        }
        .hover-accent-link:hover {
          color: var(--lv-ink) !important;
        }
        .lobby-play-btn:hover {
          transform: translateY(-1px);
          box-shadow: 0 10px 26px rgba(0, 0, 0, 0.5) !important;
        }

        .world-card-btn {
          opacity: 0.92;
          transition: all 250ms cubic-bezier(0.16, 1, 0.3, 1) !important;
        }
        @media (hover: hover) {
          .world-card-link:hover .world-card-btn {
            opacity: 1 !important;
            transform: scale(1.08);
          }
        }

        .filter-pill {
          transition: all 250ms ease !important;
        }
        .filter-pill:not(.selected):hover {
          border-color: rgba(255, 255, 255, 0.16) !important;
          color: var(--lv-ink) !important;
        }
      `}</style>
    </main>
  );
}

interface MobileDiscoverViewProps {
  query: string;
  setQuery: (v: string) => void;
  selectedCategory: string;
  setSelectedCategory: (v: string) => void;
  worlds: WorldListItem[];
  categories: string[];
  filteredWorlds: WorldListItem[];
  spotlightWorlds: WorldListItem[];
}

function MobileDiscoverView({
  query,
  setQuery,
  selectedCategory,
  setSelectedCategory,
  worlds: _worlds,
  categories,
  filteredWorlds,
  spotlightWorlds,
}: MobileDiscoverViewProps) {
  void _worlds;
  const t = useTranslations("discoverPage");
  const [viewMode, setViewMode] = useState<"list" | "grid">("list");

  const showingSpotlight = !query && selectedCategory === "全部" && spotlightWorlds.length > 0;

  // 当 spotlight 展示中（非搜索、未筛选题材），从下方列表里剔除所有 spotlight 世界，避免同卡出现 2 次
  const spotlightIdSet = useMemo(() => new Set(spotlightWorlds.map((w) => w.id)), [spotlightWorlds]);
  const listedWorlds = showingSpotlight
    ? filteredWorlds.filter((w) => !spotlightIdSet.has(w.id))
    : filteredWorlds;

  return (
    <div
      className="lv-discover-mobile"
      style={{
        position: "relative",
        zIndex: 2,
        paddingBottom: "calc(76px + env(safe-area-inset-bottom))",
      }}
    >
      {/* 搜索 + 筛选 */}
      <div
        style={{
          padding: "calc(env(safe-area-inset-top, 0px) + 16px) 16px 12px",
          display: "flex",
          gap: 10,
        }}
      >
        <label
          style={{
            flex: 1,
            height: 44,
            borderRadius: 999,
            border: "1px solid rgba(255,255,255,0.08)",
            background: "rgba(255,255,255,0.045)",
            display: "flex",
            alignItems: "center",
            gap: 9,
            padding: "0 14px",
            color: "var(--lv-ink-3)",
            fontSize: 13,
          }}
        >
          <Search size={17} style={{ color: "var(--lv-ink-3)" }} />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t("searchPlaceholder")}
            style={{
              flex: 1,
              border: 0,
              outline: 0,
              background: "transparent",
              color: "var(--lv-ink)",
              fontSize: 13,
            }}
          />
        </label>
        <button
          type="button"
          style={{
            height: 44,
            minHeight: 44,
            padding: "0 14px",
            borderRadius: 999,
            border: "1px solid rgba(255,255,255,0.10)",
            background: "transparent",
            color: "var(--lv-ink-2)",
            fontFamily: "var(--lv-font-mono)",
            fontSize: 10,
            letterSpacing: "0.14em",
            cursor: "pointer",
            display: "inline-flex",
            alignItems: "center",
            gap: 6,
          }}
        >
          <SlidersHorizontal size={14} />
          筛选
        </button>
      </div>

      {/* 题材 chip 横滑 */}
      {categories.length > 1 && (
        <div
          className="carousel-track"
          style={{
            display: "flex",
            gap: 8,
            overflowX: "auto",
            padding: "0 16px 14px",
            scrollbarWidth: "none",
          }}
        >
          {categories.map((cat) => {
            const active = selectedCategory === cat;
            return (
              <button
                key={cat}
                onClick={() => setSelectedCategory(cat)}
                style={{
                  flex: "0 0 auto",
                  borderRadius: 999,
                  padding: "9px 15px",
                  border: active
                    ? "1px solid rgba(245,242,235,0.90)"
                    : "1px solid rgba(255,255,255,0.08)",
                  background: active
                    ? "rgba(245,242,235,0.90)"
                    : "rgba(255,255,255,0.045)",
                  color: active ? "var(--lv-bg)" : "var(--lv-ink-2)",
                  fontFamily: "var(--lv-font-mono)",
                  fontSize: 10,
                  fontWeight: active ? 700 : 500,
                  letterSpacing: "0.14em",
                  cursor: "pointer",
                  minHeight: 32,
                  boxShadow: active ? "0 2px 8px rgba(0,0,0,0.25)" : "none",
                }}
              >
                {cat === "全部" ? t("categoryAll") : cat}
              </button>
            );
          })}
        </div>
      )}

      {/* Spotlight —— 横滑 scroll-snap 轨道：一屏一张、露出下一张边缘，原生惯性吸附 */}
      {showingSpotlight && <MobileSpotlightRail worlds={spotlightWorlds} />}

      {/* section head + view toggle */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "2px 16px 10px",
        }}
      >
        <h2
          style={{
            fontFamily: "var(--lv-font-serif)",
            fontSize: 21,
            fontWeight: 500,
            color: "var(--lv-ink)",
          }}
        >
          {query ? t("sectionTitleSearch") : t("sectionTitleDefault")}
        </h2>
        <div
          style={{
            height: 34,
            display: "grid",
            gridTemplateColumns: "repeat(2, 34px)",
            borderRadius: 999,
            border: "1px solid rgba(255,255,255,0.08)",
            background: "rgba(255,255,255,0.025)",
            overflow: "hidden",
          }}
        >
          <button
            type="button"
            aria-label="网格视图"
            onClick={() => setViewMode("grid")}
            style={{
              display: "grid",
              placeItems: "center",
              background: viewMode === "grid" ? "rgba(255,255,255,0.10)" : "transparent",
              color: viewMode === "grid" ? "var(--lv-ink)" : "var(--lv-ink-3)",
              border: 0,
              cursor: "pointer",
            }}
          >
            <LayoutGrid size={16} />
          </button>
          <button
            type="button"
            aria-label="列表视图"
            onClick={() => setViewMode("list")}
            style={{
              display: "grid",
              placeItems: "center",
              background: viewMode === "list" ? "rgba(255,255,255,0.10)" : "transparent",
              color: viewMode === "list" ? "var(--lv-ink)" : "var(--lv-ink-3)",
              border: 0,
              cursor: "pointer",
            }}
          >
            <ListIcon size={16} />
          </button>
        </div>
      </div>

      {/* 列表 */}
      {listedWorlds.length === 0 ? (
        <div
          style={{
            margin: "0 16px",
            padding: "48px 16px",
            textAlign: "center",
            background: "rgba(255,255,255,0.01)",
            border: "1px dashed rgba(255,255,255,0.06)",
            borderRadius: 16,
          }}
        >
          <h3 style={{ fontSize: 15, color: "var(--lv-ink-2)" }}>{t("emptyTitle")}</h3>
          <p style={{ marginTop: 6, color: "var(--lv-ink-4)", fontSize: 12 }}>
            {t("emptyHint")}
          </p>
        </div>
      ) : viewMode === "list" ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 9, padding: "0 12px 16px" }}>
          {listedWorlds.map((w) => (
            <MobileWorldRow key={w.id} world={w} />
          ))}
        </div>
      ) : (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(2, 1fr)",
            gap: "16px 10px",
            padding: "0 12px 16px",
          }}
        >
          {listedWorlds.map((w) => (
            <MobileWorldGridTile key={w.id} world={w} />
          ))}
        </div>
      )}
    </div>
  );
}

/**
 * 移动端「本周精选」横滑轨道。
 * 原生 scroll-snap（一屏一张、露出下一张边缘 + 惯性吸附），取代旧的 Framer drag 回弹方案；
 * 整卡可点进入（横滑 touchmove 不触发点击，故不与滑动冲突），底部小圆点跟随滚动位置。
 */
function MobileSpotlightRail({ worlds }: { worlds: WorldListItem[] }) {
  const t = useTranslations("discoverPage");
  const railRef = useRef<HTMLDivElement>(null);
  const [active, setActive] = useState(0);
  const multi = worlds.length > 1;

  const stepOf = (rail: HTMLDivElement) => {
    const first = rail.firstElementChild as HTMLElement | null;
    return first ? first.offsetWidth : rail.clientWidth;
  };
  const handleScroll = () => {
    const rail = railRef.current;
    if (rail) setActive(Math.round(rail.scrollLeft / stepOf(rail)));
  };
  const goTo = (i: number) => {
    const rail = railRef.current;
    if (rail) rail.scrollTo({ left: i * stepOf(rail), behavior: "smooth" });
  };

  return (
    <div style={{ margin: "0 0 14px" }}>
      <div
        ref={railRef}
        onScroll={handleScroll}
        className="carousel-track"
        style={{
          display: "flex",
          overflowX: "auto",
          scrollSnapType: "x mandatory",
          scrollbarWidth: "none",
          WebkitOverflowScrolling: "touch",
        }}
      >
        {worlds.map((w) => {
          const img = ossThumb(w.hero_image || w.cover_image, 900);
          return (
            <div
              key={w.id}
              style={{
                // 每个 slide 占整屏宽，内 16px gutter，下一张完全在屏外 → 无露边、一次滑一整屏
                flex: "0 0 100%",
                scrollSnapAlign: "start",
                boxSizing: "border-box",
                padding: "0 16px",
              }}
            >
            <Link
              href={`/worlds/${w.id}`}
              draggable={false}
              style={{
                position: "relative",
                display: "block",
                width: "100%",
                height: 188,
                borderRadius: 22,
                border: "1px solid rgba(255,255,255,0.08)",
                overflow: "hidden",
                background: "var(--lv-bg-1)",
                textDecoration: "none",
                color: "inherit",
              }}
            >
              <span
                aria-hidden
                style={{
                  position: "absolute",
                  inset: 0,
                  backgroundImage: img
                    ? `url(${img})`
                    : "linear-gradient(135deg, var(--lv-bg-1), var(--lv-bg-2))",
                  backgroundSize: "cover",
                  backgroundPosition: "center",
                }}
              />
              <span
                aria-hidden
                style={{
                  position: "absolute",
                  inset: 0,
                  background:
                    "linear-gradient(180deg, rgba(5,5,7,0.10), rgba(5,5,7,0.72) 72%, rgba(5,5,7,0.92)), radial-gradient(circle at 70% 18%, rgba(223,194,144,0.16), transparent 32%)",
                }}
              />
              <span style={{ position: "absolute", left: 18, right: 110, bottom: 16, zIndex: 2, display: "block" }}>
                <span
                  style={{
                    fontFamily: "var(--lv-font-mono)",
                    fontSize: 9,
                    letterSpacing: "0.04em",
                    color: "var(--lv-accent)",
                    marginBottom: 8,
                    display: "inline-flex",
                    alignItems: "center",
                    gap: 6,
                  }}
                >
                  <Sparkles size={10} fill="currentColor" />
                  {t("weeklyPick")}
                </span>
                <span
                  style={{
                    fontFamily: "var(--lv-font-serif)",
                    fontSize: 24,
                    fontWeight: 500,
                    lineHeight: 1.08,
                    color: "white",
                    marginBottom: 7,
                    display: "block",
                  }}
                >
                  {w.name}
                </span>
                {w.description && (
                  <span
                    style={{
                      fontSize: 12,
                      lineHeight: 1.45,
                      color: "rgba(245,242,235,0.72)",
                      maxWidth: 260,
                      display: "-webkit-box",
                      WebkitLineClamp: 1,
                      WebkitBoxOrient: "vertical",
                      overflow: "hidden",
                    }}
                  >
                    {w.description}
                  </span>
                )}
              </span>
              <span
                style={{
                  position: "absolute",
                  right: 16,
                  bottom: 16,
                  zIndex: 3,
                  height: 40,
                  padding: "0 16px 0 14px",
                  borderRadius: 9999,
                  background: "rgba(245,242,235,0.95)",
                  color: "var(--lv-bg)",
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 7,
                  fontSize: 13,
                  fontWeight: 600,
                  letterSpacing: "0.02em",
                  boxShadow: "0 6px 16px rgba(0,0,0,0.35)",
                  whiteSpace: "nowrap",
                }}
              >
                <Play size={12} fill="currentColor" strokeWidth={0} />
                {t("enter")}
              </span>
            </Link>
            </div>
          );
        })}
      </div>

      {multi && (
        <div style={{ display: "flex", justifyContent: "center", gap: 6, marginTop: 10 }}>
          {worlds.map((w, i) => (
            <button
              key={w.id}
              type="button"
              onClick={() => goTo(i)}
              aria-label={`切换到 ${w.name}`}
              style={{
                width: i === active ? 22 : 6,
                height: 3,
                borderRadius: 999,
                background: i === active ? "var(--lv-accent)" : "rgba(255,255,255,0.22)",
                border: 0,
                padding: 0,
                cursor: "pointer",
                transition: "all 320ms cubic-bezier(0.2, 0.8, 0.2, 1)",
              }}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function MobileWorldRow({ world }: { world: WorldListItem }) {
  const t = useTranslations("discoverPage");
  const cover = ossThumb(world.cover_image || world.hero_image, 520);
  const tag = [world.genre, world.era].filter(Boolean).join(" · ") || "—";
  return (
    <Link
      href={`/worlds/${world.id}`}
      style={{
        display: "grid",
        gridTemplateColumns: "36% 1fr",
        minHeight: 132,
        borderRadius: 18,
        overflow: "hidden",
        border: "1px solid rgba(255,255,255,0.08)",
        background: "rgba(255,255,255,0.055)",
        textDecoration: "none",
        color: "inherit",
      }}
    >
      <LazyCover url={cover} aria-hidden style={{ position: "relative" }} />
      <div style={{ minWidth: 0, padding: "12px 14px 11px 16px", display: "flex", flexDirection: "column" }}>
        <span
          style={{
            fontFamily: "var(--lv-font-mono)",
            fontSize: 9,
            letterSpacing: "0.14em",
            color: "var(--lv-ink-3)",
            marginBottom: 5,
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
          }}
        >
          {tag}
        </span>
        <h3
          style={{
            fontFamily: "var(--lv-font-serif)",
            fontSize: 17,
            fontWeight: 500,
            lineHeight: 1.12,
            color: "var(--lv-ink)",
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
            marginBottom: 6,
          }}
        >
          {world.name}
        </h3>
        {world.description && (
          <p
            style={{
              color: "var(--lv-ink-2)",
              fontSize: 11.5,
              lineHeight: 1.42,
              display: "-webkit-box",
              WebkitLineClamp: 1,
              WebkitBoxOrient: "vertical",
              overflow: "hidden",
              margin: 0,
            }}
          >
            {world.description}
          </p>
        )}
        <div
          style={{
            marginTop: "auto",
            paddingTop: 9,
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 10,
          }}
        >
          <span
            style={{
              fontFamily: "var(--lv-font-mono)",
              fontSize: 9,
              letterSpacing: "0.10em",
              color: "var(--lv-ink-3)",
            }}
          >
            {world.has_script ? "剧本模式" : "自由探索"}
          </span>
          <span
            style={{
              minWidth: 44,
              height: 34,
              padding: "0 12px",
              borderRadius: 999,
              border: "1px solid rgba(255,255,255,0.12)",
              background: "rgba(255,255,255,0.05)",
              color: "var(--lv-ink)",
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: 12,
              fontWeight: 500,
              letterSpacing: "0.04em",
            }}
          >
            {t("enter")}
          </span>
        </div>
      </div>
    </Link>
  );
}

function MobileWorldGridTile({ world }: { world: WorldListItem }) {
  const cover = ossThumb(world.cover_image || world.hero_image, 520);
  return (
    <Link
      href={`/worlds/${world.id}`}
      style={{ display: "block", textDecoration: "none", color: "inherit" }}
    >
      {/* 封面自带圆角描边，无外层卡框 —— 对齐桌面 LobbyWorldCard + 腾讯/爱奇艺无框网格 */}
      <LazyCover
        url={cover}
        aria-hidden
        style={{
          aspectRatio: "16 / 10",
          borderRadius: 12,
          overflow: "hidden",
          border: "1px solid rgba(255,255,255,0.08)",
          position: "relative",
        }}
      />
      <div style={{ padding: "7px 2px 0" }}>
        <h3
          style={{
            fontFamily: "var(--lv-font-serif)",
            fontSize: 14,
            fontWeight: 500,
            color: "var(--lv-ink)",
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
          }}
        >
          {world.name}
        </h3>
        <span
          style={{
            fontFamily: "var(--lv-font-mono)",
            fontSize: 9,
            letterSpacing: "0.12em",
            color: "var(--lv-ink-3)",
            display: "block",
            marginTop: 3,
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
          }}
        >
          {[world.genre, world.era].filter(Boolean).join(" · ") || "—"}
        </span>
      </div>
    </Link>
  );
}

function SpotlightSection({ worlds }: { worlds: WorldListItem[] }) {
  const t = useTranslations("discoverPage");
  const tWorlds = useTranslations("worlds");
  const [idx, setIdx] = useState(0);

  useEffect(() => {
    if (worlds.length <= 1) return;
    const t = window.setInterval(() => {
      setIdx((i) => (i + 1) % worlds.length);
    }, 9000);
    return () => window.clearInterval(t);
  }, [worlds.length]);

  const world = worlds[idx];
  if (!world) return null;

  return (
    <section
      style={{
        position: "relative",
        width: "100%",
        height: "clamp(560px, 78vh, 720px)",
        overflow: "hidden",
        zIndex: 1,
      }}
      aria-label={`本周精选：${world.name}`}
    >
      {worlds.map((w, i) => {
        const img = ossThumb(w.hero_image || w.cover_image, 900);
        if (!img) return null;
        return (
          <div
            key={w.id}
            aria-hidden
            style={{
              position: "absolute",
              inset: 0,
              backgroundImage: `url(${img})`,
              backgroundSize: "cover",
              // 容器比图高/扁时只吃底部（底部被渐变+CTA 盖住），保护顶部主体
              backgroundPosition: "center 20%",
              opacity: i === idx ? 1 : 0,
              transition: "opacity 1400ms cubic-bezier(0.4, 0, 0.2, 1)",
              zIndex: 0,
            }}
          />
        );
      })}

      {/* Cinematic chrome：底部线性渐变（给 footer 文字打底）+ 左下 radial 暗角
          （局部加深文字 safe-zone，不动画面中段）。模型生图怎么构图都能 work。 */}
      <div
        aria-hidden
        style={{
          position: "absolute",
          inset: 0,
          background:
            "linear-gradient(180deg, rgba(8,8,10,0) 0%, rgba(8,8,10,0) 38%, rgba(8,8,10,0.55) 72%, rgba(8,8,10,0.92) 94%, var(--lv-bg) 100%)",
          zIndex: 1,
          pointerEvents: "none",
        }}
      />
      <div
        aria-hidden
        style={{
          position: "absolute",
          inset: 0,
          background:
            "radial-gradient(ellipse 60% 55% at 8% 92%, rgba(0,0,0,0.6) 0%, rgba(0,0,0,0.3) 35%, transparent 65%)",
          zIndex: 1,
          pointerEvents: "none",
        }}
      />

      {/* 内容区跟下方网格对齐到同一 max-width；锚定在画面最低 1/3 */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          zIndex: 3,
          display: "flex",
          alignItems: "flex-end",
          paddingBottom: "clamp(64px, 10vh, 112px)",
        }}
      >
        <div
          style={{
            maxWidth: "1440px",
            width: "100%",
            margin: "0 auto",
            padding: "0 clamp(20px, 4vw, 52px)",
          }}
        >
          <motion.div
            key={world.id}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, ease: [0.2, 0.8, 0.2, 1] }}
            style={{ maxWidth: "640px" }}
          >
            {/* 不再叠 system-font 的世界名 h1 ——
                hero prompt 已让模型自行决定要不要把标题画进画面（要画就用我们提供的中英文名），
                UI 这里只承担 caps / meta / description / CTA 等 metadata。 */}
            <div
              className="lv-t-caps"
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "8px",
                color: "var(--lv-accent)",
                letterSpacing: "0.04em",
              }}
            >
              <Sparkles size={10} fill="currentColor" />
              {t("weeklyPick")}
            </div>

            <div
              style={{
                marginTop: "20px",
                display: "flex",
                flexWrap: "wrap",
                gap: "12px",
                alignItems: "center",
                color: "var(--lv-ink-2)",
                fontSize: "13.5px",
              }}
            >
              {world.genre && <span>{world.genre}</span>}
              {world.era && (
                <>
                  <span style={{ color: "rgba(255,255,255,0.15)" }}>·</span>
                  <span>{world.era}</span>
                </>
              )}
              {world.difficulty > 0 && (
                <>
                  <span style={{ color: "rgba(255,255,255,0.15)" }}>·</span>
                  <span>
                    {tWorlds("difficulty")}{" "}
                    {tWorlds("difficultyName", { level: difficultyLevel(world.difficulty) })}
                  </span>
                </>
              )}
            </div>

            {world.description && (
              <p
                style={{
                  marginTop: "14px",
                  fontSize: "15px",
                  color: "var(--lv-ink-2)",
                  lineHeight: 1.65,
                  display: "-webkit-box",
                  WebkitLineClamp: 2,
                  WebkitBoxOrient: "vertical",
                  overflow: "hidden",
                }}
              >
                {world.description}
              </p>
            )}

            <div style={{ display: "flex", gap: "12px", marginTop: "26px", flexWrap: "wrap" }}>
              <Link
                href={`/worlds/${world.id}`}
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "8px",
                  height: "44px",
                  padding: "0 24px",
                  borderRadius: "100px",
                  background: "var(--lv-ink)",
                  color: "#08080a",
                  fontWeight: 600,
                  fontSize: "14px",
                  textDecoration: "none",
                  boxShadow: "0 8px 24px rgba(0, 0, 0, 0.4)",
                  transition: "all 0.2s ease",
                }}
                className="lobby-play-btn"
              >
                <Play size={12} fill="currentColor" strokeWidth={0} />
                {tWorlds("startJourney")}
              </Link>
            </div>
          </motion.div>
        </div>
      </div>

      {worlds.length > 1 && (
        <div
          style={{
            position: "absolute",
            zIndex: 3,
            bottom: "calc(clamp(20px, 4vh, 32px) + env(safe-area-inset-bottom, 0px))",
            right: "clamp(20px, 4vw, 52px)",
            display: "flex",
            gap: "8px",
          }}
        >
          {worlds.map((w, i) => (
            <button
              key={w.id}
              type="button"
              onClick={() => setIdx(i)}
              aria-label={`切换到 ${w.name}`}
              style={{
                width: i === idx ? 28 : 8,
                height: 2,
                background: i === idx ? "var(--lv-accent)" : "rgba(255,255,255,0.3)",
                transition: "all 380ms cubic-bezier(0.2, 0.8, 0.2, 1)",
                cursor: "pointer",
                border: 0,
                padding: 0,
                borderRadius: 100,
              }}
            />
          ))}
        </div>
      )}

    </section>
  );
}

function ContinueSaveCard({ save }: { save: GameHistoryItem }) {
  const [hovered, setHovered] = useState(false);
  const tWorlds = useTranslations("worlds");
  const tHistory = useTranslations("history");

  return (
    <Link
      href={`/play/${save.session_id}`}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        flex: "0 0 280px",
        display: "flex",
        textDecoration: "none",
        color: "inherit",
        borderRadius: "10px",
        border: hovered
          ? "1px solid rgba(255, 255, 255, 0.12)"
          : "1px solid rgba(255, 255, 255, 0.04)",
        background: hovered ? "rgba(255, 255, 255, 0.03)" : "rgba(255, 255, 255, 0.01)",
        backdropFilter: "blur(12px)",
        padding: "10px",
        gap: "12px",
        boxShadow: hovered ? "0 12px 28px rgba(0,0,0,0.5)" : "0 4px 10px rgba(0,0,0,0.2)",
        transition: "all 300ms cubic-bezier(0.16, 1, 0.3, 1)",
        transform: hovered ? "translateY(-2px)" : "translateY(0)",
      }}
    >
      <div
        style={{
          width: "66px",
          height: "88px",
          borderRadius: "6px",
          backgroundImage: save.cover_image ? `url(${ossThumb(save.cover_image, 96)})` : undefined,
          backgroundColor: save.cover_image ? undefined : "rgba(255, 255, 255, 0.02)",
          backgroundSize: "cover",
          backgroundPosition: "center",
          border: hovered
            ? "1px solid rgba(255, 255, 255, 0.12)"
            : "1px solid rgba(255, 255, 255, 0.04)",
          flexShrink: 0,
          transition: "all 300ms cubic-bezier(0.16, 1, 0.3, 1)",
        }}
      />

      <div
        style={{
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          flex: 1,
          minWidth: 0,
        }}
      >
        <div>
          <span
            style={{
              fontSize: "8.5px",
              fontWeight: 600,
              color: "var(--lv-ink-2)",
              letterSpacing: "0.06em",
              background: "rgba(255, 255, 255, 0.02)",
              border: "1px solid rgba(255, 255, 255, 0.06)",
              padding: "1px 5px",
              borderRadius: "3px",
              display: "inline-block",
              transition: "all 300ms cubic-bezier(0.16, 1, 0.3, 1)",
            }}
          >
            {sessionModeLabel(save, tWorlds)}
          </span>

          <div
            style={{
              color: "var(--lv-ink)",
              fontWeight: 600,
              fontSize: "14px",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
              marginTop: "4px",
            }}
          >
            {save.world_name}
          </div>

          <div
            style={{
              fontSize: "11.5px",
              color: "var(--lv-ink-3)",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
              marginTop: "2px",
            }}
          >
            {save.character_name}
            {save.current_location ? ` · ${save.current_location}` : ""}
          </div>
        </div>

        <div
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "4px",
            fontSize: "10.5px",
            fontWeight: 600,
            color: hovered ? "var(--lv-ink)" : "var(--lv-ink-3)",
            transition: "color 0.2s",
          }}
        >
          <Play size={9} fill="currentColor" strokeWidth={0} />
          {save.rounds_played != null
            ? tHistory("round", { n: save.rounds_played })
            : tHistory("ctaContinue")}
        </div>
      </div>
    </Link>
  );
}

function LobbyWorldCard({ world, index }: { world: WorldListItem; index: number }) {
  const [hovered, setHovered] = useState(false);
  const cover = ossThumb(world.cover_image || world.hero_image, 520);
  const tWorlds = useTranslations("worlds");

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 15 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay: Math.min(index * 0.03, 0.3) }}
    >
      <Link
        href={`/worlds/${world.id}`}
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
        className="world-card-link"
        style={{
          display: "block",
          textDecoration: "none",
          color: "inherit",
          padding: 0,
          transition: "transform 350ms cubic-bezier(0.16, 1, 0.3, 1)",
          transform: hovered ? "translateY(-3px)" : "translateY(0)",
        }}
      >
        <div
          style={{
            position: "relative",
            aspectRatio: "3 / 2",
            borderRadius: "12px",
            overflow: "hidden",
            background: "var(--lv-bg-1)",
            marginBottom: "10px",
            border: hovered
              ? "1px solid rgba(255, 255, 255, 0.12)"
              : "1px solid rgba(255, 255, 255, 0.06)",
            boxShadow: hovered
              ? "0 16px 32px rgba(0,0,0,0.45)"
              : "0 6px 15px rgba(0,0,0,0.2)",
            transition: "all 350ms cubic-bezier(0.16, 1, 0.3, 1)",
          }}
        >
          {cover && (
            <LazyCover
              url={cover}
              aria-hidden
              style={{
                position: "absolute",
                inset: 0,
                transform: hovered ? "scale(1.04)" : "scale(1)",
                transition: "transform 600ms cubic-bezier(0.16, 1, 0.3, 1)",
              }}
            />
          )}
          <div
            style={{
              position: "absolute",
              inset: 0,
              background:
                "linear-gradient(to top, rgba(8, 8, 10, 0.28) 0%, transparent 35%)",
            }}
          />

          <span
            style={{
              position: "absolute",
              top: "8px",
              left: "8px",
              padding: "2px 8px",
              borderRadius: "4px",
              background: "rgba(8, 8, 10, 0.72)",
              border: "1px solid rgba(255, 255, 255, 0.12)",
              color: "var(--lv-ink-2)",
              fontSize: "9px",
              fontWeight: 600,
              letterSpacing: "0.06em",
              zIndex: 2,
              backdropFilter: "blur(8px)",
            }}
          >
            {worldModeLabel(world, tWorlds)}
          </span>

          <div
            className="world-card-btn"
            aria-label={tWorlds("startJourney")}
            style={{
              position: "absolute",
              inset: "auto 10px 10px auto",
              display: "grid",
              placeItems: "center",
              width: 34,
              height: 34,
              borderRadius: "50%",
              background: "rgba(245, 242, 235, 0.95)",
              color: "#08080a",
              zIndex: 2,
              boxShadow: "0 4px 12px rgba(0, 0, 0, 0.4)",
            }}
          >
            <Play size={12} fill="currentColor" strokeWidth={0} style={{ marginLeft: 1 }} />
          </div>
        </div>

        <h3
          style={{
            margin: 0,
            marginBottom: "4px",
            color: "var(--lv-ink)",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
            fontFamily: "var(--lv-font-serif)",
            fontSize: "18px",
            fontWeight: 500,
            transition: "color 200ms ease",
          }}
        >
          {world.name}
        </h3>

        {world.description && (
          <p
            style={{
              margin: "0 0 10px",
              fontSize: "12.5px",
              color: "var(--lv-ink-3)",
              lineHeight: 1.45,
              overflow: "hidden",
              textOverflow: "ellipsis",
              display: "-webkit-box",
              WebkitLineClamp: 1,
              WebkitBoxOrient: "vertical",
            }}
          >
            {world.description}
          </p>
        )}

        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            color: "var(--lv-ink-3)",
            fontSize: "11.5px",
            borderTop: "1px solid rgba(255, 255, 255, 0.04)",
            paddingTop: "8px",
          }}
        >
          <span>
            {[world.genre, world.era].filter(Boolean).join(" · ") || "—"}
          </span>

          {world.difficulty > 0 && (
            <span style={{ color: "var(--lv-ink-3)", fontSize: "11px" }}>
              {tWorlds("difficulty")}{" "}
              {tWorlds("difficultyName", { level: difficultyLevel(world.difficulty) })}
            </span>
          )}
        </div>
      </Link>
    </motion.div>
  );
}

/**
 * 骨架屏 · 匹配 LobbyWorldCard 形状（3:2 封面 + 标题条 + meta 条）
 * §10.1 列表加载规范：用 .lv-skel（柔光扫过）不用 spinner。
 */
function LobbyWorldCardSkeleton() {
  return (
    <div style={{ display: "block" }}>
      {/* 封面骨架 */}
      <div
        className="lv-skel"
        style={{
          aspectRatio: "3 / 2",
          borderRadius: 12,
          marginBottom: 10,
          border: "1px solid rgba(255,255,255,0.06)",
        }}
      />
      {/* 标题骨架 */}
      <div
        className="lv-skel"
        style={{
          height: 16,
          width: "70%",
          borderRadius: "var(--lv-r-pill, 9999px)",
          marginBottom: 8,
        }}
      />
      {/* meta 骨架 */}
      <div
        className="lv-skel"
        style={{
          height: 11,
          width: "45%",
          borderRadius: "var(--lv-r-pill, 9999px)",
        }}
      />
    </div>
  );
}
