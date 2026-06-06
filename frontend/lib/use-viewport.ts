"use client";

import { useEffect, useState } from "react";

const MOBILE_QUERY = "(max-width: 767px)";

/**
 * 监听视口宽度，返回是否为移动断点（< 768px）。
 * 注意：SSR 阶段返回 false（默认桌面），mount 后立刻同步真实值——
 * 不会有视觉跳变，因为 BottomTabBar / Navbar 的可见性主要由 CSS 媒体查询控制，
 * 此 hook 仅用于行为分支（如键盘事件、抽屉模式切换）。
 */
export function useIsMobile() {
  const [isMobile, setIsMobile] = useState(false);

  useEffect(() => {
    const mql = window.matchMedia(MOBILE_QUERY);
    const sync = () => setIsMobile(mql.matches);
    sync();
    mql.addEventListener("change", sync);
    return () => mql.removeEventListener("change", sync);
  }, []);

  return isMobile;
}
