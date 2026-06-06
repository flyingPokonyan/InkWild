"use client";

import { usePathname } from "next/navigation";
import { AnimatePresence, motion } from "motion/react";

import { useGameStore } from "@/stores/game";
import { GameLoadingScreen } from "./GameLoadingScreen";

/**
 * 开局过场 overlay —— 挂在根 layout，跨路由不卸载（办法一）。
 *
 * 开局导航在读条中途（session_created）就从 setup 切到 play。若读条屏随路由重挂，中间会
 * 闪 play/[id]/loading.tsx 的裸 pulse、AmbientAura 也重置相位 → 看着「跳一下 / 卡顿一下」。
 * 把读条屏提到 layout 这一层、用 store 驱动：从点「开始」(isStreaming=true) 一直盖到首句
 * 旁白到达。底下的路由切换 / loading.tsx / 各页自己的 GameLoadingScreen 全在它**之下**发生、
 * 被它盖住；而它本身是同一个 React 实例、同一套光晕动画，不重挂 → 零跳零闪。退场用 fade
 * 揭开舞台；开局失败时 isStreaming 转 false → overlay 自动淡出，露出 play 页的 openingFailed。
 *
 * 注意：它是被动读 store 的纯渲染组件；SSE 是浏览器直连后端 :8000 的 fetch（store 里、无
 * AbortController），本组件无论如何重渲染都**碰不到**那条流，不会影响开局流式。
 */
export function OpeningLoadingOverlay() {
  const pathname = usePathname();
  const isStreaming = useGameStore((s) => s.isStreaming);
  // 出现带内容的 narrator 消息 = 首句旁白已到。开局以外（mid-game 回合、resume）store 里
  // 都已有旧 narrator 消息，故此 overlay 只在「全新开局、首句旁白之前」这个窗口出现。
  // 布尔 selector：Zustand 只在它翻转时才重渲染本组件（不会每个 token 都渲染）。
  const openingNarrativeArrived = useGameStore((s) =>
    s.messages.some((m) => m.role === "narrator" && m.content.trim().length > 0),
  );
  const worldName = useGameStore((s) => s.worldName);
  const scriptName = useGameStore((s) => s.scriptName);
  const characterName = useGameStore((s) => s.characterName);
  const processingHint = useGameStore((s) => s.processingHint);

  // 只在开局相关路由（setup / play）显示，避免开局途中返回时把 overlay 带到无关页面。
  // setup↔play 都满足该条件，故跨这两个路由切换时 overlay 不被摘下 → 仍是同一实例、不重挂。
  const onOpeningRoute =
    !!pathname && (pathname.startsWith("/play/") || pathname.endsWith("/start"));
  const show = onOpeningRoute && isStreaming && !openingNarrativeArrived;

  return (
    <AnimatePresence initial={false}>
      {show && (
        <motion.div
          key="opening-loading-overlay"
          exit={{ opacity: 0 }}
          transition={{ duration: 0.45, ease: "easeOut" }}
          style={{
            position: "fixed",
            inset: 0,
            zIndex: "var(--lv-z-overlay)" as unknown as number,
          }}
        >
          <GameLoadingScreen
            worldName={worldName}
            scriptName={scriptName}
            characterName={characterName}
            processing={processingHint}
          />
        </motion.div>
      )}
    </AnimatePresence>
  );
}
