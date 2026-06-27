"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { motion } from "motion/react";
import { Play, Sparkles, ChevronLeft, ChevronRight } from "lucide-react";
import { useTranslations } from "next-intl";

import { difficultyLevel } from "@/lib/difficulty";
import { ossHero } from "@/lib/oss-image";
import type { WorldListItem } from "@/lib/types";

export function DesktopSpotlight({ worlds }: { worlds: WorldListItem[] }) {
  const t = useTranslations("discoverPage");
  const tWorlds = useTranslations("worlds");
  const [idx, setIdx] = useState(0);
  const wheelLockRef = useRef(0);
  const sectionRef = useRef<HTMLElement>(null);

  useEffect(() => {
    if (worlds.length <= 1) return;
    const timer = window.setInterval(() => {
      setIdx((i) => (i + 1) % worlds.length);
    }, 9000);
    return () => window.clearInterval(timer);
  }, [worlds.length]);

  // Native wheel listener with { passive: false } so preventDefault works
  useEffect(() => {
    const el = sectionRef.current;
    if (!el || worlds.length <= 1) return;

    const handleWheel = (event: globalThis.WheelEvent) => {
      if (Math.abs(event.deltaX) < 45 || Math.abs(event.deltaX) < Math.abs(event.deltaY) * 1.5) return;

      const now = Date.now();
      if (now - wheelLockRef.current < 650) return;
      wheelLockRef.current = now;
      event.preventDefault();

      setIdx((current) => {
        if (event.deltaX > 0) return (current + 1) % worlds.length;
        return (current - 1 + worlds.length) % worlds.length;
      });
    };

    el.addEventListener("wheel", handleWheel, { passive: false });
    return () => el.removeEventListener("wheel", handleWheel);
  }, [worlds.length]);

  const world = worlds[idx];
  if (!world) return null;

  const goToSpotlight = (direction: "prev" | "next") => {
    setIdx((current) => {
      if (direction === "prev") return (current - 1 + worlds.length) % worlds.length;
      return (current + 1) % worlds.length;
    });
  };

  return (
    <section
      ref={sectionRef}
      className="spotlight-section"
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
        const img = ossHero(w.hero_image || w.cover_image);
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
              backgroundPosition: "center 20%",
              opacity: i === idx ? 1 : 0,
              transition: "opacity 1400ms cubic-bezier(0.4, 0, 0.2, 1)",
              zIndex: 0,
            }}
          />
        );
      })}

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
      <div
        aria-hidden
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          right: 0,
          height: "140px",
          background:
            "linear-gradient(180deg, rgba(8,8,10,0.72) 0%, rgba(8,8,10,0.36) 55%, rgba(8,8,10,0) 100%)",
          zIndex: 1,
          pointerEvents: "none",
        }}
      />

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
            padding: "0 clamp(20px, 4vw, 60px)",
          }}
        >
          <motion.div
            key={world.id}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, ease: [0.2, 0.8, 0.2, 1] }}
            style={{ maxWidth: "640px" }}
          >
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

            <h1
              style={{
                margin: "14px 0 0",
                fontFamily: "var(--lv-font-serif)",
                fontSize: "var(--lv-t-h2)",
                fontWeight: 500,
                color: "var(--lv-ink)",
                lineHeight: 1.15,
              }}
            >
              {world.name}
            </h1>

            <div
              style={{
                marginTop: "20px",
                display: "flex",
                flexWrap: "wrap",
                gap: "12px",
                alignItems: "center",
                color: "var(--lv-ink-2)",
                fontSize: "13px",
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
            right: "clamp(20px, 4vw, 60px)",
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

      {worlds.length > 1 && (
        <>
          <button
            type="button"
            className="spotlight-nav-btn left"
            onClick={() => goToSpotlight("prev")}
            aria-label="上一张精选"
          >
            <ChevronLeft size={24} />
          </button>
          <button
            type="button"
            className="spotlight-nav-btn right"
            onClick={() => goToSpotlight("next")}
            aria-label="下一张精选"
          >
            <ChevronRight size={24} />
          </button>
        </>
      )}
    </section>
  );
}
