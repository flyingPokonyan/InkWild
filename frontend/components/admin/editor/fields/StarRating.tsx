"use client";

interface StarRatingProps {
  label?: string;
  value: number;
  onChange: (next: number) => void;
  max?: number;
}

/**
 * 1-N 星点选择器。touch target 44px，键盘可达。
 */
export function StarRating({ label, value, onChange, max = 5 }: StarRatingProps) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--lv-s-2)" }}>
      {label && <span className="lv-form-label">{label}</span>}
      <div role="radiogroup" aria-label={label} style={{ display: "flex", gap: 4 }}>
        {Array.from({ length: max }).map((_, i) => {
          const starValue = i + 1;
          const filled = starValue <= value;
          return (
            <button
              key={starValue}
              type="button"
              role="radio"
              aria-checked={filled}
              aria-label={`${starValue} / ${max}`}
              onClick={() => onChange(starValue)}
              style={{
                width: 44,
                height: 44,
                display: "grid",
                placeItems: "center",
                background: "transparent",
                border: 0,
                cursor: "pointer",
                color: filled ? "var(--lv-accent)" : "var(--lv-ink-4)",
                transition: "color var(--lv-dur-fast) var(--lv-ease)",
              }}
            >
              <Diamond filled={filled} />
            </button>
          );
        })}
      </div>
    </div>
  );
}

function Diamond({ filled }: { filled: boolean }) {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden>
      <path
        d="M7 1 L13 7 L7 13 L1 7 Z"
        fill={filled ? "currentColor" : "none"}
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinejoin="round"
      />
    </svg>
  );
}
