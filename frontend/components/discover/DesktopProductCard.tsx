"use client";

import Link from "next/link";
import { Play } from "lucide-react";
import { useTranslations } from "next-intl";

import { LazyCover } from "@/components/ui/LazyCover";
import { ossThumb } from "@/lib/oss-image";
import type { WorldListItem } from "@/lib/types";
import { formatPlayCount, mockPlayCount } from "./world-ranking";

export function DesktopProductCard({ world }: { world: WorldListItem }) {
  const t = useTranslations("discoverPage");
  const img = ossThumb(world.cover_image, 600);
  const contextLabel = [world.genre, world.era].filter(Boolean).join(" · ") || t("general");
  const playCount = world.play_count > 0 ? world.play_count : mockPlayCount(world.id);

  return (
    <Link href={`/worlds/${world.id}`} className="product-card">
      <div className="product-card-frame">
        <LazyCover url={img} aria-hidden className="product-card-cover" />
        <div className="product-card-play-overlay">
          <div className="product-card-play-btn">
            <Play size={22} fill="currentColor" />
          </div>
        </div>
      </div>
      <div className="product-card-info">
        <div className="product-card-kicker">{contextLabel}</div>
        <h3>{world.name}</h3>
        <div className="product-card-meta">
          {t("exploreCount", { count: formatPlayCount(playCount) })}
        </div>
      </div>
    </Link>
  );
}
