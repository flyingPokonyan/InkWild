"use client";

import type { CSSProperties } from "react";

export interface CoverImage {
  url?: string | null;
  label: string;
  /** CSS aspect-ratio 表达，如 "16 / 9" / "3 / 4" / "2 / 3" */
  aspectRatio: string;
}

function parseRatio(ratio: string): number {
  const [w, h] = ratio.split("/").map((s) => Number(s.trim()));
  if (!w || !h) return 1;
  return w / h;
}

interface CoverFrameProps {
  image: CoverImage;
  /** 容器外 style，外层 flex/grid 用 */
  style?: CSSProperties;
}

/**
 * 单张封面框：image + 底部 caps 标签。
 * 容器宽度由父级控制，高度通过 aspect-ratio 自动推导。
 */
export function CoverFrame({ image, style }: CoverFrameProps) {
  return (
    <figure
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 6,
        margin: 0,
        minWidth: 0,
        ...style,
      }}
    >
      <div
        style={{
          width: "100%",
          aspectRatio: image.aspectRatio,
          background: "var(--lv-bg-2)",
          border: "1px solid var(--lv-line)",
          borderRadius: "var(--lv-r-card)",
          overflow: "hidden",
          position: "relative",
        }}
      >
        {image.url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={image.url}
            alt={image.label}
            style={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }}
          />
        ) : (
          <div
            className="lv-t-caps"
            style={{
              position: "absolute",
              inset: 0,
              display: "grid",
              placeItems: "center",
              color: "var(--lv-ink-4)",
            }}
          >
            NO IMAGE
          </div>
        )}
      </div>
      <figcaption
        className="lv-t-caps"
        style={{ color: "var(--lv-ink-3)", textAlign: "center" }}
      >
        {image.label}
      </figcaption>
    </figure>
  );
}

interface CoverDeckProps {
  images: CoverImage[];
}

/**
 * 多张封面横排。
 * - 各图按 aspect-ratio 比例分配 flex-grow → **等高**自动满足
 * - 永远单行，不滚条不换行（在容器宽度允许的窄屏下整体一起缩小）
 *
 * 单张时建议用 <CoverFrame> 直接控制宽度，不必走 deck。
 */
export function CoverDeck({ images }: CoverDeckProps) {
  return (
    <div
      style={{
        display: "flex",
        gap: "var(--lv-s-3)",
        alignItems: "flex-start",
        width: "100%",
      }}
    >
      {images.map((img, i) => (
        <CoverFrame
          key={i}
          image={img}
          style={{
            flex: `${parseRatio(img.aspectRatio)} 1 0`,
          }}
        />
      ))}
    </div>
  );
}
