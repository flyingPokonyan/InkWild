"use client";

import Link from "next/link";
import { useMemo, useRef, useState } from "react";
import { Play, Sparkles, Search, SlidersHorizontal, LayoutGrid, List as ListIcon } from "lucide-react";
import { useTranslations } from "next-intl";

import { LazyCover } from "@/components/ui/LazyCover";
import { ossThumb } from "@/lib/oss-image";
import type { WorldListItem } from "@/lib/types";

export interface MobileViewProps {
  query: string;
  setQuery: (v: string) => void;
  selectedCategory: string;
  setSelectedCategory: (v: string) => void;
  categories: string[];
  filteredWorlds: WorldListItem[];
  spotlightWorlds: WorldListItem[];
}

export function MobileView({
  query,
  setQuery,
  selectedCategory,
  setSelectedCategory,
  categories,
  filteredWorlds,
  spotlightWorlds,
}: MobileViewProps) {
  const t = useTranslations("discoverPage");
  const [viewMode, setViewMode] = useState<"list" | "grid">("list");

  const showingSpotlight = !query && selectedCategory === "全部" && spotlightWorlds.length > 0;

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

      {/* Spotlight */}
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
