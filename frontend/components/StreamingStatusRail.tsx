"use client";

import { useLocale, useTranslations } from "next-intl";

import { resolveProcessingLabel } from "@/lib/processing-label";
import type { ProcessingEventPayload } from "@/lib/types";

import { LoadingPulse } from "./ui/LoadingPulse";

/**
 * 思考态进度行（首包前展示）。小号 Branch logo（持续动画）+ 演进式过程反馈：
 * 文案由真实里程碑驱动（接收行动 / 推演『你的输入』/ {NPC}进场 / 落笔成文），
 * 按 next-intl 拼装、每回合不同、零额外 LLM。无 stage（首个事件到达前）= 呼吸态，
 * 只显示 logo。§10.1 合规：Branch 为主视觉、文案为辅，非纯文字 / 非"正在加载…"。
 */
export function StreamingStatusRail({
  processing,
}: {
  processing?: ProcessingEventPayload | null;
}) {
  const t = useTranslations("play");
  const locale = useLocale();
  const label = resolveProcessingLabel(processing, t, locale);

  return (
    <div className="play-thinking-rail" role="status" aria-live="polite">
      <span className="play-thinking-glyph" aria-hidden="true">
        <LoadingPulse variant="branch" size={18} label="" />
      </span>
      {label && <span className="play-thinking-label">{label}</span>}
    </div>
  );
}
