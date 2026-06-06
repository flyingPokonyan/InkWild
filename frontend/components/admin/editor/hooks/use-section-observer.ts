"use client";

import { useEffect, useState } from "react";

interface UseSectionObserverOptions {
  ids: string[];
  /** 顶部 sticky 占位（draft strip 高度） */
  topOffset?: number;
}

/**
 * IntersectionObserver 包装：返回当前 viewport 中最靠上的 section id。
 */
export function useSectionObserver({ ids, topOffset = 80 }: UseSectionObserverOptions) {
  const [activeId, setActiveId] = useState<string>(ids[0] ?? "");

  useEffect(() => {
    if (ids.length === 0) return;
    const elements = ids
      .map((id) => document.getElementById(id))
      .filter((el): el is HTMLElement => el !== null);
    if (elements.length === 0) return;

    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (visible.length > 0) {
          setActiveId(visible[0].target.id);
        }
      },
      {
        rootMargin: `-${topOffset}px 0px -60% 0px`,
        threshold: 0,
      },
    );

    elements.forEach((el) => observer.observe(el));
    return () => observer.disconnect();
  }, [ids, topOffset]);

  return activeId;
}
