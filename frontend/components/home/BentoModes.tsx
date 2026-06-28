"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { ArrowRight, PenLine, Compass, Sparkles } from "lucide-react";

const FREE_MODE_BG =
  "https://images.unsplash.com/photo-1542451542907-6cf80ff362d6?w=1600&q=82&auto=format&fit=crop";

const SCRIPT_CARD_1 =
  "https://images.unsplash.com/photo-1518709268805-4e9042af9f23?w=800&q=82&auto=format&fit=crop";
const SCRIPT_CARD_2 =
  "https://images.unsplash.com/photo-1534447677768-be436bb09401?w=800&q=82&auto=format&fit=crop";
const SCRIPT_CARD_3 =
  "https://images.unsplash.com/photo-1426604966848-d7adac402bff?w=800&q=82&auto=format&fit=crop";

export function BentoModes() {
  const t = useTranslations("landing");

  return (
    <div className="lv-bento-container">
      <div className="lv-bento-grid">
        {/* 左侧大区域：自由模式 */}
        <div className="lv-bento-card lv-bento-large">
          <Link href="/discover?mode=free" className="lv-bento-link">
            <div
              className="lv-bento-bg"
              style={{ backgroundImage: `url(${FREE_MODE_BG})` }}
              aria-hidden
            />
            <div className="lv-bento-vignette" />
            <div className="lv-bento-content">
              <span className="lv-bento-eyebrow">
                <Compass size={14} />
                {t("modes.freeEyebrow")}
              </span>
              <h2>{t("modes.freeTitle")}</h2>
              <p>{t("modes.freeBullet2")}</p>
              <div className="lv-bento-cta">
                {t("modes.freeCta")} <ArrowRight size={14} />
              </div>
            </div>
          </Link>
        </div>

        {/* 右上小区域：剧本模式 */}
        <div className="lv-bento-card lv-bento-card-script lv-bento-small-top">
          <Link href="/discover?mode=script" className="lv-bento-link">
            <div className="lv-bento-bg-dark" />

            {/* 剧本卡牌阵列 */}
            <div className="lv-bento-script-cards">
              <div
                className="lv-bento-script-card"
                style={{ backgroundImage: `url(${SCRIPT_CARD_1})`, transform: "rotate(-12deg) translateY(10px)" }}
              />
              <div
                className="lv-bento-script-card lv-bento-script-card-center"
                style={{ backgroundImage: `url(${SCRIPT_CARD_2})`, zIndex: 2 }}
              />
              <div
                className="lv-bento-script-card"
                style={{ backgroundImage: `url(${SCRIPT_CARD_3})`, transform: "rotate(12deg) translateY(10px)" }}
              />
            </div>

            <div className="lv-bento-vignette" />
            <div className="lv-bento-content">
              <span className="lv-bento-eyebrow">
                <Sparkles size={14} />
                {t("modes.scriptEyebrow")}
              </span>
              <h3>{t("modes.scriptTitle")}</h3>
              <p>{t("modes.scriptBullet2")}</p>
              <div className="lv-bento-cta">
                {t("modes.scriptCta")} <ArrowRight size={14} />
              </div>
            </div>
          </Link>
        </div>

        {/* 右下小区域：工坊 */}
        <div className="lv-bento-card lv-bento-small-bottom">
          <Link href="/workshop" className="lv-bento-link">
            <div className="lv-bento-bg-workshop">
              <div className="lv-bento-workshop-pattern" />
            </div>
            <div className="lv-bento-vignette" />
            <div className="lv-bento-content">
              <span className="lv-bento-eyebrow">
                <PenLine size={14} />
                {t("modes.workshopEyebrow")}
              </span>
              <h3>{t("modes.workshopTitle")}</h3>
              <p>{t("modes.workshopBody")}</p>
              <div className="lv-bento-cta">
                {t("modes.workshopCta")} <ArrowRight size={14} />
              </div>
            </div>
          </Link>
        </div>
      </div>

      <style jsx global>{`
        .lv-bento-container {
          width: 100%;
          max-width: 1200px;
          margin: 0 auto;
          padding: 0 var(--lv-pad-x);
        }

        .lv-bento-grid {
          display: grid;
          grid-template-columns: 6fr 4fr;
          grid-template-rows: 1fr 1fr;
          gap: 16px;
          width: 100%;
          height: clamp(500px, calc(100dvh - 360px), 620px);
        }

        @media (max-width: 1024px) {
          .lv-bento-grid {
            grid-template-columns: 1fr;
            grid-template-rows: auto auto auto;
            height: auto;
            max-height: none;
          }
        }

        .lv-bento-card {
          position: relative;
          border-radius: 24px;
          overflow: hidden;
          background: rgba(20, 20, 22, 0.4);
          box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.08);
          transition: transform 0.4s cubic-bezier(0.16, 1, 0.3, 1), box-shadow 0.4s ease;
        }

        .lv-bento-card:hover {
          transform: translateY(-4px) scale(1.01);
          box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.2), 0 20px 40px rgba(0, 0, 0, 0.4);
        }

        .lv-bento-large {
          grid-column: 1;
          grid-row: 1 / 3;
        }

        .lv-bento-small-top {
          grid-column: 2;
          grid-row: 1;
        }

        .lv-bento-small-bottom {
          grid-column: 2;
          grid-row: 2;
        }

        @media (max-width: 1024px) {
          .lv-bento-large, .lv-bento-small-top, .lv-bento-small-bottom {
            grid-column: 1;
            grid-row: auto;
            min-height: 400px;
          }
        }

        .lv-bento-link {
          display: block;
          width: 100%;
          height: 100%;
          text-decoration: none;
          color: inherit;
        }

        .lv-bento-bg,
        .lv-bento-bg-dark,
        .lv-bento-bg-workshop {
          position: absolute;
          inset: 0;
          z-index: 0;
          transition: transform 1.2s cubic-bezier(0.16, 1, 0.3, 1);
        }

        .lv-bento-bg {
          background-size: cover;
          background-position: center;
        }

        .lv-bento-bg-dark {
          background: linear-gradient(135deg, #16181c, #0a0b0d);
        }

        .lv-bento-bg-workshop {
          background: #000;
        }

        .lv-bento-workshop-pattern {
          position: absolute;
          inset: 0;
          background-image: radial-gradient(rgba(255,255,255,0.1) 1px, transparent 1px);
          background-size: 24px 24px;
          opacity: 0.3;
        }

        .lv-bento-card:hover .lv-bento-bg,
        .lv-bento-card:hover .lv-bento-bg-workshop {
          transform: scale(1.05);
        }

        .lv-bento-vignette {
          position: absolute;
          inset: 0;
          z-index: 1;
          background:
            linear-gradient(to top, rgba(0,0,0,0.80) 0%, rgba(0,0,0,0.18) 52%, rgba(0,0,0,0.04) 100%),
            radial-gradient(100% 64% at 50% 100%, rgba(0,0,0,0.24), transparent 72%);
          pointer-events: none;
        }

        .lv-bento-card-script .lv-bento-vignette {
          background:
            linear-gradient(to top, rgba(0,0,0,0.90) 0%, rgba(0,0,0,0.68) 34%, rgba(0,0,0,0.20) 68%, rgba(0,0,0,0.04) 100%),
            radial-gradient(72% 62% at 22% 84%, rgba(0,0,0,0.60), transparent 76%);
        }

        .lv-bento-content {
          position: absolute;
          inset: 0;
          z-index: 10;
          padding: 40px;
          display: flex;
          flex-direction: column;
          justify-content: flex-end;
          pointer-events: none;
        }

        .lv-bento-card-script .lv-bento-content {
          padding: 28px 30px;
        }

        @media (max-width: 768px) {
          .lv-bento-content {
            padding: 24px;
          }
        }

        .lv-bento-eyebrow {
          display: inline-flex;
          align-items: center;
          gap: 6px;
          font-family: var(--lv-font-sans);
          font-size: 11px;
          font-weight: 600;
          letter-spacing: 0.15em;
          text-transform: uppercase;
          color: rgba(255, 255, 255, 0.6);
          margin-bottom: 12px;
        }

        .lv-bento-content h2 {
          font-family: var(--lv-font-serif);
          font-size: clamp(34px, 3vw, 40px);
          font-weight: 400;
          color: #fff;
          margin: 0 0 12px;
          line-height: 1.1;
        }

        .lv-bento-content h3 {
          font-family: var(--lv-font-serif);
          font-size: clamp(24px, 2vw, 27px);
          font-weight: 400;
          color: #fff;
          margin: 0 0 12px;
          line-height: 1.2;
        }

        .lv-bento-content p {
          font-family: var(--lv-font-sans);
          font-size: 15px;
          color: rgba(255, 255, 255, 0.7);
          line-height: 1.6;
          margin: 0 0 24px;
          max-width: 480px;
        }

        .lv-bento-cta {
          display: inline-flex;
          align-items: center;
          gap: 8px;
          font-family: var(--lv-font-sans);
          font-size: 14px;
          font-weight: 500;
          color: #fff;
          background: rgba(255,255,255,0.1);
          padding: 10px 20px;
          border-radius: 100px;
          align-self: flex-start;
          backdrop-filter: blur(10px);
          border: 1px solid rgba(255,255,255,0.1);
          transition: background 0.2s;
        }

        .lv-bento-card:hover .lv-bento-cta {
          background: rgba(255,255,255,0.2);
        }

        /* 剧本卡牌排版 */
        .lv-bento-script-cards {
          position: absolute;
          inset: 8px 14px 36% 14px;
          z-index: 1;
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 10px;
          perspective: 1000px;
          opacity: 0.9;
          transform: translateY(-14px) scale(0.86);
          transition: opacity 0.4s ease, transform 0.4s cubic-bezier(0.16, 1, 0.3, 1);
        }

        .lv-bento-card-script:hover .lv-bento-script-cards {
          opacity: 0.98;
          transform: translateY(-18px) scale(0.9);
        }

        .lv-bento-script-card {
          width: 110px;
          aspect-ratio: 2.5 / 4;
          background-size: cover;
          background-position: center;
          border-radius: 8px;
          box-shadow: inset 0 0 0 1px rgba(255,255,255,0.2), 0 10px 20px rgba(0,0,0,0.5);
          transition: transform 0.4s cubic-bezier(0.16, 1, 0.3, 1), box-shadow 0.4s ease;
        }

        .lv-bento-script-card-center {
          width: 128px;
          transform: translateY(-10px);
          box-shadow: inset 0 0 0 1px rgba(255,255,255,0.3), 0 15px 30px rgba(0,0,0,0.6);
        }

        .lv-bento-card:hover .lv-bento-script-card:first-child {
          transform: translateY(-15px) rotate(-18deg) scale(1.05);
        }

        .lv-bento-card:hover .lv-bento-script-card-center {
          transform: translateY(-25px) scale(1.1) rotate(0deg);
        }

        .lv-bento-card:hover .lv-bento-script-card:last-child {
          transform: translateY(-15px) rotate(18deg) scale(1.05);
        }
      `}</style>
    </div>
  );
}
