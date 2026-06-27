"use client";

import { useEffect, useRef, useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import type { LucideIcon } from "lucide-react";

import type { WorldListItem } from "@/lib/types";
import { DesktopProductCard } from "./DesktopProductCard";

export function DesktopCarouselRow({
  title,
  worlds,
  icon: Icon,
}: {
  title: string;
  worlds: WorldListItem[];
  icon?: LucideIcon;
}) {
  const railRef = useRef<HTMLDivElement>(null);
  const [canScrollLeft, setCanScrollLeft] = useState(false);
  const [canScrollRight, setCanScrollRight] = useState(false);
  const rowWorlds = worlds.slice(0, 8);

  useEffect(() => {
    const rail = railRef.current;
    if (!rail) return;

    const updateScrollState = () => {
      setCanScrollLeft(rail.scrollLeft > 4);
      setCanScrollRight(rail.scrollLeft + rail.clientWidth < rail.scrollWidth - 4);
    };

    updateScrollState();
    rail.addEventListener("scroll", updateScrollState, { passive: true });
    window.addEventListener("resize", updateScrollState);

    const resizeObserver = new ResizeObserver(updateScrollState);
    resizeObserver.observe(rail);

    return () => {
      rail.removeEventListener("scroll", updateScrollState);
      window.removeEventListener("resize", updateScrollState);
      resizeObserver.disconnect();
    };
  }, [rowWorlds.length]);

  if (rowWorlds.length < 4) return null;

  const scrollByPage = (direction: "left" | "right") => {
    const rail = railRef.current;
    if (!rail) return;
    const distance = Math.max(rail.clientWidth * 0.82, 360);
    rail.scrollBy({ left: direction === "right" ? distance : -distance, behavior: "smooth" });
  };

  return (
    <section className="product-row group">
      <div className="product-row-header">
        <h2>
          {Icon && <Icon size={18} className="row-icon" />} {title}
        </h2>
      </div>
      <div className="product-carousel-container" style={{ position: "relative" }}>
        <button
          type="button"
          className={`carousel-nav-btn left ${canScrollLeft ? "visible" : ""}`}
          onClick={() => scrollByPage("left")}
          disabled={!canScrollLeft}
          aria-label={`${title} 向左滚动`}
        >
          <ChevronLeft size={24} />
        </button>
        <div className="product-carousel" ref={railRef}>
          {rowWorlds.map((w) => (
            <DesktopProductCard key={w.id} world={w} />
          ))}
        </div>
        <button
          type="button"
          className={`carousel-nav-btn right ${canScrollRight ? "visible" : ""}`}
          onClick={() => scrollByPage("right")}
          disabled={!canScrollRight}
          aria-label={`${title} 向右滚动`}
        >
          <ChevronRight size={24} />
        </button>
      </div>
    </section>
  );
}
