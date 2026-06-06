"use client";

/**
 * 克制型创作输入 —— 工坊生成页「世界描述 / 剧本概述」共用。
 *
 * 视觉沿用 start 页 ChoiceScene 的令牌语言：
 * 多行 textarea 走 .lv-input 基线，全宽象牙 CTA 走 .lv-cta-ivory。
 * Enter 提交，Shift+Enter 换行。
 */

import { useEffect, useRef } from "react";
import { motion } from "motion/react";

import { lvStaggerItem } from "@/lib/motion";

interface PromptComposerProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  placeholder: string;
  ctaLabel: string;
  label?: string;
  ariaLabel?: string;
  error?: string | null;
  autoFocus?: boolean;
  rows?: number;
  maxLength?: number;
  /** false 时禁用提交（按钮置灰 + Enter 不触发），但 textarea 仍可编辑。默认 true。 */
  canSubmit?: boolean;
}

export function PromptComposer({
  value,
  onChange,
  onSubmit,
  placeholder,
  ctaLabel,
  label,
  ariaLabel,
  error,
  autoFocus = false,
  rows = 3,
  maxLength = 280,
  canSubmit = true,
}: PromptComposerProps) {
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (autoFocus) ref.current?.focus();
  }, [autoFocus]);

  const handleKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      if (canSubmit) onSubmit();
    }
  };

  return (
    <motion.div variants={lvStaggerItem} className="lv-prompt-composer">
      {label && <div className="lv-prompt-composer-label">{label}</div>}
      <textarea
        ref={ref}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        aria-label={ariaLabel ?? label ?? placeholder}
        rows={rows}
        maxLength={maxLength}
        className="lv-input lv-input--textarea lv-prompt-composer-input"
      />
      {error && <span className="lv-form-error lv-prompt-composer-error">{error}</span>}
      <button
        type="button"
        onClick={onSubmit}
        disabled={!canSubmit}
        className="lv-cta-ivory"
      >
        {ctaLabel}
      </button>

      <style jsx global>{`
        .lv-theme .lv-prompt-composer {
          width: 100%;
          max-width: 420px;
          margin: 0 auto;
          display: flex;
          flex-direction: column;
        }
        @media (max-width: 768px) {
          .lv-theme .lv-prompt-composer { max-width: 320px; }
        }
        .lv-theme .lv-prompt-composer-label {
          font-family: var(--lv-font-mono);
          font-size: 10px;
          letter-spacing: 0.16em;
          text-transform: uppercase;
          color: var(--lv-ink-3);
          margin: 0 0 8px 4px;
        }
        .lv-theme .lv-prompt-composer-input {
          min-height: 118px;
          resize: none;
          margin: 0 0 14px;
        }
        .lv-theme .lv-prompt-composer-error {
          width: 100%;
          justify-content: center;
          text-align: center;
          margin: 0 0 12px;
        }
      `}</style>
    </motion.div>
  );
}
