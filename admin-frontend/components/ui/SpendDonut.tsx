"use client";

import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";

import { colorFromString } from "@/lib/format";
import { fmtCentsTotal } from "@/lib/pricing";

interface Slice {
  label: string;
  /** stable color seed; defaults to label */
  colorKey?: string;
  cost_cents: number;
}

interface Props {
  data: Slice[];
  size?: number;
  emptyText?: string;
}

/** 紧凑 Donut + 右侧 legend，dashboard/cost 共用 */
export function SpendDonut({ data, size = 170, emptyText = "无数据" }: Props) {
  const total = data.reduce((s, d) => s + d.cost_cents, 0);

  if (total === 0) {
    return (
      <div
        className="dim"
        style={{
          height: size,
          display: "grid",
          placeItems: "center",
          textAlign: "center",
        }}
      >
        {emptyText}
      </div>
    );
  }

  const slices = data
    .filter((d) => d.cost_cents > 0)
    .map((d) => ({
      ...d,
      color: colorFromString(d.colorKey || d.label),
      pct: d.cost_cents / total,
    }));

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 20,
        flexWrap: "wrap",
      }}
    >
      <div
        style={{
          width: size,
          height: size,
          position: "relative",
          flexShrink: 0,
        }}
      >
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={slices}
              dataKey="cost_cents"
              nameKey="label"
              cx="50%"
              cy="50%"
              innerRadius={size / 2 - 22}
              outerRadius={size / 2 - 4}
              strokeWidth={0}
              paddingAngle={1}
            >
              {slices.map((s, i) => (
                <Cell key={i} fill={s.color} />
              ))}
            </Pie>
            <Tooltip
              contentStyle={{
                background: "var(--bg-elev)",
                border: "1px solid var(--border)",
                borderRadius: 6,
                fontSize: 12,
                padding: "6px 10px",
                boxShadow: "var(--shadow-md)",
              }}
              formatter={(v) => [fmtCentsTotal(Number(v ?? 0)), "消耗"]}
            />
          </PieChart>
        </ResponsiveContainer>
        <div
          style={{
            position: "absolute",
            inset: 0,
            display: "grid",
            placeItems: "center",
            pointerEvents: "none",
          }}
        >
          <div style={{ textAlign: "center" }}>
            <div className="dim" style={{ fontSize: 10.5 }}>
              合计
            </div>
            <div
              className="tabular"
              style={{ fontSize: 15, fontWeight: 600, marginTop: 2 }}
            >
              {fmtCentsTotal(total)}
            </div>
          </div>
        </div>
      </div>

      <div
        style={{
          flex: 1,
          minWidth: 140,
          display: "flex",
          flexDirection: "column",
          gap: 8,
        }}
      >
        {slices.map((s, i) => (
          <div
            key={i}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 10,
              fontSize: 12.5,
            }}
          >
            <span
              style={{
                width: 10,
                height: 10,
                borderRadius: 3,
                background: s.color,
                flexShrink: 0,
              }}
            />
            <span
              style={{
                flex: 1,
                color: "var(--fg-secondary)",
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
              title={s.label}
            >
              {s.label}
            </span>
            <span
              className="dim"
              style={{
                fontSize: 11,
                fontVariantNumeric: "tabular-nums",
              }}
            >
              {(s.pct * 100).toFixed(1)}%
            </span>
            <span
              className="tabular"
              style={{
                fontWeight: 500,
                minWidth: 60,
                textAlign: "right",
              }}
            >
              {fmtCentsTotal(s.cost_cents)}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
