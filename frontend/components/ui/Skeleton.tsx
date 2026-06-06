import { CSSProperties } from "react";

interface SkeletonProps {
  /** 默认 100% × 16px */
  width?: number | string;
  height?: number | string;
  /** 圆角默认 lv-r-card (16)；卡片骨架用默认，文字骨架建议 4 */
  radius?: number | string;
  className?: string;
  style?: CSSProperties;
}

/**
 * 灰阶轮廓占位。列表/卡片加载用这个，不用 spinner（§10.1）。
 * 建议在容器里放 1-3 个，对应卡片大致比例。
 */
export function Skeleton({
  width = "100%",
  height = 16,
  radius = "var(--lv-r-card)",
  className = "",
  style,
}: SkeletonProps) {
  return (
    <div
      className={className}
      style={{
        width,
        height,
        borderRadius: radius,
        background: "var(--lv-line-2)",
        ...style,
      }}
    />
  );
}
