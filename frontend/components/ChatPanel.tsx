"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { useTranslations } from "next-intl";

import { isNearBottom } from "@/lib/play-scroll";
import { useGameStore } from "@/stores/game";

import { JumpToLatestButton } from "./JumpToLatestButton";
import { MessageBubble } from "./MessageBubble";
import { StreamingStatusRail } from "./StreamingStatusRail";

export function ChatPanel() {
  const messages = useGameStore((state) => state.messages);
  const characterName = useGameStore((state) => state.characterName);
  const characterDesc = useGameStore((state) => state.characterDesc);
  const characterAbilities = useGameStore((state) => state.characterAbilities);
  const streamPhase = useGameStore((state) => state.streamPhase);
  const processingHint = useGameStore((state) => state.processingHint);
  const retryCount = useGameStore((state) => state.retryCount);
  const retryAction = useGameStore((state) => state.retryAction);
  const t = useTranslations("play");

  const timelineRef = useRef<HTMLDivElement>(null);
  const stickRef = useRef(true);
  const [showJump, setShowJump] = useState(false);

  const identitySummary = characterDesc || characterAbilities.join(" · ");
  const lastMessage = messages[messages.length - 1];
  const activeNarratorId =
    streamPhase === "streaming" && lastMessage?.role === "narrator" ? lastMessage.id : null;
  const isProcessing = streamPhase === "processing";
  const isIdle = streamPhase !== "processing" && streamPhase !== "streaming";

  const updateStick = useCallback(() => {
    const el = timelineRef.current;
    if (!el) return;
    const near = isNearBottom(
      { scrollTop: el.scrollTop, scrollHeight: el.scrollHeight, clientHeight: el.clientHeight },
      120,
    );
    stickRef.current = near;
    setShowJump(!near && messages.length > 2);
  }, [messages.length]);

  useEffect(() => {
    const el = timelineRef.current;
    if (!el) return;
    el.addEventListener("scroll", updateStick, { passive: true });
    return () => el.removeEventListener("scroll", updateStick);
  }, [updateStick]);

  useEffect(() => {
    const el = timelineRef.current;
    if (!el || !stickRef.current) return;
    const frame = requestAnimationFrame(() => {
      el.scrollTo({
        top: el.scrollHeight,
        behavior: streamPhase === "streaming" ? "auto" : "smooth",
      });
    });
    return () => cancelAnimationFrame(frame);
  }, [messages, processingHint, streamPhase]);

  const jumpToLatest = useCallback(() => {
    const el = timelineRef.current;
    if (!el) return;
    el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
    stickRef.current = true;
    setShowJump(false);
  }, []);

  if (messages.length === 0) {
    return (
      <div
        ref={timelineRef}
        className="play-timeline scrollbar-hide flex items-center justify-center"
      >
        <div className="play-empty-state mx-auto text-center">
          <h2 className="lv-t-h2" style={{ color: "var(--lv-ink-2)" }}>
            {t("emptyTitle")}
          </h2>
          <p
            className="lv-t-narrative"
            style={{ marginTop: "var(--lv-s-4)", color: "var(--lv-ink-3)" }}
          >
            {t("emptyDesc")}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div ref={timelineRef} className="play-timeline scrollbar-hide">
      <div
        className="play-timeline-inner"
        style={{
          flexDirection: "column",
          display: "flex",
          minHeight: "100%",
        }}
      >
        {characterName && (
          <section className="play-identity">
            <div className="play-identity-label">
              {t("identityCaps")}
            </div>
            <div className="play-identity-name">
              {characterName}
            </div>
            {identitySummary && (
              <div className="play-identity-desc">
                {identitySummary}
              </div>
            )}
          </section>
        )}

        <div
          className="flex flex-col flex-1 justify-end"
          style={{ gap: "var(--lv-s-8)", paddingBottom: "var(--lv-s-8)" }}
        >
          {messages.map((message) => (
            <div key={message.id} className="play-message-enter">
              <MessageBubble message={message} isActive={message.id === activeNarratorId} />
            </div>
          ))}
        </div>

        {/* 思考态 → 正文：平滑淡出/上移让位正文，消除"首包到达硬切"。
            进场用 CSS play-rail-in，故 initial=false（避免双重动画）。 */}
        <AnimatePresence>
          {isProcessing && (
            <motion.div
              key="thinking-rail"
              initial={false}
              exit={{ opacity: 0, y: -4 }}
              transition={{ duration: 0.3, ease: "easeOut" }}
              style={{ padding: "0 0 var(--lv-s-6)" }}
            >
              <StreamingStatusRail processing={processingHint} />
            </motion.div>
          )}
        </AnimatePresence>

        {isIdle && lastMessage?.role === "narrator" && (
          <div className="flex justify-end" style={{ paddingBottom: "var(--lv-s-6)" }}>
            <button
              type="button"
              onClick={() => {
                void retryAction();
              }}
              disabled={retryCount >= 3}
              className="play-retry-button inline-flex items-center gap-2"
            >
              <svg
                width="12"
                height="12"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
                <path d="M3 3v5h5" />
              </svg>
              {retryCount >= 3 ? t("retryMaxed") : t("regenerate")}
            </button>
          </div>
        )}

        <div className="play-composer-spacer" aria-hidden />
      </div>

      <JumpToLatestButton visible={showJump} onClick={jumpToLatest} />
    </div>
  );
}
