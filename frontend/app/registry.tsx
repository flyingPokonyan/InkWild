"use client";

import React, { useState } from "react";
import { useServerInsertedHTML } from "next/navigation";
import { StyleRegistry, createStyleRegistry } from "styled-jsx";

// styled-jsx 的 SSR 收集器。App Router 下 <style jsx> 默认不进首屏 HTML，
// 必须用 registry + useServerInsertedHTML 把规则在 SSR 阶段刷进 <head>，
// 否则首屏拿不到布局样式，会出现"内容先按默认块流（左对齐）画一遍、
// hydrate 后才归位"的 FOUC。官方方案见 next docs 01-app/02-guides/css-in-js。
export default function StyledJsxRegistry({
  children,
}: {
  children: React.ReactNode;
}) {
  // 懒初始化，整个生命周期只建一次 registry
  const [jsxStyleRegistry] = useState(() => createStyleRegistry());

  useServerInsertedHTML(() => {
    const styles = jsxStyleRegistry.styles();
    jsxStyleRegistry.flush();
    return <>{styles}</>;
  });

  return <StyleRegistry registry={jsxStyleRegistry}>{children}</StyleRegistry>;
}
