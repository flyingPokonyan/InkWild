import { ButtonHTMLAttributes, forwardRef } from "react";

interface ChipProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  selected?: boolean;
}

/**
 * Selectable filter chip. 选中态走 ink（§2.2），不用 accent。
 * 形状 pill，字号 t-meta，高度 44（触摸目标 §13）。
 */
export const Chip = forwardRef<HTMLButtonElement, ChipProps>(
  ({ selected = false, className = "", style, ...rest }, ref) => {
    const composed = ["lv-chip", "lv-t-meta", selected ? "lv-chip--selected" : "", className]
      .filter(Boolean)
      .join(" ");
    const selectedStyle = selected
      ? {
          background: "rgba(255, 255, 255, 0.07)",
          color: "var(--lv-ink)",
          borderColor: "var(--lv-line-2)",
        }
      : {
          background: "transparent",
          color: "var(--lv-ink-2)",
          borderColor: "var(--lv-line)",
        };
    return (
      <button
        ref={ref}
        type="button"
        className={composed}
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: "var(--lv-s-2)",
          minHeight: 44,
          padding: "var(--lv-s-2) var(--lv-s-4)",
          border: "1px solid",
          borderRadius: "var(--lv-r-pill)",
          fontFamily: "var(--lv-font-sans)",
          lineHeight: 1,
          cursor: "pointer",
          transition: "all var(--lv-dur-fast) var(--lv-ease)",
          whiteSpace: "nowrap",
          ...selectedStyle,
          ...style,
        }}
        {...rest}
      />
    );
  },
);
Chip.displayName = "Chip";
