import { colorFromString } from "@/lib/format";
import { fmtCentsTotal } from "@/lib/pricing";

interface Row {
  /** display label, e.g. "game" / "DeepSeek" */
  label: string;
  /** stable color seed (usually same as label) */
  colorKey?: string;
  cost_cents: number;
  share: number;
  /** optional right-side meta (e.g. "30 calls") */
  meta?: string;
}

interface Props {
  rows: Row[];
  emptyText?: string;
}

/** 共用 HBars：用于按 Provider / Purpose 分布等场景 */
export function BreakdownBars({ rows, emptyText = "无数据" }: Props) {
  if (rows.length === 0) {
    return (
      <div className="dim" style={{ padding: 24, textAlign: "center" }}>
        {emptyText}
      </div>
    );
  }
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      {rows.map((r) => (
        <div
          key={r.label}
          style={{
            display: "flex",
            alignItems: "center",
            gap: 10,
            fontSize: 12.5,
          }}
        >
          <div
            style={{
              width: 120,
              fontSize: 11.5,
              color: "var(--fg-secondary)",
              whiteSpace: "nowrap",
              overflow: "hidden",
              textOverflow: "ellipsis",
            }}
            title={r.label}
          >
            {r.label}
          </div>
          <div
            style={{
              flex: 1,
              background: "var(--bg-subtle)",
              borderRadius: 3,
              height: 8,
              overflow: "hidden",
            }}
          >
            <div
              style={{
                height: "100%",
                width: `${Math.max(r.share * 100, r.cost_cents > 0 ? 1.5 : 0)}%`,
                background: colorFromString(r.colorKey || r.label),
                borderRadius: 3,
                transition: "width 240ms cubic-bezier(.3,.7,.4,1)",
              }}
            />
          </div>
          {r.meta && (
            <span
              className="dim-2"
              style={{ fontSize: 10.5, minWidth: 56, textAlign: "right" }}
            >
              {r.meta}
            </span>
          )}
          <div
            className="tabular"
            style={{ minWidth: 70, textAlign: "right", fontWeight: 500 }}
          >
            {fmtCentsTotal(r.cost_cents)}
          </div>
        </div>
      ))}
    </div>
  );
}
