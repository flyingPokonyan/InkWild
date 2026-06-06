/**
 * Framer Motion 预设——把 v2.2 §6 的动效令牌包成可复用 transition / variants。
 *
 * 用法：
 *   import { motion } from "motion/react";
 *   import { lvFadeUp, lvFastEase, lvPageEase } from "@/lib/motion";
 *
 *   <motion.div variants={lvFadeUp} initial="hidden" animate="show" />
 *   <motion.button transition={lvFastEase}>...</motion.button>
 */

export const LV_EASE = [0.2, 0.7, 0.2, 1] as const;
export const LV_DUR_FAST = 0.2;
export const LV_DUR_PAGE = 0.4;
export const LV_DUR_CINEMATIC_A = 1.8;
export const LV_DUR_CINEMATIC_B = 1.2;

export const lvFastEase = {
  duration: LV_DUR_FAST,
  ease: LV_EASE,
} as const;

export const lvPageEase = {
  duration: LV_DUR_PAGE,
  ease: LV_EASE,
} as const;

export const lvFadeUp = {
  hidden: { opacity: 0, y: 14 },
  show: { opacity: 1, y: 0, transition: lvPageEase },
} as const;

export const lvFadeIn = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: lvPageEase },
} as const;

export const lvCinematicFadeIn = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: { duration: LV_DUR_CINEMATIC_B, ease: LV_EASE },
  },
} as const;

/**
 * Netflix / Apple TV+ 风格的 stagger 入场。
 * 容器控制 staggerChildren 间隔；item 控制单卡 fade-up。
 * 用 500ms 单卡 + 70ms 间隔，比 lvPageEase（400ms）略柔，给"内容墙渐次升起"的感觉。
 */
export const lvStaggerContainer = {
  hidden: {},
  show: {
    transition: {
      staggerChildren: 0.07,
      delayChildren: 0.04,
    },
  },
} as const;

export const lvStaggerItem = {
  hidden: { opacity: 0, y: 12 },
  show: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.5, ease: LV_EASE },
  },
} as const;
