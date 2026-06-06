"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";

import { formatJsonInput } from "@/lib/admin-format";

interface JsonFieldProps<T> {
  label?: string;
  help?: string;
  value: T;
  onChange: (next: T) => void;
  rows?: number;
  /** 折叠（默认折叠在 details 内） */
  collapsible?: boolean;
  /** 默认是否展开 */
  defaultOpen?: boolean;
  /** details 的可见 summary 文案 */
  summary?: string;
  /** 关闭时的 summary（替代展开后的文案，可选） */
  summaryOpen?: string;
}

/**
 * 可结构化降级到 JSON 的字段。
 * - 展示 textarea，blur 时尝试 parse；parse 失败显示红字 inline error，不丢用户输入
 * - 默认折叠在 details 内（collapsible=true 时）作为"高级模式"
 */
export function JsonField<T extends Record<string, unknown> | unknown[] | null>({
  label,
  help,
  value,
  onChange,
  rows = 6,
  collapsible = false,
  defaultOpen = false,
  summary,
  summaryOpen,
}: JsonFieldProps<T>) {
  const t = useTranslations("admin.editor.json");
  const [text, setText] = useState(() => formatJsonInput(value ?? null));
  const [error, setError] = useState<string | null>(null);
  const [lastValue, setLastValue] = useState(value);

  // sync external value → text on identity change. Adjust-during-render to avoid effect setState.
  if (value !== lastValue) {
    setLastValue(value);
    let textMatchesValue = false;
    try {
      textMatchesValue =
        JSON.stringify(JSON.parse(text || "null")) === JSON.stringify(value ?? null);
    } catch {
      // text is malformed mid-edit; don't clobber it
      textMatchesValue = true;
    }
    if (!textMatchesValue) {
      setText(formatJsonInput(value ?? null));
    }
  }

  const commit = () => {
    const trimmed = text.trim();
    if (!trimmed) {
      onChange((value && typeof value === "object" && !Array.isArray(value) ? {} : null) as T);
      setError(null);
      return;
    }
    try {
      const parsed = JSON.parse(trimmed);
      onChange(parsed as T);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : t("invalid"));
    }
  };

  const fieldNode = (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--lv-s-2)" }}>
      {label && <label className="lv-form-label">{label}</label>}
      <textarea
        className="lv-input lv-input--textarea"
        style={{
          fontFamily: "var(--lv-font-mono)",
          fontSize: "var(--lv-t-meta)",
          lineHeight: 1.5,
          minHeight: rows * 18,
          whiteSpace: "pre",
        }}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onBlur={commit}
        spellCheck={false}
      />
      {error ? (
        <span className="lv-form-error" role="alert">
          {error}
        </span>
      ) : help ? (
        <span className="lv-form-help">{help}</span>
      ) : null}
    </div>
  );

  if (!collapsible) return fieldNode;

  return (
    <details
      open={defaultOpen}
      style={{
        border: "1px solid var(--lv-line)",
        borderRadius: "var(--lv-r-card)",
        padding: "var(--lv-s-3) var(--lv-s-4)",
      }}
    >
      <summary
        className="lv-t-caps"
        style={{
          cursor: "pointer",
          color: "var(--lv-ink-3)",
          listStyle: "none",
          minHeight: 32,
          display: "inline-flex",
          alignItems: "center",
        }}
      >
        {summary ?? t("valid")}
      </summary>
      <div style={{ marginTop: "var(--lv-s-3)" }}>
        {summaryOpen && (
          <p className="lv-form-help" style={{ marginTop: 0, marginBottom: "var(--lv-s-2)" }}>
            {summaryOpen}
          </p>
        )}
        {fieldNode}
      </div>
    </details>
  );
}
