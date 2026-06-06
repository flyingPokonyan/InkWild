"use client";

import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";

const FALLBACK = "linear-gradient(135deg, var(--lv-bg-1), var(--lv-bg-2))";

interface LazyCoverProps {
  /** 封面 URL（建议已过 ossThumb）。空则一直显示 fallback。 */
  url?: string | null;
  /** 未进入视口 / 无图时的占位背景，默认暗渐变。 */
  fallback?: string;
  /** 首屏 / LCP 封面传 true，跳过懒加载立即出图。 */
  eager?: boolean;
  style?: CSSProperties;
  className?: string;
  children?: ReactNode;
  "aria-hidden"?: boolean;
}

/**
 * 懒加载封面层。`background-image` 无法原生 lazy —— 用 IntersectionObserver，
 * 进入视口前 600px 才贴图，首屏外的封面不抢首屏带宽。`eager` 给首屏 hero。
 * 行为对齐被替换的 `<div style={{ backgroundImage }} />`：默认 cover/center，可被 style 覆盖。
 */
export function LazyCover({ url, fallback = FALLBACK, eager = false, style, className, children, ...rest }: LazyCoverProps) {
  const ref = useRef<HTMLDivElement>(null);
  const [show, setShow] = useState(eager);

  useEffect(() => {
    if (show || !url) return;
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          setShow(true);
          io.disconnect();
        }
      },
      { rootMargin: "600px 0px" },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [show, url]);

  return (
    <div
      ref={ref}
      className={className}
      {...rest}
      style={{
        backgroundSize: "cover",
        backgroundPosition: "center",
        ...style,
        backgroundImage: show && url ? `url(${url})` : fallback,
      }}
    >
      {children}
    </div>
  );
}
