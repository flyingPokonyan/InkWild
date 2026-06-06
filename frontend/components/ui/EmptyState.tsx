import { ReactNode } from "react";

interface EmptyStateProps {
  /** 一句话状态，sans t-body */
  title: ReactNode;
  /** 次级提示，sans t-meta */
  hint?: ReactNode;
  /** 1 个 CTA。多个就是错的（§10.2）。 */
  action?: ReactNode;
}

/**
 * 空态规范（§10.2）。
 * 禁止：插画占位、emoji、SVG 卡通、"哎呀这里空空~" 类口语化文案。
 */
export function EmptyState({ title, hint, action }: EmptyStateProps) {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: "var(--lv-s-3)",
        padding: "var(--lv-s-16) var(--lv-s-4)",
        textAlign: "center",
      }}
    >
      <p className="lv-t-body" style={{ margin: 0 }}>
        {title}
      </p>
      {hint && (
        <p className="lv-t-meta" style={{ margin: 0 }}>
          {hint}
        </p>
      )}
      {action && <div style={{ marginTop: "var(--lv-s-2)" }}>{action}</div>}
    </div>
  );
}
