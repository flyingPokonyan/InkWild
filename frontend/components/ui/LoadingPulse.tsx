interface LoadingPulseProps {
  /**
   * - "inline"：8px 暖金圆（文本旁小 feedback）
   * - "block"：Branch + Grow + 下方文案（品牌入场，全屏/页面加载用，居中）
   * - "branch"：只渲染小号 Branch glyph（持续 Grow 动画），供思考态进度行内左对齐用
   */
  variant?: "inline" | "block" | "branch";
  /** block 变体的 Branch 高度（默认 64px）；branch 变体默认 18px */
  size?: number;
  /** block 变体下方文案。默认 "正在加载"。caller 自己已有上下文文字时传 "" 隐藏。 */
  label?: string;
}

/** 复用 Branch + Grow 路径（动画在 globals.css `.lv-loading-branch .lv-grow-*`，
 *  2.5s infinite，prefers-reduced-motion 自带降级）。 */
function BranchGlyph({ size, label }: { size: number; label?: string }) {
  return (
    <svg
      className="lv-loading-branch"
      viewBox="0 0 100 120"
      width={size * 0.83}
      height={size}
      fill="none"
      role="img"
      aria-label={label || "思考中"}
      style={{ display: "block", flexShrink: 0 }}
    >
      <g stroke="currentColor" strokeWidth="6" strokeLinecap="round">
        <path className="lv-grow-trunk" d="M 50 112 Q 50 84, 52 56 Q 54 32, 52 12" />
        <path className="lv-grow-b1" d="M 51 84 Q 62 80, 76 70" />
        <path className="lv-grow-b2" d="M 52 58 Q 40 52, 28 46" />
        <path className="lv-grow-b3" d="M 52 28 Q 62 24, 72 18" />
        <path className="lv-grow-tip" d="M 76 70 L 81 66" />
      </g>
    </svg>
  );
}

/**
 * Loading 指示。
 * - inline: 8px 暖金圆 1800ms 脉冲（小 UI feedback，§10.1 兼容）
 * - block: Branch + Grow 2.5s + 下方 italic serif 文案（品牌入场，全屏/页面加载用）
 * - branch: 小号 Branch glyph（持续动画），思考态进度行内左对齐用
 */
export function LoadingPulse({
  variant = "block",
  size,
  label = "正在加载",
}: LoadingPulseProps) {
  if (variant === "inline") {
    return <span className="lv-loading-pulse" style={{ display: "inline-block" }} />;
  }
  if (variant === "branch") {
    return <BranchGlyph size={size ?? 18} label={label} />;
  }
  const blockSize = size ?? 64;
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: 18,
        padding: "var(--lv-s-16) 0",
        color: "var(--lv-ink)",
      }}
    >
      <BranchGlyph size={blockSize} label={label} />
      {label && (
        <div
          style={{
            fontFamily: "var(--lv-font-serif)",
            fontSize: 13.5,
            color: "var(--lv-ink-3)",
            letterSpacing: "0.02em",
            opacity: 0.85,
          }}
        >
          {label}
        </div>
      )}
    </div>
  );
}
