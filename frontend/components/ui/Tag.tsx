import { HTMLAttributes } from "react";

interface TagProps extends HTMLAttributes<HTMLSpanElement> {
  /** mono caps 标签，色按 ink-3 默认。需要强调用 color prop 覆盖。 */
  color?: string;
}

/**
 * 小型 caps 标签：mono 11px，全大写，默认 ink-3 灰阶。
 * 用于题材、时代、模式编码 ◆/◇、版本号等。
 */
export function Tag({ color, className = "", style, children, ...rest }: TagProps) {
  return (
    <span
      className={`lv-t-caps ${className}`.trim()}
      style={{ color: color ?? "var(--lv-ink-3)", ...style }}
      {...rest}
    >
      {children}
    </span>
  );
}
