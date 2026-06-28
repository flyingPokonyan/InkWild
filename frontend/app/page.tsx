"use client";

import { useEffect, useRef } from "react";
import Link from "next/link";
import { motion } from "motion/react";
import {
  ChevronDown,
  PenLine,
  Play,
} from "lucide-react";
import { BentoModes } from "@/components/home/BentoModes";
import { useTranslations } from "next-intl";

import { LangChip } from "@/components/LangChip";
import { ProductNav } from "@/components/ProductNav";
import { LV_EASE } from "@/lib/motion";

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
              <span className="lv-home-action-label">{t("ctaStart")}</span>
            </Link>
            <Link href="/workshop" className="lv-btn lv-btn-lg lv-home-secondary" aria-label={t("ctaWorkshop")}>
              <PenLine size={15} />
              <span className="lv-home-action-label">{t("ctaWorkshop")}</span>
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
          <p className="lv-home-section-brief lv-t-narrative">
            {t("modes.body")}
          </p>

          <div className="lv-home-bento-wrap">
            <BentoModes />
          </div>
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

        .lv-home-modes {
          background: var(--lv-bg-stage);
          color: var(--lv-ink);
        }

        .lv-home-modes::before,
        .lv-home-modes::after {
          content: "";
          position: absolute;
          inset: 0;
          pointer-events: none;
          z-index: 0;
        }

        .lv-home-modes::before {
          inset: 0;
          background:
            radial-gradient(42% 34% at 24% 22%, rgba(245,242,235,0.075), transparent 72%),
            radial-gradient(46% 36% at 76% 66%, rgba(245,242,235,0.055), transparent 74%),
            linear-gradient(180deg, rgba(255,255,255,0.012), transparent 34%, rgba(255,255,255,0.01));
          opacity: 1;
        }

        .lv-home-modes::after {
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
          gap: 0;
          transform: translateY(-18px);
        }

        .lv-home-modes .lv-home-section-head {
          margin: 0 auto;
          max-width: 560px;
          text-align: center;
        }

        .lv-home-bento-wrap {
          width: 100%;
          margin-top: 28px;
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
          .lv-home-scroll-cue {
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
            padding: calc(env(safe-area-inset-top, 0px) + 18px) 20px 0;
          }

          .lv-home-mobile-brand {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            color: var(--lv-ink);
            text-decoration: none;
            font-family: "Source Han Serif SC", "Noto Serif SC", "Songti SC", STSong, serif;
            font-size: 28px;
            font-weight: 500;
            font-style: normal;
            line-height: 1;
            letter-spacing: 0.01em;
            text-shadow: 0 3px 18px rgba(0,0,0,0.5);
          }

          .lv-home-hero {
            min-height: calc(100dvh - 72px);
            padding: calc(env(safe-area-inset-top, 0px) + 176px) 20px calc(104px + env(safe-area-inset-bottom, 0px));
            align-items: center;
          }

          .lv-home-hero-wash {
            background:
              linear-gradient(180deg, rgba(5,5,7,0.30) 0%, rgba(5,5,7,0.10) 28%, rgba(5,5,7,0.22) 58%, rgba(5,5,7,0.72) 100%),
              linear-gradient(90deg, rgba(5,5,7,0.54) 0%, rgba(5,5,7,0.22) 48%, rgba(5,5,7,0.08) 100%);
          }

          .lv-home-hero-vignette {
            background:
              radial-gradient(120% 78% at 64% 36%, transparent 36%, rgba(3,3,4,0.52) 100%),
              linear-gradient(180deg, transparent 70%, rgba(3,3,4,0.74) 100%);
          }

          .lv-home-hero-video {
            object-position: 58% center;
          }

          .lv-home-hero-content {
            width: min(100%, 340px);
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
            margin-top: 16px;
            max-width: 100%;
            font-size: clamp(24px, 6.2vw, 28px);
            line-height: 1.18;
            letter-spacing: 0.01em;
            white-space: nowrap;
          }

          .lv-home-title em {
            white-space: nowrap;
          }

          .lv-home-lead {
            max-width: 23em;
            margin-left: 0;
            margin-right: 0;
            margin-top: 16px;
            font-size: 13px;
            line-height: 1.72;
            letter-spacing: 0;
            color: rgba(245,242,235,0.82);
          }

          .lv-home-actions {
            display: grid;
            grid-template-columns: 1fr 1fr;
            align-items: center;
            width: min(100%, 320px);
            margin-top: 24px;
            justify-content: stretch;
            gap: 8px;
          }

          .lv-home-primary,
          .lv-home-secondary {
            min-width: 0;
          }

          .lv-home-actions .lv-btn {
            min-height: 44px;
            padding-inline: 12px;
            border-radius: 999px;
          }

          .lv-home-primary {
            width: 100%;
            font-size: 13px;
          }

          .lv-home-secondary {
            width: 100%;
            font-size: 13px;
            color: rgba(245,242,235,0.88);
            background: rgba(245,242,235,0.10);
            border-color: rgba(245,242,235,0.18);
            white-space: nowrap;
          }

          .lv-home-secondary svg {
            flex: 0 0 auto;
          }

          .lv-home-secondary .lv-home-action-label {
            display: inline;
          }

          .lv-home-section {
            min-height: auto;
            padding: 56px 20px;
          }

          .lv-home-hero > .lv-home-scroll-cue {
            display: none;
          }

          .lv-home-modes .lv-home-inner {
            flex-direction: column;
            gap: 24px;
            transform: none;
          }

          .lv-home-bento-wrap {
            margin-top: 0;
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
