"use client";

import { type ReactNode } from "react";

interface PreviewBlockProps {
  caps: string;
  children: ReactNode;
}

export function PreviewBlock({ caps, children }: PreviewBlockProps) {
  return (
    <section style={{ display: "flex", flexDirection: "column", gap: "var(--lv-s-3)" }}>
      <div className="lv-t-caps" style={{ color: "var(--lv-ink-3)" }}>
        {caps}
      </div>
      {children}
    </section>
  );
}

export function PreviewEmpty({ children }: { children: ReactNode }) {
  return (
    <div
      className="lv-t-meta"
      style={{
        padding: "var(--lv-s-4)",
        border: "1px dashed var(--lv-line)",
        borderRadius: "var(--lv-r-card)",
        textAlign: "center",
        color: "var(--lv-ink-4)",
      }}
    >
      {children}
    </div>
  );
}

interface CoverProps {
  src?: string | null;
  ratio: "3/2" | "21/9" | "2/3";
  alt: string;
}

export function PreviewCover({ src, ratio, alt }: CoverProps) {
  const aspect = ratio === "3/2" ? "3 / 2" : ratio === "21/9" ? "21 / 9" : "2 / 3";
  return (
    <div
      style={{
        position: "relative",
        width: "100%",
        aspectRatio: aspect,
        borderRadius: "var(--lv-r-card)",
        overflow: "hidden",
        background: "var(--lv-bg-2)",
        border: "1px solid var(--lv-line)",
      }}
    >
      {src ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={src}
          alt={alt}
          style={{
            width: "100%",
            height: "100%",
            objectFit: "cover",
            display: "block",
          }}
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
          NO COVER
        </div>
      )}
    </div>
  );
}
