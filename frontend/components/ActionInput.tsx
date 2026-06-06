"use client";

import { useEffect, useRef, useState, type ChangeEvent, type KeyboardEvent } from "react";
import { useTranslations } from "next-intl";

import { useConfirm } from "@/components/ui/ConfirmDialog";
import { isExitIntent } from "@/lib/exit-intent";
import { useGameStore } from "@/stores/game";

import { QuickActions } from "./QuickActions";

/**
 * §12.7 + v2.2 design refactor:
 *  · multi-line textarea + autosize (useEffect-based lifecycle)
 *  · 内嵌 send icon button（圆形 32px，含加载旋转状态）
 *  · 容器透明 + 1px ink-line border，跟 stage 同层不浮起
 *  · 圆角 24px（chat-style 视觉惯例，§3 单独破例）
 *  · accent 颜色随模式（剧本暖金 / 自由苔绿）通过 --play-accent CSS var 注入
 *  · processing / streaming 都 disabled，避免重复提交
 */
export function ActionInput() {
  const [input, setInput] = useState("");
  const taRef = useRef<HTMLTextAreaElement | null>(null);
  const sendAction = useGameStore((state) => state.sendAction);
  const endGame = useGameStore((state) => state.endGame);
  const isStreaming = useGameStore((state) => state.isStreaming);
  const mode = useGameStore((state) => state.mode);
  const t = useTranslations("play");
  const confirm = useConfirm();

  const accent = mode === "free" ? "var(--lv-accent-2)" : "var(--lv-accent)";

  // §12.7: Robust auto-sizing based on React render lifecycle (no flickers/jumps)
  useEffect(() => {
    const ta = taRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight, 200) + "px";
  }, [input]);

  const handleChange = (e: ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
  };

  const handleKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleSubmit = async () => {
    const text = input.trim();
    if (!text || isStreaming) return;
    // 主动退场意图：只弹确认，绝不直接结束（误判最坏 = 弹个框点继续）。
    // 命中策略见 lib/exit-intent.ts —— 整句锚定元词，剧情台词/叙事不会误伤。
    if (isExitIntent(text)) {
      const ok = await confirm({
        title: "结束这一局？",
        message: "会为你生成一段落幕收场，结束后可在历史里回顾。",
        confirmText: "结束并落幕",
        cancelText: "继续游戏",
      });
      if (!ok) return; // 保留输入，玩家可继续
      setInput("");
      void endGame();
      return;
    }
    setInput("");
    void sendAction(text);
  };

  return (
    <div className="play-composer">
      <div className="play-composer-inner">
        <QuickActions />
        <div
          className="play-compose-row"
          style={{ ["--play-accent" as string]: accent } as React.CSSProperties}
        >
          <textarea
            ref={taRef}
            rows={1}
            value={input}
            onChange={handleChange}
            onKeyDown={handleKey}
            placeholder={t("inputPlaceholder")}
            disabled={isStreaming}
            className="play-compose-input"
            aria-label={t("inputPlaceholder")}
          />
          <button
            type="button"
            onClick={handleSubmit}
            disabled={isStreaming || !input.trim()}
            className="play-compose-submit"
            aria-label={t("submit")}
            title={t("submit")}
          >
            {isStreaming ? (
              <span className="play-composer-submit-loading" aria-hidden="true" />
            ) : (
              <svg
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M12 19V5" />
                <path d="m5 12 7-7 7 7" />
              </svg>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

