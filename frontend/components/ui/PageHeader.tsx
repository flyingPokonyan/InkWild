import { ReactNode } from "react";

interface PageHeaderProps {
  /** 上方 caps 小字 */
  eyebrow?: ReactNode;
  /** 主标题，serif t-h1（32px 桌面 / 24px 移动）。不要在这里写四字大标题装首屏。 */
  title: ReactNode;
  /** 副标题，sans t-body 一行。≤ 30 字。 */
  subtitle?: ReactNode;
  /** 右侧操作区（toolbar / 排序等） */
  trailing?: ReactNode;
}

/**
 * 压扁 200px 内的页面头部（§7.3 §8.4）。
 * 不是占满首屏的 hero——只放页面级 t-h1 + 一行引文。
 * Hero 只允许出现在首页。
 */
export function PageHeader({ eyebrow, title, subtitle, trailing }: PageHeaderProps) {
  return (
    <header
      style={{
        display: "flex",
        alignItems: "flex-end",
        justifyContent: "space-between",
        gap: "var(--lv-s-6)",
        padding: "var(--lv-s-16) 0 var(--lv-s-8)",
        borderBottom: "1px solid var(--lv-line)",
      }}
    >
      <div style={{ display: "flex", flexDirection: "column", gap: "var(--lv-s-2)", minWidth: 0 }}>
        {eyebrow && <div className="lv-t-caps">{eyebrow}</div>}
        <h1 className="lv-t-h1">{title}</h1>
        {subtitle && (
          <p className="lv-t-body" style={{ color: "var(--lv-ink-2)", margin: 0 }}>
            {subtitle}
          </p>
        )}
      </div>
      {trailing && <div style={{ flexShrink: 0 }}>{trailing}</div>}
    </header>
  );
}
