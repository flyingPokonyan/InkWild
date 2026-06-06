"use client";

import { motion } from "motion/react";

import { lvStaggerItem } from "@/lib/motion";

interface AuthorsNotePromptProps {
  value: string;
  placeholder: string;
  ariaLabel: string;
  ctaLabel: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  error?: string | null;
  maxLength?: number;
}

export function AuthorsNotePrompt({
  value,
  placeholder,
  ariaLabel,
  ctaLabel,
  onChange,
  onSubmit,
  error,
  maxLength = 200,
}: AuthorsNotePromptProps) {
  const handleKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter") {
      event.preventDefault();
      onSubmit();
    }
  };

  return (
    <motion.div
      variants={lvStaggerItem}
      className="lv-authors-note-prompt"
    >
      <div className="lv-authors-note-label">{ariaLabel}</div>
      <input
        type="text"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        maxLength={maxLength}
        aria-label={ariaLabel}
        className="lv-authors-note-input"
      />
      {error && (
        <span className="lv-form-error lv-authors-note-error">{error}</span>
      )}
      <button
        type="button"
        onClick={onSubmit}
        className="lv-authors-note-button"
      >
        {ctaLabel}
      </button>

      <style jsx global>{`
        .lv-theme .lv-authors-note-prompt {
          width: 100%;
          max-width: 380px;
          margin: 0 auto;
          display: flex;
          flex-direction: column;
        }

        @media (max-width: 768px) {
          .lv-theme .lv-authors-note-prompt {
            max-width: 292px;
          }
        }

        .lv-theme .lv-authors-note-label {
          font-family: var(--lv-font-mono);
          font-size: 10px;
          letter-spacing: 0.16em;
          text-transform: uppercase;
          color: var(--lv-ink-3);
          margin: 0 0 8px 16px;
        }

        .lv-theme .lv-authors-note-input {
          height: 46px;
          border-radius: var(--lv-r-pill);
          border: 1px solid rgba(255, 255, 255, 0.10);
          background: rgba(255, 255, 255, 0.045);
          color: var(--lv-ink);
          padding: 0 16px;
          font-size: 12px;
          font-family: var(--lv-font-sans);
          line-height: 46px;
          width: 100%;
          margin: 0 0 12px;
          outline: none;
          transition:
            border-color var(--lv-dur-fast) var(--lv-ease),
            background var(--lv-dur-fast) var(--lv-ease);
        }

        .lv-theme .lv-authors-note-input::placeholder {
          color: var(--lv-ink-3);
        }

        .lv-theme .lv-authors-note-input:focus {
          border-color: rgba(255, 255, 255, 0.22);
          background: rgba(255, 255, 255, 0.07);
        }

        .lv-theme .lv-authors-note-error {
          width: 100%;
          justify-content: center;
          text-align: center;
          margin: 0 0 12px;
        }

        .lv-theme .lv-authors-note-button {
          height: 48px;
          border-radius: var(--lv-r-pill);
          background: rgba(245, 242, 235, 0.94);
          color: var(--lv-bg);
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 14px;
          font-weight: 600;
          font-family: var(--lv-font-sans);
          border: none;
          width: 100%;
          cursor: pointer;
          transition:
            background var(--lv-dur-fast) var(--lv-ease),
            transform var(--lv-dur-fast) var(--lv-ease);
        }

        .lv-theme .lv-authors-note-button:hover:not(:disabled) {
          background: rgba(245, 242, 235, 1);
        }

        .lv-theme .lv-authors-note-button:active:not(:disabled) {
          transform: translateY(1px);
        }
      `}</style>
    </motion.div>
  );
}
