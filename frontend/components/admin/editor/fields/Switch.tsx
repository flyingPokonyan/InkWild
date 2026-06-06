"use client";

interface SwitchProps {
  label: string;
  description?: string;
  checked: boolean;
  onChange: (next: boolean) => void;
}

/**
 * 切换开关（44px 触摸目标）。开启态用 accent。
 */
export function Switch({ label, description, checked, onChange }: SwitchProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      style={{
        display: "flex",
        alignItems: "center",
        gap: "var(--lv-s-3)",
        background: "transparent",
        border: 0,
        cursor: "pointer",
        padding: "var(--lv-s-2) 0",
        textAlign: "left",
        color: "inherit",
      }}
    >
      <span
        aria-hidden
        style={{
          position: "relative",
          width: 36,
          height: 20,
          flexShrink: 0,
          borderRadius: "var(--lv-r-pill)",
          background: checked ? "var(--lv-accent)" : "rgba(255,255,255,0.08)",
          border: "1px solid",
          borderColor: checked ? "var(--lv-accent)" : "var(--lv-line-2)",
          transition: "all var(--lv-dur-fast) var(--lv-ease)",
        }}
      >
        <span
          style={{
            position: "absolute",
            top: 2,
            left: checked ? 18 : 2,
            width: 14,
            height: 14,
            borderRadius: "50%",
            background: checked ? "#1a1610" : "var(--lv-ink-2)",
            transition: "left var(--lv-dur-fast) var(--lv-ease)",
          }}
        />
      </span>
      <span style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 0 }}>
        <span className="lv-t-body" style={{ color: "var(--lv-ink)" }}>
          {label}
        </span>
        {description && (
          <span className="lv-t-meta" style={{ color: "var(--lv-ink-3)" }}>
            {description}
          </span>
        )}
      </span>
    </button>
  );
}
