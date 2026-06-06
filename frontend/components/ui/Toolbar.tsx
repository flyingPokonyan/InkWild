import { ReactNode } from "react";

interface ToolbarProps {
  /** 左侧：分类 / 搜索 / 筛选（必须左对齐 §8.1） */
  leading?: ReactNode;
  /** 右侧：排序 / 视图切换 */
  trailing?: ReactNode;
  /** 工具栏自身的额外 className（罕见） */
  className?: string;
}

/**
 * 页面级工具栏（§8.1）。**必须左对齐**，禁止居中孤岛工具栏。
 * 用法：<Toolbar leading={<Chips/>} trailing={<SortDropdown/>} />
 */
export function Toolbar({ leading, trailing, className = "" }: ToolbarProps) {
  return (
    <div
      className={className}
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: "var(--lv-s-4)",
        flexWrap: "wrap",
        padding: "var(--lv-s-6) 0",
      }}
    >
      <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--lv-s-2)", alignItems: "center", flex: 1, minWidth: 0 }}>
        {leading}
      </div>
      {trailing && (
        <div style={{ display: "flex", gap: "var(--lv-s-2)", alignItems: "center", flexShrink: 0 }}>
          {trailing}
        </div>
      )}
    </div>
  );
}
