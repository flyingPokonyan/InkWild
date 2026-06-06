"use client";

import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { motion } from "motion/react";
import { useTranslations } from "next-intl";

import { lvFastEase, lvFadeUp, LV_EASE } from "@/lib/motion";
import { useWorldDetail } from "@/lib/api/worlds";
import { resolveExitHref, withReturn } from "@/lib/play-return";
import { difficultyLevel } from "@/lib/difficulty";
import { resolvePlayableCharacters } from "@/lib/world-entry";
import { MobileTopBar, MobileIconButton } from "@/components/MobileTopBar";
import { LoadingPulse } from "@/components/ui/LoadingPulse";
import { ossThumb } from "@/lib/oss-image";
import type { CharacterDTO, ScriptDTO, WorldDetail } from "@/lib/types";

/* 状态：加载中 — §10.1 中央 8px 暖金脉冲，无文字 */
function ScriptLoadingState() {
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

/* 状态：找不到剧本 / 加载失败 */
function ScriptErrorState({ title, backHref }: { title: string; backHref: string }) {
  const t = useTranslations("worlds");
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
        {title}
      </h1>
      <Link href={backHref} className="lv-btn lv-btn-primary">
        {t("backToWorld")}
      </Link>
    </div>
  );
}

export function ScriptDetailClient() {
  const { id, scriptId } = useParams<{ id: string; scriptId: string }>();
  const router = useRouter();
  const searchParams = useSearchParams();
  const returnTo = searchParams.get("return");
  const worldHref = withReturn(`/worlds/${id}`, returnTo);
  const backHref = resolveExitHref(returnTo, worldHref);
  const t = useTranslations("worlds");
  const { data: world, isLoading } = useWorldDetail(id);

  if (isLoading) return <ScriptLoadingState />;

  const script = world?.scripts.find((s) => s.id === scriptId) ?? null;
  if (!world || !script) {
    return <ScriptErrorState title={t("scriptNotFound")} backHref={worldHref} />;
  }

  const playable = resolvePlayableCharacters(world, script);
  const onStart = () =>
    router.push(withReturn(`/worlds/${id}/start?mode=script&script=${script.id}`, returnTo));

  return (
    <main
      className="lv-theme lv-content-mobile-pad"
      style={{ background: "var(--lv-bg)", color: "var(--lv-ink)" }}
    >
      <MobileScriptDetail
        world={world}
        script={script}
        playable={playable}
        onStart={onStart}
        worldHref={worldHref}
      />

      <ScriptDesktop
        world={world}
        script={script}
        playable={playable}
        onStart={onStart}
        backHref={backHref}
        t={t}
      />

      <style jsx global>{`
        .lv-scriptd-chars {
          display: grid;
          gap: var(--lv-s-6);
          grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
        }
        .lv-scriptd-character-card {
          min-width: 0;
          border-radius: 12px;
          transition: transform var(--lv-dur-fast) var(--lv-ease), color var(--lv-dur-fast) var(--lv-ease);
        }
        .lv-scriptd-character-avatar {
          transition:
            transform var(--lv-dur-fast) var(--lv-ease),
            border-color var(--lv-dur-fast) var(--lv-ease),
            box-shadow var(--lv-dur-fast) var(--lv-ease);
        }
        .lv-scriptd-character-avatar-img {
          transition: transform 520ms var(--lv-ease);
        }
        @media (hover: hover) {
          .lv-scriptd-character-card:hover {
            transform: translateY(-4px);
          }
          .lv-scriptd-character-card:hover .lv-scriptd-character-avatar {
            border-color: rgba(245, 242, 235, 0.2);
            box-shadow: 0 14px 32px rgba(0, 0, 0, 0.36);
          }
          .lv-scriptd-character-card:hover .lv-scriptd-character-avatar-img {
            transform: scale(1.06);
          }
        }
        @media (max-width: 768px) {
          .lv-scriptd-desktop { display: none !important; }
        }
        @media (min-width: 769px) {
          .lv-scriptd-mobile { display: none !important; }
        }
      `}</style>
    </main>
  );
}

/* ============================ 桌面 ============================ */

function ScriptDesktop({
  world,
  script,
  playable,
  onStart,
  backHref,
  t,
}: {
  world: WorldDetail;
  script: ScriptDTO;
  playable: CharacterDTO[];
  onStart: () => void;
  backHref: string;
  t: ReturnType<typeof useTranslations>;
}) {
  const cover = ossThumb(script.cover_image || world.hero_image || world.cover_image, 900);

  return (
    <div className="lv-scriptd-desktop">
      {/* ===== Cinematic hero（对齐世界详情例外 A — Ken Burns，缩放 ≤ 1.05） ===== */}
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
        <div style={{ position: "absolute", inset: 0, zIndex: 0, pointerEvents: "none" }} aria-hidden>
          {cover ? (
            <div
              style={{
                position: "absolute",
                inset: 0,
                backgroundImage: `url(${cover})`,
                backgroundSize: "cover",
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
                background: "radial-gradient(ellipse at 50% 30%, var(--lv-bg-2), var(--lv-bg) 75%)",
              }}
            />
          )}
          {/* 开场幕布：从全黑渐淡 */}
          <motion.div
            initial={{ opacity: 1 }}
            animate={{ opacity: 0 }}
            transition={{ duration: 1.6, ease: LV_EASE }}
            style={{ position: "absolute", inset: 0, background: "rgba(10,10,12,0.95)" }}
          />
          {/* 单层 gradient 保护文字 */}
          <div
            style={{
              position: "absolute",
              inset: 0,
              background:
                "linear-gradient(180deg, rgba(10,10,12,0.55) 0%, rgba(10,10,12,0.2) 35%, rgba(10,10,12,0.85) 75%, rgba(10,10,12,1) 100%)",
            }}
          />
        </div>

        {/* 面包屑：返回所属世界（cinematic 例外内的最小导航 chrome） */}
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
            maxWidth: "70vw",
            overflow: "hidden",
            whiteSpace: "nowrap",
            textOverflow: "ellipsis",
          }}
        >
          ← {world.name}
        </Link>

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
          <motion.div variants={lvFadeUp} initial="hidden" animate="show" style={{ maxWidth: 880 }}>
            {/* meta 行 */}
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
                {t("difficulty")} {t("difficultyName", { level: difficultyLevel(script.difficulty) })}
              </span>
              <span aria-hidden style={{ color: "var(--lv-ink-4)" }}>·</span>
              <span>{script.estimated_time}</span>
            </div>

            {/* 剧本名 */}
            <motion.h1
              className="lv-t-h1"
              transition={{ ...lvFastEase, delay: 0.1 }}
              initial={{ opacity: 0, y: 14 }}
              animate={{ opacity: 1, y: 0 }}
              style={{ margin: 0, color: "var(--lv-ink)" }}
            >
              {script.name}
            </motion.h1>

            {/* 梗概 */}
            {script.description && (
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
                  WebkitLineClamp: 6,
                  WebkitBoxOrient: "vertical",
                }}
              >
                {script.description}
              </motion.p>
            )}

            {/* CTA */}
            <motion.div
              transition={{ ...lvFastEase, delay: 0.3 }}
              initial={{ opacity: 0, y: 14 }}
              animate={{ opacity: 1, y: 0 }}
              style={{ marginTop: "var(--lv-s-8)", display: "flex", flexWrap: "wrap", gap: "var(--lv-s-3)" }}
            >
              <button type="button" onClick={onStart} className="lv-btn lv-btn-primary lv-btn-lg">
                {t("startThisScript")}
              </button>
            </motion.div>
          </motion.div>
        </div>
      </section>

      {/* ===== Below-the-fold：可玩角色 ===== */}
      {playable.length > 0 && (
        <div
          style={{
            maxWidth: "var(--lv-max-w)",
            margin: "0 auto",
            padding: "var(--lv-s-16) var(--lv-pad-x) var(--lv-s-24)",
          }}
        >
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
            <div className="lv-scriptd-chars">
              {playable.map((c) => (
                <div
                  key={c.id}
                  className="lv-scriptd-character-card"
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    alignItems: "center",
                    gap: "var(--lv-s-3)",
                    textAlign: "center",
                  }}
                >
                  <div
                    className="lv-scriptd-character-avatar"
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
                        className="lv-scriptd-character-avatar-img"
                        style={{ width: "100%", height: "100%", objectFit: "cover" }}
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
          </motion.section>
        </div>
      )}
    </div>
  );
}

/* ============================ 移动 ============================ */

function MobileScriptDetail({
  world,
  script,
  playable,
  onStart,
  worldHref,
}: {
  world: WorldDetail;
  script: ScriptDTO;
  playable: CharacterDTO[];
  onStart: () => void;
  worldHref: string;
}) {
  const t = useTranslations("worlds");
  const cover = ossThumb(script.cover_image || world.hero_image || world.cover_image, 900);

  return (
    <div
      className="lv-scriptd-mobile"
      style={{
        position: "relative",
        background: "var(--lv-bg)",
        minHeight: "100dvh",
        paddingBottom: "calc(76px + env(safe-area-inset-bottom))",
      }}
    >
      <section
        style={{
          position: "relative",
          minHeight: 360,
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
            <Link href={worldHref} aria-label="返回所属世界">
              <MobileIconButton aria-label="返回所属世界" variant="transparent" as="div">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7">
                  <path d="M15 18 9 12l6-6" />
                </svg>
              </MobileIconButton>
            </Link>
          }
        />
        <div style={{ position: "absolute", left: 18, right: 18, bottom: 18, zIndex: 2 }}>
          {/* 所属世界面包屑 */}
          <Link
            href={worldHref}
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 6,
              color: "rgba(245,242,235,0.72)",
              fontFamily: "var(--lv-font-mono)",
              fontSize: 9,
              letterSpacing: "0.13em",
              textTransform: "uppercase",
              textDecoration: "none",
              marginBottom: 8,
              maxWidth: "100%",
              overflow: "hidden",
              whiteSpace: "nowrap",
            }}
          >
            {world.name}
          </Link>
          <h1
            style={{
              fontFamily: "var(--lv-font-serif)",
              fontSize: 32,
              fontWeight: 500,
              lineHeight: 1.06,
              color: "white",
              marginBottom: 10,
              display: "-webkit-box",
              WebkitLineClamp: 2,
              WebkitBoxOrient: "vertical",
              overflow: "hidden",
            }}
          >
            {script.name}
          </h1>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              flexWrap: "wrap",
              gap: 8,
              marginBottom: 14,
              color: "rgba(245,242,235,0.74)",
              fontFamily: "var(--lv-font-mono)",
              fontSize: 10,
              letterSpacing: "0.06em",
            }}
          >
            <span>
              {t("difficulty")} {t("difficultyName", { level: difficultyLevel(script.difficulty) })}
            </span>
            <span aria-hidden style={{ color: "rgba(245,242,235,0.32)" }}>·</span>
            <span>{script.estimated_time}</span>
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
            {t("startThisScript")}
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
              <path d="M5 12h14M13 5l7 7-7 7" />
            </svg>
          </button>
        </div>
      </section>

      <div style={{ padding: "16px 12px 0", display: "flex", flexDirection: "column", gap: 16 }}>
        {script.description && (
          <section style={{ padding: "0 4px" }}>
            <h2
              style={{
                fontFamily: "var(--lv-font-serif)",
                fontSize: 21,
                fontWeight: 500,
                color: "var(--lv-ink)",
                marginBottom: 8,
              }}
            >
              {t("scriptsTitle")}
            </h2>
            <p style={{ color: "var(--lv-ink-2)", fontSize: 13, lineHeight: 1.72, margin: 0 }}>
              {script.description}
            </p>
          </section>
        )}

        {playable.length > 0 && (
          <>
            <div style={{ padding: "0 4px" }}>
              <h2
                style={{
                  fontFamily: "var(--lv-font-serif)",
                  fontSize: 21,
                  fontWeight: 500,
                  color: "var(--lv-ink)",
                }}
              >
                {t("charactersTitle")}
              </h2>
            </div>
            <div
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
              {playable.map((c) => (
                <article
                  key={c.id}
                  className="lv-scriptd-character-card lv-scriptd-mobile-character-card"
                  style={{
                    flex: "0 0 78px",
                    minHeight: 108,
                    textAlign: "center",
                    scrollSnapAlign: "start",
                  }}
                >
                  <div
                    className="lv-scriptd-character-avatar"
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
