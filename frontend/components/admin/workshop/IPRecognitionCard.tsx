"use client";

/**
 * IP 识别选择 —— 生成 loading 屏中段的"决策时刻"。
 *
 * 重写：现在走通用 ChoiceScene (embedded) + ListChoiceOption + useChoiceCountdown。
 * 嵌入 GenerationLoadingScreen 的 centerSlot，外层背景由 GenerationLoadingScreen 提供。
 * original 或 confidence < 0.5 时直接自动 onChoose("none") 不渲染 UI。
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { motion } from "motion/react";

import {
  ChoiceScene,
  ListChoiceOption,
  useChoiceCountdown,
} from "@/components/choice";
import { lvStaggerContainer } from "@/lib/motion";

type Recognition = {
  kind: "known_ip" | "hybrid" | "original";
  confidence: number;
  ip_name?: string | null;
  ip_type?: string | null;
  one_liner?: string | null;
  source_hints?: string[];
};

type FidelityMode = "strict" | "loose" | "none";

type OptionDef = {
  mode: FidelityMode;
  title: string;
  desc: string;
  recommended?: boolean;
};

type Props = {
  recognition: Recognition;
  onChoose: (mode: FidelityMode) => void;
  autoConfirmMs?: number;
};

const IP_TYPE_LABEL: Record<string, string> = {
  tv: "剧集",
  movie: "电影",
  novel: "小说",
  anime: "动画",
  game: "游戏",
  other: "其它",
};

export function IPRecognitionCard({ recognition, onChoose, autoConfirmMs = 8000 }: Props) {
  const shouldSkip =
    recognition.kind === "original" || recognition.confidence < 0.5;

  const isHigh = recognition.kind === "known_ip" && recognition.confidence >= 0.85;
  const defaultMode: FidelityMode = isHigh ? "strict" : "none";

  const ipName = recognition.ip_name || "未知作品";

  const options = useMemo<OptionDef[]>(() => {
    if (isHigh) {
      return [
        { mode: "strict", title: "高复刻原作", desc: "保留关键人物、地点、核心设定", recommended: true },
        { mode: "loose", title: "借鉴主线，自由创作", desc: "主线参考原作，人物地点可自由扩展" },
        { mode: "none", title: "这不是复刻", desc: "不参考原作，按描述独立生成" },
      ];
    }
    return [
      { mode: "loose", title: `参考《${ipName}》创作`, desc: "借用原作的风格与世界观线索" },
      { mode: "none", title: "按我写的来", desc: "不参考原作，按描述独立生成" },
    ];
  }, [isHigh, ipName]);

  const defaultOption = options.find((o) => o.mode === defaultMode);

  const [paused, setPaused] = useState(false);
  const decidedRef = useRef(false);

  useEffect(() => {
    if (shouldSkip && !decidedRef.current) {
      decidedRef.current = true;
      onChoose("none");
    }
  }, [shouldSkip, onChoose]);

  const handleChoose = (mode: FidelityMode) => {
    if (decidedRef.current) return;
    decidedRef.current = true;
    onChoose(mode);
  };

  const { secondsLeft } = useChoiceCountdown({
    totalMs: autoConfirmMs,
    paused: shouldSkip || paused,
    onTimeout: () => handleChoose(defaultMode),
  });

  if (shouldSkip) return null;

  const ipTypeLabel = recognition.ip_type
    ? IP_TYPE_LABEL[recognition.ip_type] || recognition.ip_type
    : null;

  const eyebrow = ipTypeLabel ?? undefined;
  const description = recognition.one_liner || undefined;

  const countdownText = paused
    ? "暂停自动选择"
    : defaultOption
      ? `${secondsLeft}s 后默认「${defaultOption.title}」`
      : `${secondsLeft}s 后自动选择`;

  return (
    <ChoiceScene
      embedded
      eyebrow={eyebrow}
      title={`《${ipName}》`}
      description={description}
      countdown={{ text: countdownText }}
      onCountdownPauseChange={setPaused}
    >
      <motion.div
        variants={lvStaggerContainer}
        initial="hidden"
        animate="show"
        style={{
          width: "100%",
          maxWidth: 480,
          margin: "0 auto",
          display: "flex",
          flexDirection: "column",
          gap: "var(--lv-s-2)",
        }}
      >
        {options.map((opt, idx) => (
          <ListChoiceOption
            key={opt.mode}
            index={idx + 1}
            title={opt.title}
            description={opt.desc}
            recommended={opt.recommended}
            selected={false}
            onSelect={() => handleChoose(opt.mode)}
          />
        ))}
      </motion.div>
    </ChoiceScene>
  );
}
