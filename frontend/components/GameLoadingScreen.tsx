"use client";

/**
 * Game 入场过场（10–20s）—— 等首条 narrator LLM 流时显示。
 *
 * 视觉：黑底 + AmbientAura（月光白 7s 呼吸 + edge vignette）+ 中央 3 行文字 + 8px 脉冲圆。
 * 字体：世界名 serif h1（§1.1 ③ 卡片世界名）；剧本名 serif italic h3 + 《》（§1.1 ② italic 高亮、④ 引文）；
 *      角色行 sans meta（中文禁用 mono caps/micro）。
 * 文案规则：见 docs/design/visual-principles.md §10.1（禁假步骤、禁"正在加载…"）+ §9.1（删修饰词，保情绪）。
 *
 * 不做实际进度条 — 后端是 LLM 流（开始/收到/结束三态），没有 0-100%，假进度违规。
 */

import { useLocale, useTranslations } from "next-intl";

import { resolveProcessingLabel } from "@/lib/processing-label";
import type { ProcessingEventPayload } from "@/lib/types";

import { AmbientAura } from "./choice/AmbientAura";
import { LoadingPulse } from "./ui/LoadingPulse";

interface GameLoadingScreenProps {
  worldName: string | null;
  characterName: string | null;
  scriptName?: string | null;
  /** Live opening milestone — shown subtly under the logo (体察态度 / 接收行动 /
   *  谁进场 / 落笔). Null until the first milestone arrives (logo-only). */
  processing?: ProcessingEventPayload | null;
}

export function GameLoadingScreen({ worldName, characterName, scriptName, processing }: GameLoadingScreenProps) {
  const t = useTranslations("play");
  const locale = useLocale();
  const label = resolveProcessingLabel(processing, t, locale);
  return (
    <div
      className="game-loading-root relative flex min-h-dvh w-full flex-col items-center justify-center overflow-hidden px-6"
      style={{ background: "var(--lv-bg)" }}
    >
      <AmbientAura />

      <div className="relative z-10 flex flex-col items-center text-center" style={{ marginTop: "-4vh" }}>
        {worldName && (
          <h1
            className="lv-t-h1"
            style={{
              fontFamily: "var(--lv-font-serif)",
              fontWeight: 500,
              color: "var(--lv-ink)",
              letterSpacing: "-0.015em",
            }}
          >
            {worldName}
          </h1>
        )}

        {scriptName && (
          <div
            className="lv-t-h3 mt-1.5"
            style={{
              fontFamily: "var(--lv-font-serif)",
              fontWeight: 400,
              color: "var(--lv-ink-2)",
              letterSpacing: "0.01em",
            }}
          >
            《{scriptName}》
          </div>
        )}

        {characterName && (
          <div
            className="lv-t-meta mt-3"
            style={{
              color: "var(--lv-ink-3)",
              letterSpacing: "0.04em",
            }}
          >
            你扮演&nbsp;&nbsp;{characterName}
          </div>
        )}

        <div className="mt-16">
          {/* 已有 worldName / scriptName / characterName + 下方 flavor，不再叠加默认文案 */}
          <LoadingPulse variant="block" label="" />
        </div>

        {label && (
          <div
            className="lv-t-meta mt-6"
            style={{
              color: "var(--lv-ink-3)",
              opacity: 0.85,
              maxWidth: "32ch",
              lineHeight: 1.6,
              transition: "opacity 400ms ease",
            }}
          >
            {label}
          </div>
        )}
      </div>

    </div>
  );
}
