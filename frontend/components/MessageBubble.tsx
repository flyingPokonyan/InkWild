"use client";

import type { ChatMessage } from "@/lib/types";
import { useGameStore } from "@/stores/game";

/**
 * §12.2 / §12.3 + v2.2 design refactor:
 *  · 玩家消息：删 border-left 色块，仅 YOU › caps eyebrow + italic body
 *    eyebrow 颜色随模式（剧本暖金 / 自由苔绿），通过 --play-accent CSS var 注入
 *  · narrator：sans clamp 15→17 + lh 1.85 + streaming 末尾 cursor (.play-message-cursor)
 *  · 字体合规：所有中文走 sans，YOU › 西文走 mono caps（§1.1 合规）
 */
export function MessageBubble({
  message,
  isActive = false,
}: {
  message: ChatMessage;
  isActive?: boolean;
}) {
  const mode = useGameStore((state) => state.mode);
  const accent = mode === "free" ? "var(--lv-accent-2)" : "var(--lv-accent)";

  if (message.role === "user") {
    return (
      <div
        className="play-message-player"
        style={{ ["--play-accent" as string]: accent } as React.CSSProperties}
      >
        <div className="play-message-player-eyebrow">You &rsaquo;</div>
        <div className="play-message-player-body">{message.content}</div>
      </div>
    );
  }

  // narrator
  return (
    <div className="play-message-narrator" style={{ opacity: isActive ? 1 : 0.92 }}>
      {message.content.split("\n").map((paragraph, idx) => (
        <p
          key={idx}
          style={idx > 0 && paragraph.trim() !== "" ? { marginTop: "var(--lv-s-6)" } : undefined}
        >
          {paragraph}
          {isActive && idx === message.content.split("\n").length - 1 && (
            <span className="play-message-cursor" aria-hidden />
          )}
        </p>
      ))}
    </div>
  );
}
