"use client";

import { useState, useEffect, useRef } from "react";
import Link from "next/link";
import { motion } from "motion/react";
import {
  ArrowRight,
  ChevronDown,
  PenLine,
  Play,
} from "lucide-react";
import { useTranslations } from "next-intl";

import { LangChip } from "@/components/LangChip";
import { ProductNav } from "@/components/ProductNav";
import { LV_EASE, lvStaggerContainer, lvStaggerItem } from "@/lib/motion";

const COPYRIGHT_YEAR = 2026;
const HERO_VIDEO = "/hero-sky-1440.mp4";
const HERO_POSTER = "/hero-sky-poster.jpg";
const GRAIN =
  "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='140' height='140'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='2' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E\")";

export default function HomePage() {
  const t = useTranslations("landing");
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const applyMotionPreference = () => {
      if (mq.matches) {
        video.pause();
      } else {
        void video.play().catch(() => {});
      }
    };

    applyMotionPreference();
    mq.addEventListener("change", applyMotionPreference);
    return () => mq.removeEventListener("change", applyMotionPreference);
  }, []);

  const modeCards = [
    {
      key: "script",
      href: "/discover?mode=script",
      eyebrow: t("modes.scriptEyebrow"),
      title: t("modes.scriptTitle"),
      body: t("modes.scriptBullet2"),
      cta: t("modes.scriptCta"),
      image: "https://images.unsplash.com/photo-1426604966848-d7adac402bff?w=1600&q=82&auto=format&fit=crop",
    },
    {
      key: "free",
      href: "/discover?mode=free",
      eyebrow: t("modes.freeEyebrow"),
      title: t("modes.freeTitle"),
      body: t("modes.freeBullet2"),
      cta: t("modes.freeCta"),
      image: "https://images.unsplash.com/photo-1470071459604-3b5ec3a7fe05?w=1600&q=82&auto=format&fit=crop",
    },
  ];

  return (
    <main className="lv-home lv-theme">
      <ProductNav variant="transparent" active="home" />

      <section className="lv-home-hero">
        <MobileChrome />
        <div className="lv-home-hero-media" aria-hidden>
          <video
            ref={videoRef}
            autoPlay
            loop
            muted
            playsInline
            preload="metadata"
            poster={HERO_POSTER}
            className="lv-home-hero-video"
          >
            <source src={HERO_VIDEO} type="video/mp4" />
          </video>
          <div className="lv-home-hero-wash" />
          <div className="lv-home-hero-grain" style={{ backgroundImage: GRAIN }} />
          <div className="lv-home-hero-vignette" />
        </div>

        <div className="lv-home-hero-content">
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, ease: LV_EASE }}
            className="lv-home-kicker lv-t-caps"
            aria-label={`${t("engineOnline")} · ${t("brandLine")}`}
          >
            <span className="lv-home-engine-dot" aria-hidden />
            <span>{t("brandLine")}</span>
          </motion.div>

          <motion.h1
            initial={{ opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.08, ease: LV_EASE }}
            className="lv-home-title lv-t-display"
          >
            {t("heroTitle")}
            <em>{t("heroTitleAccent")}</em>
          </motion.h1>

          <motion.p
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.24, ease: LV_EASE }}
            className="lv-home-lead lv-t-narrative"
          >
            {t.rich("heroBody", {
              scripted: (chunks) => <strong>{chunks}</strong>,
              free: (chunks) => <strong>{chunks}</strong>,
            })}
          </motion.p>

          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.34, ease: LV_EASE }}
            className="lv-home-actions"
          >
            <Link href="/discover" className="lv-btn lv-btn-primary lv-btn-lg lv-home-primary">
              <Play size={15} fill="currentColor" strokeWidth={0} />
              {t("ctaStart")}
            </Link>
            <Link href="/workshop" className="lv-btn lv-btn-lg lv-home-secondary">
              <PenLine size={15} />
              {t("ctaWorkshop")}
            </Link>
          </motion.div>
        </div>

        <a href="#modes" className="lv-home-scroll-cue" aria-label={t("scrollCue")}>
          <span className="lv-t-caps">{t("scrollCue")}</span>
          <ChevronDown size={18} strokeWidth={1.7} />
        </a>
      </section>

      <section id="modes" className="lv-home-section lv-home-modes">
        <div className="lv-home-inner">
          <motion.p
            className="lv-home-section-brief lv-t-narrative"
            initial={{ opacity: 0, y: 18 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, amount: 0.45 }}
            transition={{ duration: 0.45, ease: LV_EASE }}
          >
            {t("modes.body")}
          </motion.p>

          <div className="lv-home-mode-showcase">
            <motion.div
              className="lv-home-mode-grid"
              variants={lvStaggerContainer}
              initial="hidden"
              whileInView="show"
              viewport={{ once: true, amount: 0.25 }}
            >
              {modeCards.map((card) => (
                <motion.div key={card.key} variants={lvStaggerItem}>
                  <Link href={card.href} className="lv-home-mode-card">
                    <span
                      className="lv-home-mode-image"
                      style={{ backgroundImage: `url(${card.image})` }}
                      aria-hidden
                    />
                    <span className="lv-home-mode-scrim" aria-hidden />
                    <div className="lv-home-mode-copy">
                      <span className="lv-home-mode-eyebrow">{card.eyebrow}</span>
                      <h3>{card.title}</h3>
                      <p>{card.body}</p>
                      <span className="lv-home-card-cta">
                        {card.cta}
                        <ArrowRight size={14} />
                      </span>
                    </div>
                  </Link>
                </motion.div>
              ))}
            </motion.div>
          </div>
        </div>

        <a href="#live-demo" className="lv-home-scroll-cue lv-home-cue-section" aria-label={t("scrollCue")}>
          <ChevronDown size={18} strokeWidth={1.7} />
        </a>
      </section>

      <section id="live-demo" className="lv-home-section lv-home-live">
        <div className="lv-home-inner lv-home-live-stack">
          <motion.p
            className="lv-home-section-brief lv-t-narrative"
            initial={{ opacity: 0, y: 18 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, amount: 0.4 }}
            transition={{ duration: 0.45, ease: LV_EASE }}
          >
            {t("steps.body")}
          </motion.p>

          <motion.div
            className="lv-home-demo-wrap"
            initial={{ opacity: 0, y: 22 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, amount: 0.25 }}
            transition={{ duration: 0.55, ease: LV_EASE }}
          >
            <LivePlayDemo />
          </motion.div>
        </div>
      </section>

      <footer className="lv-home-footer">
        <div className="lv-home-footer-inner">
          <span className="lv-t-meta">© {COPYRIGHT_YEAR} InkWild Studio</span>
          <nav className="lv-t-meta" aria-label="Footer">
            <Link href="/discover">{t("footer.links.discover")}</Link>
            <Link href="/workshop">{t("footer.links.workshop")}</Link>
            <Link href="/history">{t("footer.links.history")}</Link>
          </nav>
        </div>
      </footer>

      <style jsx global>{`
        .lv-home {
          min-height: 100dvh;
          overflow-x: hidden;
          background: var(--lv-bg);
          color: var(--lv-ink);
        }

        /* 桌面：整页按屏吸附滚动（一次一页）。沿用 .landing-v2 约定：
           容器自身做滚动 + mandatory snap；ProductNav / BottomTabBar 都是 fixed，不受影响。
           移动端不开（分屏内容按高度自适应，强吸附会困住超高的那屏）。 */
        @media (min-width: 769px) {
          .lv-home {
            height: 100dvh;
            overflow-y: auto;
            scroll-snap-type: y mandatory;
            scroll-behavior: smooth;
          }
        }

        @keyframes lv-home-cue {
          0%, 100% { transform: translate(-50%, 0); opacity: 0.68; }
          50% { transform: translate(-50%, 6px); opacity: 1; }
        }

        .lv-home-hero {
          position: relative;
          min-height: 100dvh;
          isolation: isolate;
          overflow: hidden;
          display: grid;
          align-items: center;
          padding: 112px var(--lv-pad-x) 96px;
          scroll-snap-align: start;
          scroll-snap-stop: always;
        }

        .lv-home-hero-media,
        .lv-home-hero-wash,
        .lv-home-hero-grain,
        .lv-home-hero-vignette {
          position: absolute;
          inset: 0;
        }

        .lv-home-hero-media {
          z-index: -1;
          overflow: hidden;
          background: var(--lv-bg-stage);
        }

        .lv-home-hero-video {
          position: absolute;
          inset: 0;
          z-index: 0;
          width: 100%;
          height: 100%;
          object-fit: cover;
          object-position: center;
          filter: brightness(1.02) saturate(1.04) contrast(1.03);
        }

        .lv-home-title em {
          font-style: normal;
          color: rgba(245,242,235,0.88);
        }

        /* 视频保留电影质感，叠层只负责文字可读性和与下屏暗底衔接。 */
        .lv-home-hero-wash {
          background:
            linear-gradient(180deg, rgba(5,5,7,0.62) 0%, rgba(5,5,7,0.14) 16%, transparent 34%,
              transparent 52%, rgba(5,5,7,0.4) 78%, rgba(5,5,7,0.82) 100%),
            radial-gradient(112% 78% at 50% 48%, rgba(5,5,7,0.38) 0%, rgba(5,5,7,0.18) 42%, rgba(5,5,7,0.06) 68%, transparent 100%);
        }

        .lv-home-hero-grain {
          background-size: 140px 140px;
          opacity: 0.05;
          mix-blend-mode: soft-light;
          pointer-events: none;
        }

        .lv-home-hero-vignette {
          background: radial-gradient(120% 90% at 50% 42%, transparent 52%, rgba(3,3,4,0.55) 100%);
        }

        .lv-home-hero-content {
          position: relative;
          z-index: 2;
          width: min(820px, 100%);
          margin: 0 auto;
          text-align: center;
        }

        .lv-home-kicker {
          display: inline-flex;
          align-items: center;
          gap: 9px;
          color: rgba(245,242,235,0.74);
          font-family: "Inter", "PingFang SC", "Noto Sans SC", system-ui, sans-serif;
          font-weight: 500;
          text-shadow: 0 2px 16px rgba(0,0,0,0.62);
        }

        .lv-home-engine-dot {
          width: 7px;
          height: 7px;
          flex: 0 0 auto;
          border-radius: 50%;
          background: var(--lv-success);
          box-shadow: 0 0 0 3px rgba(127, 176, 145, 0.14), 0 0 16px rgba(127, 176, 145, 0.5);
        }

        .lv-theme .lv-home-title {
          margin-top: 20px;
          max-width: none;
          color: var(--lv-ink);
          font-family: "Source Han Serif SC", "Noto Serif SC", "Songti SC", STSong, "SimSun", serif;
          font-size: clamp(28px, 3.2vw, 44px);
          font-weight: 400;
          line-height: 1.18;
          letter-spacing: 0.025em;
          white-space: nowrap;
          text-shadow: 0 4px 30px rgba(0,0,0,0.66), 0 2px 8px rgba(0,0,0,0.5);
        }

        .lv-home-lead {
          max-width: 690px;
          margin: 24px auto 0;
          color: rgba(245,242,235,0.82);
          font-family: "Inter", "PingFang SC", "Noto Sans SC", system-ui, sans-serif;
          font-size: clamp(14px, 1vw, 16px);
          line-height: 1.85;
          letter-spacing: 0.01em;
          text-shadow: 0 2px 18px rgba(0,0,0,0.7);
        }

        .lv-home-lead strong {
          color: var(--lv-ink);
          font-weight: 500;
        }

        .lv-home-actions {
          display: flex;
          flex-wrap: wrap;
          justify-content: center;
          gap: var(--lv-s-3);
          margin-top: 34px;
        }

        .lv-home-actions .lv-btn {
          box-sizing: border-box;
        }

        .lv-home-primary,
        .lv-home-secondary {
          min-width: 148px;
          max-width: 100%;
          justify-content: center;
          text-decoration: none;
        }

        .lv-home-secondary {
          background: rgba(8,8,10,0.22);
          border-color: rgba(245,242,235,0.26);
          backdrop-filter: blur(10px);
          -webkit-backdrop-filter: blur(10px);
        }

        .lv-home-primary:hover,
        .lv-home-secondary:hover {
          transform: translateY(-1px);
          box-shadow: 0 14px 34px rgba(0,0,0,0.62);
        }

        .lv-home a:focus-visible,
        .lv-home button:focus-visible {
          outline: 2px solid var(--lv-accent);
          outline-offset: 3px;
        }

        .lv-home-scroll-cue {
          position: absolute;
          left: 50%;
          bottom: 28px;
          z-index: 2;
          display: inline-flex;
          flex-direction: column;
          align-items: center;
          gap: 8px;
          min-width: 52px;
          min-height: 44px;
          color: rgba(245,242,235,0.74);
          text-decoration: none;
          text-shadow: 0 2px 14px rgba(0,0,0,0.6);
          animation: lv-home-cue 1.9s ease-in-out infinite;
          transition: color var(--lv-dur-fast) var(--lv-ease);
        }

        .lv-home-scroll-cue:hover {
          color: var(--lv-ink);
        }

        .lv-home-section {
          min-height: 100dvh;
          display: flex;
          align-items: center;
          padding: 76px var(--lv-pad-x);
          border-top: 1px solid rgba(255,255,255,0.035);
          position: relative;
          isolation: isolate;
          overflow: hidden;
          scroll-snap-align: start;
          scroll-snap-stop: always;
        }

        .lv-home-modes,
        .lv-home-live {
          background: var(--lv-bg-stage);
          color: var(--lv-ink);
        }

        .lv-home-modes::before,
        .lv-home-live::before,
        .lv-home-modes::after,
        .lv-home-live::after {
          content: "";
          position: absolute;
          inset: 0;
          pointer-events: none;
          z-index: 0;
        }

        .lv-home-modes::before,
        .lv-home-live::before {
          inset: 0;
          background:
            radial-gradient(42% 34% at 24% 22%, rgba(245,242,235,0.075), transparent 72%),
            radial-gradient(46% 36% at 76% 66%, rgba(245,242,235,0.055), transparent 74%),
            linear-gradient(180deg, rgba(255,255,255,0.012), transparent 34%, rgba(255,255,255,0.01));
          opacity: 1;
        }

        .lv-home-modes::after,
        .lv-home-live::after {
          background:
            radial-gradient(92% 72% at 50% 42%, rgba(8,8,10,0.08), rgba(8,8,10,0.5) 70%, rgba(8,8,10,0.82) 100%),
            linear-gradient(180deg, rgba(8,8,10,0.74) 0%, rgba(8,8,10,0.48) 48%, rgba(8,8,10,0.82) 100%);
        }

        .lv-home-inner {
          position: relative;
          z-index: 1;
          width: 100%;
          max-width: var(--lv-max-w);
          margin: 0 auto;
        }

        .lv-home-section-head {
          max-width: 680px;
        }

        .lv-home-section-head > .lv-t-caps {
          margin-bottom: 12px;
          color: var(--lv-ink-3);
        }

        .lv-home-section-title {
          margin: 0;
          color: var(--lv-ink);
          font-family: var(--lv-font-serif);
          font-size: clamp(20px, 2vw, 26px);
          font-weight: 500;
          line-height: 1.2;
          letter-spacing: 0.005em;
        }

        .lv-home-section-brief {
          max-width: 720px;
          margin: 0 auto;
          color: var(--lv-ink-3);
          text-align: center;
        }

        .lv-home-modes .lv-home-inner {
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: var(--lv-s-8);
        }

        .lv-home-modes .lv-home-section-head {
          margin: 0 auto;
          max-width: 560px;
          text-align: center;
        }

        .lv-home-mode-showcase {
          display: flex;
          justify-content: center;
          width: 100%;
        }

        .lv-home-mode-grid {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: var(--lv-s-6);
          width: 100%;
          max-width: 860px;
        }

        .lv-home-mode-card {
          position: relative;
          display: flex;
          flex-direction: column;
          justify-content: flex-end;
          min-height: clamp(280px, 33vh, 340px);
          padding: 0;
          border-radius: var(--lv-r-card);
          background: var(--lv-bg-1);
          border: 1px solid rgba(255,255,255,0.10);
          box-shadow: 0 22px 64px rgba(0,0,0,0.48);
          color: var(--lv-ink);
          text-decoration: none;
          height: 100%;
          overflow: hidden;
          isolation: isolate;
          transition:
            transform var(--lv-dur-fast) var(--lv-ease),
            border-color var(--lv-dur-fast) var(--lv-ease),
            box-shadow var(--lv-dur-fast) var(--lv-ease);
        }

        .lv-home-mode-card:hover {
          transform: translateY(-4px);
          border-color: rgba(255,255,255,0.18);
          box-shadow: 0 30px 82px rgba(0,0,0,0.62);
        }

        .lv-home-mode-image,
        .lv-home-mode-scrim {
          position: absolute;
          inset: 0;
        }

        .lv-home-mode-image {
          z-index: -2;
          background-size: cover;
          background-position: center;
          transform: scale(1.03);
          transition: transform 520ms var(--lv-ease), filter 520ms var(--lv-ease);
        }

        .lv-home-mode-card:hover .lv-home-mode-image {
          transform: scale(1.08);
          filter: saturate(1.03);
        }

        .lv-home-mode-scrim {
          z-index: -1;
          background:
            linear-gradient(180deg, rgba(5,5,7,0.08) 0%, rgba(5,5,7,0.12) 34%, rgba(5,5,7,0.62) 72%, rgba(5,5,7,0.94) 100%),
            linear-gradient(90deg, rgba(5,5,7,0.28) 0%, transparent 58%);
        }

        .lv-home-mode-copy {
          min-width: 0;
          display: flex;
          flex-direction: column;
          justify-content: flex-end;
          min-height: inherit;
          padding: 24px;
        }

        .lv-home-mode-eyebrow {
          display: inline-flex;
          align-items: center;
          gap: 9px;
          color: rgba(245,242,235,0.78);
          font-size: var(--lv-t-meta);
          font-weight: 500;
          line-height: 1.4;
          text-shadow: 0 2px 12px rgba(0,0,0,0.62);
        }

        .lv-home-mode-eyebrow::before {
          content: "";
          width: 6px;
          height: 6px;
          border-radius: 50%;
          background: rgba(245,242,235,0.66);
          box-shadow: 0 0 0 3px rgba(245,242,235,0.08);
        }

        .lv-home-mode-card h3 {
          margin-top: 12px;
          color: var(--lv-ink);
          font-family: var(--lv-font-serif);
          font-size: clamp(22px, 2.1vw, 30px);
          font-weight: 500;
          line-height: 1.14;
          letter-spacing: 0.005em;
          text-shadow: 0 4px 28px rgba(0,0,0,0.66);
        }

        .lv-home-mode-card p {
          max-width: 36ch;
          margin-top: 10px;
          color: rgba(245,242,235,0.82);
          font-size: var(--lv-t-body);
          line-height: 1.7;
          text-shadow: 0 2px 16px rgba(0,0,0,0.68);
        }

        .lv-home-card-cta {
          display: inline-flex;
          align-items: center;
          gap: 8px;
          margin-top: var(--lv-s-4);
          padding-top: 0;
          color: var(--lv-ink);
          font-size: var(--lv-t-body);
          font-weight: 500;
          text-shadow: 0 2px 14px rgba(0,0,0,0.62);
        }

        .lv-home-card-cta svg {
          transition: transform var(--lv-dur-fast) var(--lv-ease);
          color: var(--lv-ink-3);
        }

        .lv-home-mode-card:hover .lv-home-card-cta svg {
          transform: translateX(3px);
          color: var(--lv-ink);
        }

        .lv-home-live-stack {
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: var(--lv-s-6);
        }

        .lv-home-live-stack .lv-home-section-head {
          margin: 0 auto;
          max-width: 560px;
          text-align: center;
        }

        .lv-home-demo-wrap {
          min-width: 0;
          max-width: 900px;
          position: relative;
          width: 100%;
        }

        .lv-home-demo-wrap::before {
          content: none;
        }

        /* ───────── 三屏：实时响应区 demo ───────── */
        .lv-live {
          border-radius: var(--lv-r-card);
          border: 1px solid rgba(255, 255, 255, 0.08);
          background:
            linear-gradient(rgba(255,255,255,0.018) 1px, transparent 1px),
            linear-gradient(90deg, rgba(255,255,255,0.014) 1px, transparent 1px),
            rgba(10, 10, 12, 0.82);
          background-size: 28px 28px, 28px 28px, auto;
          box-shadow: var(--lv-card-shadow-hover), inset 0 1px 0 rgba(255,255,255,0.035);
          overflow: hidden;
        }
        .lv-live-slate {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 14px;
          padding: 14px 22px;
          border-bottom: 1px solid rgba(255, 255, 255, 0.06);
          background: linear-gradient(180deg, rgba(255,255,255,0.018), transparent);
        }
        .lv-live-ctx {
          display: flex;
          gap: 16px;
          flex-wrap: wrap;
          font-family: var(--lv-font-mono);
          font-size: 11px;
          letter-spacing: 0.04em;
          color: var(--lv-ink-3);
        }
        .lv-live-ctx b { color: var(--lv-ink); font-weight: 500; }
        .lv-live-status {
          flex: 0 0 auto;
          display: inline-flex;
          align-items: center;
          gap: 7px;
          color: var(--lv-ink-3);
          padding: 4px 11px;
          border-radius: var(--lv-r-pill);
          border: 1px solid rgba(255,255,255,0.08);
          font-family: var(--lv-font-mono);
          font-size: 10px;
          letter-spacing: 0.08em;
          text-transform: uppercase;
          transition: all var(--lv-dur-fast) var(--lv-ease);
        }
        .lv-live-status i {
          width: 6px; height: 6px; border-radius: 50%;
          background: var(--lv-ink-4);
        }
        .lv-live-status.on {
          color: var(--lv-ink);
          border-color: rgba(255,255,255,0.16);
          background: rgba(255,255,255,0.045);
        }
        .lv-live-status.on i {
          background: var(--lv-ink-2);
          animation: lv-live-pulse 1.4s ease-in-out infinite;
        }
        .lv-live-status.updated {
          color: var(--lv-ink-2);
          border-color: rgba(255,255,255,0.14);
          background: rgba(255,255,255,0.035);
        }
        .lv-live-status.updated i {
          background: var(--lv-success);
        }
        .lv-live-grid {
          display: grid;
          grid-template-columns: minmax(0, 1fr) 260px minmax(0, 1fr);
          gap: 1px;
          background: rgba(255,255,255,0.055);
          min-height: 300px;
        }
        .lv-live-panel {
          min-width: 0;
          background: rgba(8,8,10,0.72);
          padding: 24px;
          display: flex;
          flex-direction: column;
          justify-content: space-between;
          gap: var(--lv-s-4);
        }
        .lv-live-panel-label {
          display: inline-flex;
          align-items: center;
          gap: 8px;
          color: var(--lv-ink-3);
          font-family: var(--lv-font-mono);
          font-size: var(--lv-t-micro);
          font-weight: 500;
          letter-spacing: 0.16em;
          text-transform: uppercase;
        }
        .lv-live-panel-label::before {
          content: "";
          width: 5px;
          height: 5px;
          border-radius: 50%;
          background: var(--lv-ink-3);
        }
        .lv-live-panel-label.on::before {
          background: var(--lv-ink-2);
        }
        .lv-live-you-text {
          color: var(--lv-ink-2);
          font-style: italic;
          font-family: var(--lv-font-serif);
          font-size: var(--lv-t-narrative);
          line-height: 1.72;
          min-height: 5.2em;
          margin: 0;
        }
        .lv-live-narr {
          color: var(--lv-ink);
          font-family: var(--lv-font-sans);
          font-size: var(--lv-t-body);
          line-height: 1.85;
          min-height: 8.4em;
          white-space: pre-wrap;
        }
        .lv-live-placeholder {
          color: var(--lv-ink-4);
        }
        .lv-live-caret {
          display: inline-block;
          width: 6px;
          height: 1.05em;
          margin-left: 3px;
          vertical-align: -0.15em;
          border-radius: 2px;
          background: var(--lv-ink-2);
          animation: lv-live-blink 1.2s steps(1) infinite;
        }
        .lv-live-trace {
          display: flex;
          flex-direction: column;
          gap: 10px;
        }
        .lv-live-trace-current {
          display: none;
        }
        .lv-live-trace-row {
          display: grid;
          grid-template-columns: 16px 1fr;
          gap: 10px;
          align-items: start;
          color: var(--lv-ink-3);
          font-size: var(--lv-t-meta);
          line-height: 1.55;
          transition: color var(--lv-dur-fast) var(--lv-ease);
        }
        .lv-live-trace-row::before {
          content: "";
          width: 6px;
          height: 6px;
          margin-top: 6px;
          border-radius: 50%;
          background: var(--lv-ink-4);
          box-shadow: 0 0 0 1px rgba(255,255,255,0.08);
        }
        .lv-live-trace-row.done {
          color: var(--lv-ink-3);
        }
        .lv-live-trace-row.done::before {
          background: var(--lv-ink-3);
        }
        .lv-live-trace-row.active {
          color: var(--lv-ink);
        }
        .lv-live-trace-row.active::before {
          background: var(--lv-ink-2);
          animation: lv-live-pulse 1.4s ease-in-out infinite;
        }
        .lv-live-trace-row.done {
          color: rgba(245, 242, 235, 0.34);
        }
        .lv-live-trace-row.done::before {
          background: rgba(245, 242, 235, 0.22);
          box-shadow: none;
        }

        @keyframes lv-live-blink { 0%, 50% { opacity: 0.9; } 51%, 100% { opacity: 0.1; } }
        @keyframes lv-live-pulse { 0%, 100% { opacity: 0.5; transform: scale(0.9); } 50% { opacity: 1; transform: scale(1.15); } }

        .lv-home-mobile-chrome {
          display: none;
        }

        .lv-home-footer {
          padding: 30px var(--lv-pad-x) calc(30px + env(safe-area-inset-bottom, 0px));
          border-top: 1px solid rgba(255,255,255,0.04);
          scroll-snap-align: end;
        }

        .lv-home-footer-inner {
          max-width: var(--lv-max-w);
          margin: 0 auto;
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 16px;
          color: var(--lv-ink-4);
        }

        .lv-home-footer nav {
          display: flex;
          gap: 20px;
        }

        .lv-home-footer a {
          color: var(--lv-ink-3);
          text-decoration: none;
          transition: color var(--lv-dur-fast) var(--lv-ease);
        }

        .lv-home-footer a:hover {
          color: var(--lv-ink);
        }

        @media (prefers-reduced-motion: reduce) {
          .lv-home-scroll-cue,
          .lv-live-caret,
          .lv-live-trace-row.active::before,
          .lv-live-status.on i {
            animation: none !important;
          }
          .lv-home {
            scroll-snap-type: none;
            scroll-behavior: auto;
          }
        }

        @media (max-width: 768px) {
          .lv-home-mobile-chrome {
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            z-index: 10;
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: calc(env(safe-area-inset-top, 0px) + 14px) 20px 0;
          }

          .lv-home-mobile-brand {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            color: var(--lv-ink);
            text-decoration: none;
            font-family: "Source Han Serif SC", "Noto Serif SC", "Songti SC", STSong, serif;
            font-size: 20px;
            font-weight: 500;
            font-style: normal;
            letter-spacing: 0.02em;
          }

          .lv-home-hero {
            min-height: 88dvh;
            padding: 104px 20px 78px;
            align-items: end;
          }

          /* 移动端文字在底部：遮罩底部加权 */
          .lv-home-hero-wash {
            background:
              linear-gradient(180deg, rgba(8,8,10,0.08) 0%, transparent 30%, rgba(5,5,7,0.24) 62%, rgba(8,8,10,0.66) 92%, rgba(8,8,10,0.82) 100%);
          }

          .lv-home-hero-content {
            width: min(100%, calc(100vw - 40px));
            margin: 0;
            text-align: left;
            transform: none;
          }

          .lv-home-hero-content .lv-home-kicker,
          .lv-home-hero-content .lv-home-title,
          .lv-home-hero-content .lv-home-lead,
          .lv-home-hero-content .lv-home-actions {
            opacity: 1 !important;
            transform: none !important;
          }

          .lv-theme .lv-home-title {
            margin-top: 18px;
            font-size: clamp(27px, 7.2vw, 34px);
            line-height: 1.16;
            letter-spacing: 0;
            white-space: normal;
            text-wrap: balance;
          }

          .lv-home-lead {
            max-width: 340px;
            margin-left: 0;
            margin-right: 0;
            margin-top: 22px;
          }

          .lv-home-actions {
            display: grid;
            grid-template-columns: 1fr;
            width: min(100%, 340px);
            margin-top: 30px;
            justify-content: stretch;
          }

          .lv-home-primary,
          .lv-home-secondary {
            width: 100%;
            min-width: 0;
          }

          .lv-home-section {
            min-height: auto;
            padding: 56px 20px;
          }

          .lv-home-live {
            padding: 30px 14px 42px;
          }

          .lv-home-live-stack {
            gap: 14px;
          }

          .lv-home-live .lv-home-section-brief {
            max-width: 330px;
            font-size: 15px;
            line-height: 1.58;
          }

          .lv-home-cue-section {
            display: none;
          }

          .lv-home-hero > .lv-home-scroll-cue {
            display: none;
          }

          .lv-home-modes .lv-home-inner {
            flex-direction: column;
            gap: 24px;
          }

          .lv-home-mode-grid {
            grid-template-columns: 1fr;
            margin-top: 0;
            gap: var(--lv-s-4);
          }

          .lv-home-mode-card {
            min-height: clamp(220px, 31vh, 280px);
          }

          .lv-home-mode-copy {
            padding: 20px;
          }

          .lv-home-mode-card h3 {
            font-size: var(--lv-t-h2);
          }

          .lv-home-demo-wrap {
            max-width: none;
          }

          .lv-live {
            border-radius: 10px;
          }

          .lv-live-slate {
            align-items: center;
            flex-direction: row;
            gap: 10px;
            padding: 10px 12px;
          }

          .lv-live-ctx {
            min-width: 0;
            gap: 8px;
            font-size: 10px;
          }

          .lv-live-ctx span:nth-child(2) {
            display: none;
          }

          .lv-live-grid {
            grid-template-columns: 1fr;
            min-height: 0;
          }

          .lv-live-panel {
            min-height: auto;
            padding: 12px;
            gap: 10px;
          }

          .lv-live-panel-action {
            min-height: 92px;
          }

          .lv-live-panel-trace {
            padding: 9px 12px 11px;
          }

          .lv-live-panel-trace .lv-live-panel-label {
            display: none;
          }

          .lv-live-panel-narrative {
            min-height: 132px;
          }

          .lv-live-you-text,
          .lv-live-narr {
            min-height: auto;
          }

          .lv-live-trace {
            display: grid;
            grid-template-columns: repeat(5, minmax(0, 1fr));
            gap: 6px;
          }

          .lv-live-trace-row {
            display: block;
            height: 8px;
            font-size: 0;
            line-height: 0;
            color: transparent;
            overflow: hidden;
          }

          .lv-live-trace-row::before {
            display: block;
            width: 100%;
            height: 3px;
            margin-top: 2px;
            border-radius: 999px;
            background: rgba(245,242,235,0.14);
            box-shadow: none;
          }

          .lv-live-trace-row.done::before {
            background: rgba(245,242,235,0.26);
          }

          .lv-live-trace-row.active::before {
            background: var(--lv-ink);
          }

          .lv-live-trace-current {
            display: block;
            grid-column: 1 / -1;
            color: var(--lv-ink-3);
            font-size: 11px;
            line-height: 1.4;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
          }

          .lv-live-narr {
            max-height: 7.4em;
            overflow: hidden;
          }

          .lv-home-footer {
            padding-bottom: calc(86px + env(safe-area-inset-bottom, 0px));
          }

          .lv-home-footer-inner {
            align-items: flex-start;
            flex-direction: column-reverse;
          }
        }
      `}</style>
    </main>
  );
}

function MobileChrome() {
  return (
    <div className="lv-home-mobile-chrome">
      <Link href="/" className="lv-home-mobile-brand">
        InkWild
      </Link>
      <LangChip />
    </div>
  );
}

// ────────────────────────────────────────────────────────────────
// 三屏：实时响应区 demo —— 复刻真实游玩流程
//   玩家逐字输入 → 系统按真实里程碑 loading → 旁白逐字流式输出，3 回合循环
// ────────────────────────────────────────────────────────────────
interface DemoTurn {
  input: string;
  summary: string;
  npcs: string[];
  reply: string;
}

const DEMO_TURNS: DemoTurn[] = [
  {
    input: "我推开酒馆的门，目光扫过角落里那个戴皮帽的男人。",
    summary: "观察戴皮帽的男人",
    npcs: ["皮帽客", "酒馆老板"],
    reply:
      "门轴吱呀一声，二十几道目光同时落过来——又散开。\n只有靠窗那个戴皮帽的男人停下了筷子，左手食指上有一道新结的痂。",
  },
  {
    input: "我走过去假装找座位，余光记下他桌上的东西。",
    summary: "靠近并观察桌面",
    npcs: ["皮帽客"],
    reply:
      "他面前摆着半盏冷茶，和一张折了三折的船票，目的地那栏被指甲反复抠过。\n他没抬头，却用沙哑的声音开口：『雾天赶路，可不是什么好主意。』",
  },
  {
    input: "我在他对面坐下：『昨夜湖边出的事，你也在场吧？』",
    summary: "试探昨夜湖边的事",
    npcs: ["皮帽客"],
    reply:
      "他捏着茶盏的手指猛地收紧，茶水晃出一圈涟漪。\n良久，他才低声道：『有些事，知道得越多，离岸就越远。』",
  },
];

type Phase = "input" | "think" | "output" | "hold";

function LivePlayDemo() {
  const [turn, setTurn] = useState(0);
  const [phase, setPhase] = useState<Phase>("input");
  const [typedIn, setTypedIn] = useState("");
  const [typedOut, setTypedOut] = useState("");
  const [stage, setStage] = useState(0);

  const cur = DEMO_TURNS[turn];
  const milestones = [
    "接收你的行动",
    "体察各人对你的态度",
    `推演『${cur.summary}』`,
    `${cur.npcs.join("、")} 进入这一幕`,
    "落笔成文",
  ];

  // 玩家输入逐字
  useEffect(() => {
    if (phase !== "input") return;
    if (typedIn.length >= cur.input.length) {
      const t = setTimeout(() => setPhase("think"), 520);
      return () => clearTimeout(t);
    }
    const t = setTimeout(() => setTypedIn(cur.input.slice(0, typedIn.length + 1)), 40);
    return () => clearTimeout(t);
  }, [phase, typedIn, cur.input]);

  // 系统里程碑 loading
  useEffect(() => {
    if (phase !== "think") return;
    if (stage >= milestones.length - 1) {
      const t = setTimeout(() => setPhase("output"), 640);
      return () => clearTimeout(t);
    }
    const t = setTimeout(() => setStage((s) => s + 1), 560);
    return () => clearTimeout(t);
  }, [phase, stage, milestones.length]);

  // 旁白逐字流式输出
  useEffect(() => {
    if (phase !== "output") return;
    if (typedOut.length >= cur.reply.length) {
      const t = setTimeout(() => setPhase("hold"), 240);
      return () => clearTimeout(t);
    }
    const t = setTimeout(() => setTypedOut(cur.reply.slice(0, typedOut.length + 1)), 28);
    return () => clearTimeout(t);
  }, [phase, typedOut, cur.reply]);

  // 停留后进入下一回合（循环）
  useEffect(() => {
    if (phase !== "hold") return;
    const t = setTimeout(() => {
      const next = (turn + 1) % DEMO_TURNS.length;
      setTurn(next);
      setTypedIn("");
      setTypedOut("");
      setStage(0);
      setPhase("input");
    }, 2600);
    return () => clearTimeout(t);
  }, [phase, turn, cur]);

  const streaming = phase === "think" || phase === "output";
  const statusText = streaming ? "实时推演中" : phase === "hold" ? "世界已更新" : "等待行动";
  const traceClass = (index: number) => {
    if (phase === "think" && index === stage) return " active";
    if (phase === "input" && index === 0) return " active";
    if (phase === "output" || phase === "hold" || index < stage) return " done";
    return "";
  };

  return (
    <div className="lv-live">
      <div className="lv-live-slate">
        <div className="lv-live-ctx">
          <span>世界 <b>雾隐镇</b></span>
          <span>模式 <b>剧本</b></span>
          <span>角色 <b>外来旅人</b></span>
        </div>
        <span className={`lv-live-status ${streaming ? "on" : phase === "hold" ? "updated" : ""}`}>
          <i />
          {statusText}
        </span>
      </div>

      <div className="lv-live-grid">
        <div className="lv-live-panel lv-live-panel-action">
          <span className={`lv-live-panel-label${phase === "input" ? " on" : ""}`}>Action</span>
          <p className="lv-live-you-text">
            {typedIn}
            {phase === "input" && <span className="lv-live-caret" />}
          </p>
        </div>

        <div className="lv-live-panel lv-live-panel-trace">
          <span className={`lv-live-panel-label${phase === "think" ? " on" : ""}`}>Trace</span>
          <div className="lv-live-trace">
            <span className="lv-live-trace-current">
              {milestones[Math.min(stage, milestones.length - 1)]}
            </span>
            {milestones.map((item, index) => (
              <span
                key={item}
                className={`lv-live-trace-row${traceClass(index)}`}
              >
                {item}
              </span>
            ))}
          </div>
        </div>

        <div className="lv-live-panel lv-live-panel-narrative">
          <span className={`lv-live-panel-label${phase === "output" ? " on" : ""}`}>Narrative</span>
          <div className="lv-live-narr">
            {typedOut || <span className="lv-live-placeholder">等待推演结果写入...</span>}
            {phase === "output" && <span className="lv-live-caret" />}
          </div>
        </div>
      </div>

    </div>
  );
}
