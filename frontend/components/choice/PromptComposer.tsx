"use client";

/**
 * 克制型创作输入 —— 工坊生成页「世界描述 / 剧本概述」共用。
 *
 * 视觉沿用 start 页 ChoiceScene 的令牌语言：
 * 多行 textarea 使用 start 页同款安静填充 / 中性 focus，全宽象牙 CTA 走 .lv-cta-ivory。
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
        className="lv-prompt-composer-input"
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
          max-width: 400px;
          margin: 0 auto;
          display: flex;
          flex-direction: column;
        }
        @media (max-width: 768px) {
          .lv-theme .lv-prompt-composer { max-width: 292px; }
        }
        .lv-theme .lv-prompt-composer-label {
          font-family: var(--lv-font-mono);
          font-size: 10px;
          letter-spacing: 0.16em;
          text-transform: uppercase;
          color: var(--lv-ink-3);
          margin: 0 0 8px 16px;
        }
        .lv-theme .lv-prompt-composer-input {
          width: 100%;
          min-height: 118px;
          border-radius: 24px;
          border: 1px solid rgba(245, 242, 235, 0.11);
          background: rgba(5, 5, 7, 0.58);
          color: var(--lv-ink);
          padding: 15px 18px;
          font-family: var(--lv-font-sans);
          font-size: var(--lv-t-body);
          line-height: 1.65;
          outline: none;
          resize: none;
          margin: 0 0 14px;
          box-shadow:
            inset 0 1px 0 rgba(245, 242, 235, 0.04),
            0 1px 0 rgba(0, 0, 0, 0.28);
          transition:
            border-color var(--lv-dur-fast) var(--lv-ease),
            background var(--lv-dur-fast) var(--lv-ease),
            box-shadow var(--lv-dur-fast) var(--lv-ease);
        }
        .lv-theme .lv-prompt-composer-input::placeholder {
          color: var(--lv-ink-4);
        }
        .lv-theme .lv-prompt-composer-input:focus {
          border-color: rgba(245, 242, 235, 0.24);
          background: rgba(5, 5, 7, 0.78);
          box-shadow:
            inset 0 1px 0 rgba(245, 242, 235, 0.06),
            0 0 0 1px rgba(245, 242, 235, 0.03);
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
