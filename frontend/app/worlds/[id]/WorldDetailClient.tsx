"use client";

import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { motion } from "motion/react";
import { useTranslations } from "next-intl";

import { lvFastEase, lvFadeUp, LV_EASE } from "@/lib/motion";
import { compactMobileMeta, shouldShowWorldSynopsisToggle } from "@/lib/world-detail-mobile";
import { useWorldDetail } from "@/lib/api/worlds";
import { resolveExitHref, withReturn } from "@/lib/play-return";
import { difficultyLevel } from "@/lib/difficulty";
import { MobileTopBar, MobileIconButton } from "@/components/MobileTopBar";
import { LoadingPulse } from "@/components/ui/LoadingPulse";
import { ossHero, ossThumb } from "@/lib/oss-image";
import type { ScriptDTO, WorldDetail } from "@/lib/types";

/* 状态：加载中 — §10.1 中央 8px 暖金脉冲，无文字 */
function WorldLoadingState() {
  return (
    <div
      className="lv-h-dvh"
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "var(--lv-bg)",
      }}
    >
      <LoadingPulse variant="block" />
    </div>
  );
}

/* 状态：错误 — §10.3 6px 红点 + 一句 + retry */
function WorldErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  const t = useTranslations("worlds");
  const tc = useTranslations("common");
  return (
    <div
      className="lv-h-dvh"
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: "var(--lv-s-4)",
        padding: "var(--lv-s-6)",
        background: "var(--lv-bg)",
        textAlign: "center",
      }}
    >
      <h1 className="lv-t-h2" style={{ margin: 0 }}>
        {t("loadFailed")}
      </h1>
      <p className="lv-t-meta" style={{ margin: 0 }}>
        {message || t("loadFailedHint")}
      </p>
      <div style={{ display: "flex", gap: "var(--lv-s-3)", marginTop: "var(--lv-s-3)" }}>
        <button type="button" onClick={onRetry} className="lv-btn">
          {tc("retry")}
        </button>
        <Link href="/discover" className="lv-btn lv-btn-primary">
          {t("backToDiscover")}
        </Link>
      </div>
    </div>
  );
}

function firstGlyph(value: string): string {
  return Array.from(value.trim())[0] ?? "·";
}

function ScriptCover({ script }: { script: ScriptDTO }) {
  return (
    <div className="lv-world-script-cover">
      {script.cover_image ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={ossThumb(script.cover_image, 320)} alt="" className="lv-world-script-cover-img" />
      ) : (
        <div className="lv-world-script-cover-fallback" aria-hidden>
          {firstGlyph(script.name)}
        </div>
      )}
    </div>
  );
}

function ScriptMeta({ script }: { script: ScriptDTO }) {
  const t = useTranslations("worlds");
  return (
    <div className="lv-world-script-meta">
      <span className="lv-world-script-time">{script.estimated_time}</span>
      <span>{t("difficultyName", { level: difficultyLevel(script.difficulty) })}</span>
    </div>
  );
}

/* 剧本卡 = 通往剧本详情页的链接。桌面/移动共用，移动端追加 modifier class */
function ScriptCardLink({
  script,
  href,
  className,
}: {
  script: ScriptDTO;
  href: string;
  className?: string;
}) {
  return (
    <Link href={href} className={`lv-world-script-card${className ? ` ${className}` : ""}`}>
      <ScriptCover script={script} />
      <div className="lv-world-script-body">
        <h3 className="lv-world-script-title">{script.name}</h3>
        {script.description && <p className="lv-world-script-desc">{script.description}</p>}
        <ScriptMeta script={script} />
      </div>
    </Link>
  );
}

const DESKTOP_VISIBLE_SCRIPTS = 8;
const MOBILE_VISIBLE_SCRIPTS = 4;

export function WorldDetailClient() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const searchParams = useSearchParams();
  const returnTo = searchParams.get("return");
  const backHref = resolveExitHref(returnTo, "/discover");
  const t = useTranslations("worlds");
  const [scriptsExpanded, setScriptsExpanded] = useState(false);
  const { data: world, isLoading, isError, error, refetch } = useWorldDetail(id);

  if (isLoading) return <WorldLoadingState />;
  if (isError || !world) {
    return (
      <WorldErrorState
        message={error instanceof Error ? error.message : ""}
        onRetry={() => void refetch()}
      />
    );
  }

  const cover = ossHero(world.hero_image || world.cover_image);
  const supportsLine = world.has_script_mode ? t("supportsBoth") : t("supportsFreeOnly");
  const desktopScripts = scriptsExpanded
    ? world.scripts
    : world.scripts.slice(0, DESKTOP_VISIBLE_SCRIPTS);
  const canToggleScripts = world.scripts.length > DESKTOP_VISIBLE_SCRIPTS;
  const scriptHref = (scriptId: string) =>
    withReturn(`/worlds/${id}/scripts/${scriptId}`, returnTo);

  return (
    <main
      className="lv-theme lv-content-mobile-pad"
      style={{ background: "var(--lv-bg)", color: "var(--lv-ink)" }}
    >
      <MobileWorldDetail
        world={world}
        onStart={() => router.push(withReturn(`/worlds/${id}/start`, returnTo))}
        backHref={backHref}
        scriptHref={scriptHref}
      />

      <div className="lv-world-desktop">
      {/* ===== Cinematic hero（例外 A — Ken Burns 1800ms+，缩放 ≤ 1.05） ===== */}
      <section
        style={{
          position: "relative",
          width: "100%",
          minHeight: "calc(100dvh - 56px)",
          display: "flex",
          alignItems: "flex-end",
          overflow: "hidden",
          paddingTop: "var(--lv-s-16)",
          paddingBottom: "var(--lv-s-16)",
        }}
      >
        {/* 封面层 */}
        <div
          style={{ position: "absolute", inset: 0, zIndex: 0, pointerEvents: "none" }}
          aria-hidden
        >
          {cover ? (
            <div
              style={{
                position: "absolute",
                inset: 0,
                backgroundImage: `url(${cover})`,
                backgroundSize: "cover",
                // 满屏 hero 比 21:9 高时只吃底部（底部留作滚动钩子+渐变），保护顶部主体
                backgroundPosition: "center 20%",
                backgroundRepeat: "no-repeat",
                animation: "lv-kenburns 18s ease-in-out infinite",
              }}
            />
          ) : (
            <div
              style={{
                position: "absolute",
                inset: 0,
                background:
                  "radial-gradient(ellipse at 50% 30%, var(--lv-bg-2), var(--lv-bg) 75%)",
              }}
            />
          )}
          {/* 开场幕布：从全黑渐淡，给"灯光打亮"的入场感 */}
          <motion.div
            initial={{ opacity: 1 }}
            animate={{ opacity: 0 }}
            transition={{ duration: 1.6, ease: LV_EASE }}
            style={{
              position: "absolute",
              inset: 0,
              background: "rgba(10,10,12,0.95)",
            }}
          />
          {/* 单层 gradient 保护文字（§6 禁装饰堆叠） */}
          <div
            style={{
              position: "absolute",
              inset: 0,
              background:
                "linear-gradient(180deg, rgba(10,10,12,0.55) 0%, rgba(10,10,12,0.2) 35%, rgba(10,10,12,0.85) 75%, rgba(10,10,12,1) 100%)",
            }}
          />
        </div>

        {/* 左上角细返回链接（cinematic 例外内的最小导航 chrome） */}
        <Link
          href={backHref}
          className="lv-t-caps"
          style={{
            position: "absolute",
            top: "var(--lv-s-4)",
            left: "var(--lv-pad-x)",
            zIndex: 2,
            color: "var(--lv-ink-3)",
            textDecoration: "none",
            display: "inline-flex",
            alignItems: "center",
            gap: 6,
            padding: "8px 4px",
            minHeight: 32,
          }}
        >
          ← {t("backToDiscover")}
        </Link>

        {/* 内容 */}
        <div
          style={{
            position: "relative",
            zIndex: 1,
            width: "100%",
            maxWidth: "var(--lv-max-w)",
            margin: "0 auto",
            padding: "0 var(--lv-pad-x)",
          }}
        >
          <motion.div
            variants={lvFadeUp}
            initial="hidden"
            animate="show"
            style={{ maxWidth: 880 }}
          >
            {/* meta 行（caps） */}
            <div
              className="lv-t-caps"
              style={{
                display: "flex",
                flexWrap: "wrap",
                alignItems: "center",
                gap: "var(--lv-s-3)",
                marginBottom: "var(--lv-s-4)",
              }}
            >
              <span>{world.genre}</span>
              <span aria-hidden style={{ color: "var(--lv-ink-4)" }}>·</span>
              <span>{world.era}</span>
              <span aria-hidden style={{ color: "var(--lv-ink-4)" }}>·</span>
              <span>
                {t("difficulty")} {t("difficultyName", { level: difficultyLevel(world.difficulty) })}
              </span>
              <span aria-hidden style={{ color: "var(--lv-ink-4)" }}>·</span>
              <span>{world.estimated_time}</span>
            </div>

            {/* 主标题 */}
            <motion.h1
              className="lv-t-h1"
              transition={{ ...lvFastEase, delay: 0.1 }}
              initial={{ opacity: 0, y: 14 }}
              animate={{ opacity: 1, y: 0 }}
              style={{ margin: 0, color: "var(--lv-ink)" }}
            >
              {world.name}
            </motion.h1>

            {/* 描述 */}
            <motion.p
              className="lv-t-narrative"
              transition={{ ...lvFastEase, delay: 0.2 }}
              initial={{ opacity: 0, y: 14 }}
              animate={{ opacity: 1, y: 0 }}
              style={{
                marginTop: "var(--lv-s-6)",
                maxWidth: "var(--lv-max-w-read)",
                color: "var(--lv-ink-2)",
                overflow: "hidden",
                display: "-webkit-box",
                WebkitLineClamp: 5,
                WebkitBoxOrient: "vertical",
              }}
            >
              {world.description}
            </motion.p>

            {/* CTA */}
            <motion.div
              transition={{ ...lvFastEase, delay: 0.3 }}
              initial={{ opacity: 0, y: 14 }}
              animate={{ opacity: 1, y: 0 }}
              style={{
                marginTop: "var(--lv-s-8)",
                display: "flex",
                flexWrap: "wrap",
                gap: "var(--lv-s-3)",
              }}
            >
              <button
                type="button"
                onClick={() => router.push(withReturn(`/worlds/${id}/start`, returnTo))}
                className="lv-btn lv-btn-primary lv-btn-lg"
              >
                {t("startJourney")}
              </button>
            </motion.div>

            {/* mode hint */}
            <div
              className="lv-t-caps"
              style={{
                marginTop: "var(--lv-s-6)",
                color: "var(--lv-ink-3)",
              }}
            >
              {supportsLine}
            </div>
          </motion.div>
        </div>
      </section>

      {/* ===== Below-the-fold ===== */}
      <div
        style={{
          maxWidth: "var(--lv-max-w)",
          margin: "0 auto",
          padding: "var(--lv-s-16) var(--lv-pad-x) var(--lv-s-24)",
          display: "flex",
          flexDirection: "column",
          gap: "var(--lv-s-16)",
        }}
      >
        {/* Scripts */}
        {world.has_script_mode && (
          <motion.section
            variants={lvFadeUp}
            initial="hidden"
            whileInView="show"
            viewport={{ once: true, amount: 0.2 }}
            className="lv-world-script-section"
          >
            <header className="lv-world-script-head">
              <div>
                <h2 className="lv-t-h2 lv-world-script-heading">
                  {t("scriptsTitle")}
                </h2>
              </div>
              {world.scripts.length > 0 && (
                <span className="lv-world-script-count">
                  {t("scriptsCount", { count: world.scripts.length })}
                </span>
              )}
            </header>
            {world.scripts.length === 0 ? (
              <p className="lv-t-meta" style={{ margin: 0, color: "var(--lv-ink-3)" }}>
                {t("step.noScripts")}
              </p>
            ) : (
              <>
                <div className="lv-world-script-list">
                  {desktopScripts.map((s) => (
                    <ScriptCardLink key={s.id} script={s} href={scriptHref(s.id)} />
                  ))}
                </div>
                {canToggleScripts && (
                  <button
                    type="button"
                    className="lv-world-script-toggle"
                    onClick={() => setScriptsExpanded((value) => !value)}
                  >
                    {scriptsExpanded
                      ? t("scriptsCollapse")
                      : t("scriptsExpand", {
                          count: world.scripts.length - DESKTOP_VISIBLE_SCRIPTS,
                        })}
                  </button>
                )}
              </>
            )}
          </motion.section>
        )}

        {/* Characters */}
        <motion.section
          variants={lvFadeUp}
          initial="hidden"
          whileInView="show"
          viewport={{ once: true, amount: 0.2 }}
        >
          <header
            style={{
              display: "flex",
              alignItems: "baseline",
              justifyContent: "space-between",
              gap: "var(--lv-s-4)",
              marginBottom: "var(--lv-s-6)",
            }}
          >
            <h2 className="lv-t-h2" style={{ margin: 0 }}>
              {t("charactersTitle")}
            </h2>
            <span className="lv-t-caps">{t("charactersCaps")}</span>
          </header>
          {world.characters.length === 0 ? (
            <p className="lv-t-meta" style={{ margin: 0, color: "var(--lv-ink-3)" }}>
              {t("noCharacters")}
            </p>
          ) : (
            <div
              style={{
                display: "grid",
                gap: "var(--lv-s-6)",
                gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))",
              }}
            >
              {world.characters.map((c) => (
                <div
                  key={c.id}
                  className="lv-world-character-card"
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    alignItems: "center",
                    gap: "var(--lv-s-3)",
                    textAlign: "center",
                  }}
                >
                  <div
                    className="lv-world-character-avatar"
                    style={{
                      width: 96,
                      height: 96,
                      borderRadius: "var(--lv-r-pill)",
                      overflow: "hidden",
                      background: "var(--lv-bg-2)",
                      border: "1px solid var(--lv-line)",
                    }}
                  >
                    {c.avatar ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        src={ossThumb(c.avatar, 160)}
                        alt={c.name}
                        className="lv-world-character-avatar-img"
                        style={{
                          width: "100%",
                          height: "100%",
                          objectFit: "cover",
                        }}
                      />
                    ) : (
                      <div
                        className="lv-t-h1"
                        style={{
                          width: "100%",
                          height: "100%",
                          display: "grid",
                          placeItems: "center",
                          color: "var(--lv-ink-4)",
                        }}
                      >
                        {c.name[0]}
                      </div>
                    )}
                  </div>
                  <h3 className="lv-t-h3" style={{ margin: 0 }}>
                    {c.name}
                  </h3>
                </div>
              ))}
            </div>
          )}
        </motion.section>
      </div>
      </div>

      <style jsx global>{`
        /* ===== 剧本：海报网格（桌面）—— 无外层卡框，仅封面带圆角描边，对齐 discover ===== */
        .lv-world-script-section {
          width: 100%;
        }
        .lv-world-script-head {
          display: flex;
          align-items: baseline;
          justify-content: space-between;
          gap: var(--lv-s-4);
          margin-bottom: var(--lv-s-6);
        }
        .lv-world-script-heading {
          margin: 0;
        }
        .lv-world-script-count {
          flex-shrink: 0;
          color: var(--lv-ink-3);
          font-family: var(--lv-font-mono);
          font-size: 10px;
          font-weight: 500;
          letter-spacing: 0.14em;
          text-transform: uppercase;
        }
        .lv-world-script-list {
          display: grid;
          grid-template-columns: repeat(4, minmax(0, 1fr));
          gap: 18px 14px;
        }
        .lv-world-script-card {
          display: block;
          min-width: 0;
          overflow: hidden;
          color: inherit;
          text-decoration: none;
          border-radius: 10px;
          transition: transform var(--lv-dur-fast) var(--lv-ease), filter var(--lv-dur-fast) var(--lv-ease);
        }
        .lv-world-script-cover {
          position: relative;
          width: 100%;
          aspect-ratio: 3 / 2;
          overflow: hidden;
          border-radius: 8px;
          border: 1px solid rgba(255, 255, 255, 0.07);
          background: var(--lv-bg-1);
          box-shadow: 0 5px 14px rgba(0, 0, 0, 0.18);
          transition: border-color var(--lv-dur-fast) var(--lv-ease);
        }
        .lv-world-script-cover-img {
          position: absolute;
          inset: 0;
          width: 100%;
          height: 100%;
          object-fit: cover;
          transition: transform 700ms cubic-bezier(0.16, 1, 0.3, 1);
        }
        .lv-world-script-cover-fallback {
          position: absolute;
          inset: 0;
          display: grid;
          place-items: center;
          background:
            radial-gradient(82% 70% at 50% 28%, rgba(245, 242, 235, 0.07), transparent 70%),
            linear-gradient(150deg, var(--lv-bg-1), var(--lv-bg-2));
          color: var(--lv-ink-4);
          font-family: var(--lv-font-serif);
          font-size: 46px;
          line-height: 1;
        }
        .lv-world-script-body {
          min-width: 0;
          padding: 9px 2px 0;
        }
        .lv-world-script-title {
          margin: 0;
          color: var(--lv-ink);
          font-family: var(--lv-font-serif);
          font-size: 17px;
          font-weight: 500;
          line-height: 1.22;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }
        .lv-world-script-desc {
          margin: 4px 0 0;
          color: var(--lv-ink-3);
          font-size: 12px;
          line-height: 1.45;
          display: -webkit-box;
          -webkit-line-clamp: 1;
          -webkit-box-orient: vertical;
          overflow: hidden;
        }
        .lv-world-script-meta {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 10px;
          margin-top: 8px;
          color: var(--lv-ink-3);
          font-size: 12px;
        }
        .lv-world-script-time {
          font-variant-numeric: tabular-nums;
          letter-spacing: 0.01em;
        }
        @media (hover: hover) {
          .lv-world-script-card:hover {
            transform: translateY(-3px);
            filter: brightness(1.04);
          }
          .lv-world-script-card:hover .lv-world-script-cover {
            border-color: rgba(245, 242, 235, 0.18);
            box-shadow: 0 14px 34px rgba(0, 0, 0, 0.34);
          }
          .lv-world-script-card:hover .lv-world-script-cover-img {
            transform: scale(1.045);
          }
        }
        .lv-world-script-toggle {
          width: 100%;
          min-height: 42px;
          margin-top: 18px;
          border-radius: var(--lv-r-pill);
          border: 1px solid var(--lv-line-2);
          background: transparent;
          color: var(--lv-ink-2);
          font-size: 13px;
          cursor: pointer;
          transition: background var(--lv-dur-fast) var(--lv-ease), border-color var(--lv-dur-fast) var(--lv-ease), color var(--lv-dur-fast) var(--lv-ease);
        }
        .lv-world-script-toggle:hover {
          border-color: rgba(255, 255, 255, 0.16);
          background: rgba(255, 255, 255, 0.035);
          color: var(--lv-ink);
        }

        .lv-world-character-card {
          min-width: 0;
          border-radius: 12px;
          transition: transform var(--lv-dur-fast) var(--lv-ease), color var(--lv-dur-fast) var(--lv-ease);
        }
        .lv-world-character-avatar {
          transition:
            transform var(--lv-dur-fast) var(--lv-ease),
            border-color var(--lv-dur-fast) var(--lv-ease),
            box-shadow var(--lv-dur-fast) var(--lv-ease);
        }
        .lv-world-character-avatar-img {
          transition: transform 520ms var(--lv-ease);
        }
        @media (hover: hover) {
          .lv-world-character-card:hover {
            transform: translateY(-4px);
          }
          .lv-world-character-card:hover .lv-world-character-avatar {
            border-color: rgba(245, 242, 235, 0.2);
            box-shadow: 0 14px 32px rgba(0, 0, 0, 0.36);
          }
          .lv-world-character-card:hover .lv-world-character-avatar-img {
            transform: scale(1.06);
          }
        }
        @media (max-width: 1100px) {
          .lv-world-script-list {
            grid-template-columns: repeat(3, minmax(0, 1fr));
          }
        }
        @media (max-width: 860px) {
          .lv-world-script-list {
            grid-template-columns: repeat(2, minmax(0, 1fr));
          }
        }

        /* ===== 剧本：紧凑卡片（移动）===== */
        .lv-world-mobile-section-head {
          display: flex;
          align-items: baseline;
          justify-content: space-between;
          gap: 12px;
          padding: 0 4px;
        }
        .lv-world-mobile-section-head h2 {
          margin: 0;
          color: var(--lv-ink);
          font-family: var(--lv-font-serif);
          font-size: 21px;
          font-weight: 500;
        }
        .lv-world-mobile-section-head span {
          color: var(--lv-ink-4);
          font-family: var(--lv-font-mono);
          font-size: 10px;
          letter-spacing: 0.12em;
        }
        .lv-world-mobile-script-grid {
          display: grid;
          grid-template-columns: repeat(2, minmax(0, 1fr));
          gap: 9px;
        }
        .lv-world-mobile-script-card .lv-world-script-cover {
          aspect-ratio: 1.35 / 1;
        }
        .lv-world-mobile-script-card .lv-world-script-body {
          padding: 8px 1px 0;
        }
        .lv-world-mobile-script-card .lv-world-script-title {
          font-size: 15px;
          line-height: 1.16;
        }
        .lv-world-mobile-script-card .lv-world-script-desc {
          margin-top: 4px;
          font-size: 12px;
          line-height: 1.42;
          -webkit-line-clamp: 1;
        }
        .lv-world-mobile-script-card .lv-world-script-meta {
          gap: 6px;
          margin-top: 7px;
          font-size: 11px;
        }
        .lv-world-mobile-script-toggle {
          margin: 12px 4px 0;
          width: calc(100% - 8px);
          min-height: 44px;
        }
        @media (max-width: 768px) {
          .lv-world-desktop { display: none !important; }
        }
        @media (min-width: 769px) {
          .lv-world-mobile { display: none !important; }
        }
      `}</style>
    </main>
  );
}

function MobileWorldDetail({
  world,
  onStart,
  backHref,
  scriptHref,
}: {
  world: WorldDetail;
  onStart: () => void;
  backHref: string;
  scriptHref: (scriptId: string) => string;
}) {
  const t = useTranslations("worlds");
  const cover = ossThumb(world.hero_image || world.cover_image, 900, { quality: 90 });
  const [synopsisExpanded, setSynopsisExpanded] = useState(false);
  const [scriptsExpanded, setScriptsExpanded] = useState(false);
  const heroMeta = [compactMobileMeta(world.genre), compactMobileMeta(world.era)].filter(Boolean);
  const canExpandSynopsis = shouldShowWorldSynopsisToggle(world.description);
  const mobileScripts = scriptsExpanded
    ? world.scripts
    : world.scripts.slice(0, MOBILE_VISIBLE_SCRIPTS);
  const canToggleScripts = world.scripts.length > MOBILE_VISIBLE_SCRIPTS;

  return (
    <div
      className="lv-world-mobile"
      style={{
        position: "relative",
        background: "var(--lv-bg)",
        minHeight: "100dvh",
        paddingBottom: "calc(76px + env(safe-area-inset-bottom))",
      }}
    >
      <section
        data-world-mobile-hero
        style={{
          position: "relative",
          minHeight: 340,
          overflow: "hidden",
          backgroundImage: cover
            ? `linear-gradient(180deg, rgba(0,0,0,0.28), rgba(0,0,0,0.70) 48%, rgba(8,8,10,0.99)), url(${cover})`
            : "radial-gradient(ellipse at 50% 30%, var(--lv-bg-2), var(--lv-bg) 75%)",
          backgroundSize: "cover",
          backgroundPosition: "center",
        }}
      >
        <div
          aria-hidden
          style={{
            position: "absolute",
            inset: 0,
            background:
              "radial-gradient(circle at 82% 16%, rgba(223,194,144,0.12), transparent 28%), linear-gradient(180deg, rgba(5,5,7,0.34), rgba(5,5,7,0.42) 34%, rgba(5,5,7,0.98))",
          }}
        />
        <MobileTopBar
          variant="transparent"
          left={
            <Link href={backHref} aria-label="返回">
              <MobileIconButton aria-label="返回" variant="transparent" as="div">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7">
                  <path d="M15 18 9 12l6-6" />
                </svg>
              </MobileIconButton>
            </Link>
          }
          right={
            <MobileIconButton aria-label="更多" variant="transparent">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7">
                <circle cx="12" cy="12" r="1" />
                <circle cx="19" cy="12" r="1" />
                <circle cx="5" cy="12" r="1" />
              </svg>
            </MobileIconButton>
          }
        />
        <div style={{ position: "absolute", left: 18, right: 18, bottom: 18, zIndex: 2 }}>
          <div
            style={{
              display: "flex",
              flexWrap: "nowrap",
              gap: 7,
              alignItems: "center",
              color: "rgba(245,242,235,0.72)",
              fontFamily: "var(--lv-font-mono)",
              fontSize: 9,
              letterSpacing: "0.13em",
              marginBottom: 8,
              overflow: "hidden",
              whiteSpace: "nowrap",
            }}
          >
            {heroMeta.map((item, index) => (
              <span key={item} style={{ display: "inline-flex", alignItems: "center", gap: 7, minWidth: 0 }}>
                {index > 0 && (
                  <span aria-hidden style={{ color: "rgba(245,242,235,0.32)" }}>
                    ·
                  </span>
                )}
                <span
                  style={{
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                  }}
                >
                  {item}
                </span>
              </span>
            ))}
          </div>
          <h1
            style={{
              fontFamily: "var(--lv-font-serif)",
              fontSize: 34,
              fontWeight: 500,
              lineHeight: 1.05,
              color: "white",
              marginBottom: 12,
              display: "-webkit-box",
              WebkitLineClamp: 2,
              WebkitBoxOrient: "vertical",
              overflow: "hidden",
            }}
          >
            {world.name}
          </h1>
          <div style={{ display: "flex", gap: 7, marginBottom: 14 }}>
            {world.has_script_mode && (
              <span
                style={{
                  height: 25,
                  padding: "0 10px",
                  borderRadius: 999,
                  border: "1px solid rgba(255,255,255,0.14)",
                  background: "rgba(8,8,10,0.48)",
                  backdropFilter: "blur(14px)",
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 6,
                  color: "var(--lv-ink-2)",
                  fontFamily: "var(--lv-font-mono)",
                  fontSize: 9,
                  letterSpacing: "0.12em",
                }}
              >
                剧本模式
              </span>
            )}
            <span
              style={{
                height: 25,
                padding: "0 10px",
                borderRadius: 999,
                border: "1px solid rgba(255,255,255,0.14)",
                background: "rgba(8,8,10,0.48)",
                backdropFilter: "blur(14px)",
                display: "inline-flex",
                alignItems: "center",
                gap: 6,
                color: "var(--lv-ink-2)",
                fontFamily: "var(--lv-font-mono)",
                fontSize: 9,
                letterSpacing: "0.12em",
                }}
              >
                自由探索
              </span>
          </div>
          <button
            type="button"
            onClick={onStart}
            style={{
              width: "100%",
              height: 50,
              borderRadius: 999,
              background: "rgba(245,242,235,0.94)",
              color: "var(--lv-bg)",
              border: 0,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: 8,
              fontSize: 14,
              fontWeight: 700,
              letterSpacing: "0.04em",
              boxShadow: "0 12px 28px rgba(0,0,0,0.42)",
              cursor: "pointer",
            }}
          >
            开始游玩
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
              <path d="M5 12h14M13 5l7 7-7 7" />
            </svg>
          </button>
        </div>
      </section>

      <div style={{ padding: "14px 12px 0", display: "flex", flexDirection: "column", gap: 14 }}>
        {world.description && (
          <section style={{ padding: "0 4px" }}>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                gap: 12,
                marginBottom: 8,
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
                世界简介
              </h2>
              {canExpandSynopsis && (
                <button
                  type="button"
                  aria-expanded={synopsisExpanded}
                  onClick={() => setSynopsisExpanded((value) => !value)}
                  style={{
                    minHeight: 32,
                    borderRadius: 999,
                    border: "1px solid rgba(255,255,255,0.12)",
                    background: "rgba(255,255,255,0.04)",
                    color: "var(--lv-ink-2)",
                    padding: "0 11px",
                    fontSize: 12,
                    cursor: "pointer",
                  }}
                >
                  {synopsisExpanded ? "收起" : "展开"}
                </button>
              )}
            </div>
            <p
              style={{
                color: "var(--lv-ink-2)",
                fontSize: 13,
                lineHeight: 1.72,
                margin: 0,
                display: canExpandSynopsis && !synopsisExpanded ? "-webkit-box" : "block",
                WebkitLineClamp: canExpandSynopsis && !synopsisExpanded ? 3 : undefined,
                WebkitBoxOrient: canExpandSynopsis && !synopsisExpanded ? "vertical" : undefined,
                overflow: canExpandSynopsis && !synopsisExpanded ? "hidden" : undefined,
              }}
            >
              {world.description}
            </p>
          </section>
        )}

        {world.has_script_mode && world.scripts.length > 0 && (
          <>
            <div className="lv-world-mobile-section-head">
              <h2>剧本</h2>
              <span>{world.scripts.length}</span>
            </div>
            <div
              className="lv-world-mobile-script-grid"
              style={{
                padding: "0 4px",
              }}
            >
              {mobileScripts.map((s) => (
                <ScriptCardLink
                  key={s.id}
                  script={s}
                  href={scriptHref(s.id)}
                  className="lv-world-mobile-script-card"
                />
              ))}
            </div>
            {canToggleScripts && (
              <button
                type="button"
                className="lv-world-script-toggle lv-world-mobile-script-toggle"
                onClick={() => setScriptsExpanded((value) => !value)}
              >
                {scriptsExpanded
                  ? t("scriptsCollapse")
                  : t("scriptsExpand", {
                      count: world.scripts.length - MOBILE_VISIBLE_SCRIPTS,
                    })}
              </button>
            )}
          </>
        )}

        {world.characters.length > 0 && (
          <>
            <div data-world-mobile-characters style={{ padding: "0 4px" }}>
              <h2
                style={{
                  fontFamily: "var(--lv-font-serif)",
                  fontSize: 21,
                  fontWeight: 500,
                  color: "var(--lv-ink)",
                }}
              >
                角色
              </h2>
            </div>
            <div
              className="lv-world-chars-strip"
              style={{
                display: "flex",
                gap: 18,
                overflowX: "auto",
                overflowY: "hidden",
                padding: "0 4px 8px",
                scrollSnapType: "x mandatory",
                scrollPaddingLeft: 4,
                scrollbarWidth: "none",
              }}
            >
              {world.characters.map((c) => (
                <article
                  key={c.id}
                  className="lv-world-character-card lv-world-mobile-character-card"
                  style={{
                    flex: "0 0 78px",
                    minHeight: 108,
                    textAlign: "center",
                    scrollSnapAlign: "start",
                  }}
                >
                  <div
                    className="lv-world-character-avatar"
                    style={{
                      width: 64,
                      height: 64,
                      margin: "0 auto 9px",
                      borderRadius: 999,
                      border: "1px solid rgba(255,255,255,0.12)",
                      backgroundImage: c.avatar ? `url(${ossThumb(c.avatar, 160)})` : undefined,
                      backgroundColor: c.avatar ? undefined : "var(--lv-bg-2)",
                      backgroundSize: "cover",
                      backgroundPosition: "center",
                      display: "grid",
                      placeItems: "center",
                      color: "var(--lv-ink-4)",
                      fontFamily: "var(--lv-font-serif)",
                      fontSize: 24,
                    }}
                  >
                    {c.avatar ? null : c.name[0]}
                  </div>
                  <h3
                    style={{
                      fontFamily: "var(--lv-font-serif)",
                      fontSize: 15,
                      lineHeight: 1.05,
                      color: "var(--lv-ink)",
                      marginBottom: 4,
                      whiteSpace: "nowrap",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                    }}
                  >
                    {c.name}
                  </h3>
                </article>
              ))}
            </div>
          </>
        )}

      </div>
    </div>
  );
}
