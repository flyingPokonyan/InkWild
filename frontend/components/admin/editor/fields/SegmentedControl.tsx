"use client";

interface Option {
  value: string;
  label: string;
  hint?: string;
}

interface SegmentedControlProps {
  label?: string;
  value: string;
  options: Option[];
  onChange: (next: string) => void;
}

/**
 * 横向分段选择（trigger_type / ending_type 用）。
 * touch ≥ 44px。选中态走 ink，不用 accent 装饰。
 */
export function SegmentedControl({ label, value, options, onChange }: SegmentedControlProps) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--lv-s-2)" }}>
      {label && <span className="lv-form-label">{label}</span>}
      <div
        role="radiogroup"
        aria-label={label}
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: 6,
        }}
      >
        {options.map((opt) => {
          const selected = opt.value === value;
          return (
            <button
              key={opt.value}
              type="button"
              role="radio"
              aria-checked={selected}
              onClick={() => onChange(opt.value)}
              className="lv-t-meta"
              style={{
                minHeight: 44,
                padding: "0 var(--lv-s-4)",
                borderRadius: "var(--lv-r-pill)",
                border: "1px solid",
                borderColor: selected ? "var(--lv-line-2)" : "var(--lv-line)",
                background: selected ? "rgba(255,255,255,0.07)" : "transparent",
                color: selected ? "var(--lv-ink)" : "var(--lv-ink-3)",
                cursor: "pointer",
                transition: "all var(--lv-dur-fast) var(--lv-ease)",
                whiteSpace: "nowrap",
              }}
            >
              {opt.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}
