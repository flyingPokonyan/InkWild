"use client";

import { useId, useState } from "react";

import { arrayToLines, linesToArray } from "@/lib/admin-format";

interface ChipsInputProps {
  label?: string;
  help?: string;
  value: string[];
  onChange: (next: string[]) => void;
  placeholder?: string;
  rows?: number;
}

/**
 * 多行文本字段：每行一条，转 string[]。
 * 比裸 textarea 多了 chip 预览，让作者一眼看到几条。
 */
export function ChipsInput({
  label,
  help,
  value,
  onChange,
  placeholder,
  rows = 4,
}: ChipsInputProps) {
  const id = useId();
  const [text, setText] = useState(() => arrayToLines(value));
  const [lastValue, setLastValue] = useState(value);

  // sync external value if upstream replaced (e.g. payload reload).
  // 用 "adjust state during render" 模式避开 useEffect setState。
  if (value !== lastValue) {
    setLastValue(value);
    const incoming = arrayToLines(value);
    if (text !== incoming && incoming !== arrayToLines(linesToArray(text))) {
      setText(incoming);
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--lv-s-2)" }}>
      {label && (
        <label htmlFor={id} className="lv-form-label">
          {label}
        </label>
      )}
      <textarea
        id={id}
        className="lv-input lv-input--textarea"
        style={{ minHeight: rows * 22 }}
        value={text}
        placeholder={placeholder}
        onChange={(e) => {
          setText(e.target.value);
          onChange(linesToArray(e.target.value));
        }}
      />
      {value.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
          {value.slice(0, 12).map((item, i) => (
            <span
              key={`${item}-${i}`}
              className="lv-t-meta"
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 4,
                padding: "2px 10px",
                border: "1px solid var(--lv-line)",
                borderRadius: "var(--lv-r-pill)",
                color: "var(--lv-ink-2)",
                background: "rgba(255,255,255,0.02)",
              }}
            >
              {item}
            </span>
          ))}
          {value.length > 12 && (
            <span
              className="lv-t-meta"
              style={{
                padding: "2px 10px",
                color: "var(--lv-ink-3)",
              }}
            >
              +{value.length - 12}
            </span>
          )}
        </div>
      )}
      {help && <span className="lv-form-help">{help}</span>}
    </div>
  );
}
