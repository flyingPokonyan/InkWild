"use client";

import { useState, type TextareaHTMLAttributes } from "react";

/**
 * 失焦时收成 1 行；聚焦时展开到最多 3 行（更多则内部滚动）。
 * 用于"扫一眼一行就够、要细看再点开"的场景，比如地点详情。
 */
export function FocusExpandTextarea({
  value,
  onChange,
  placeholder,
  style,
  ...rest
}: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  const [focused, setFocused] = useState(false);
  const collapsed = 24;
  const expanded = 78;

  return (
    <textarea
      value={value}
      onChange={onChange}
      placeholder={placeholder}
      rows={focused ? 3 : 1}
      style={{
        height: focused ? expanded : collapsed,
        overflow: focused ? "auto" : "hidden",
        resize: "none",
        transition: "height var(--lv-dur-fast) var(--lv-ease)",
        lineHeight: 1.5,
        ...style,
      }}
      onFocus={(e) => {
        setFocused(true);
        rest.onFocus?.(e);
      }}
      onBlur={(e) => {
        setFocused(false);
        rest.onBlur?.(e);
      }}
      {...rest}
    />
  );
}
