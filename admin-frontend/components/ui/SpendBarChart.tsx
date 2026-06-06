"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { fmtCentsTotal } from "@/lib/pricing";

interface Props {
  data: { label: string; value: number; date?: string }[];
  height?: number;
  /** 当为 true，X 轴只显示首尾，节省空间（dashboard 用） */
  compact?: boolean;
}

/**
 * 统一的"日消耗"柱状图：累计 0 元的日子也画出空 slot；
 * Y 轴自动格式化为 ¥；柱体带轻微渐变；空数据自动隐藏。
 */
export function SpendBarChart({ data, height = 220, compact = false }: Props) {
  const hasAnyValue = data.some((p) => p.value > 0);
  if (!hasAnyValue) {
    return (
      <div
        className="dim"
        style={{
          height,
          display: "grid",
          placeItems: "center",
          textAlign: "center",
        }}
      >
        该时段无消耗记录
        <div className="dim-2" style={{ fontSize: 11, marginTop: 4 }}>
          token_usage 表 cost_cents 全为 0
        </div>
      </div>
    );
  }

  return (
    <div style={{ width: "100%", height }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          data={data}
          margin={{ top: 12, right: 12, left: 4, bottom: 4 }}
          barCategoryGap={compact ? "12%" : "20%"}
        >
          <defs>
            <linearGradient id="spendBarGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--accent)" stopOpacity={0.95} />
              <stop offset="100%" stopColor="var(--accent)" stopOpacity={0.55} />
            </linearGradient>
          </defs>
          <CartesianGrid
            stroke="oklch(0.92 0.004 250)"
            strokeDasharray="3 3"
            vertical={false}
          />
          <XAxis
            dataKey="label"
            tick={{ fontSize: 10, fill: "var(--fg-tertiary)" }}
            axisLine={false}
            tickLine={false}
            interval={compact ? "preserveStartEnd" : undefined}
            minTickGap={compact ? 60 : 16}
          />
          <YAxis
            tick={{ fontSize: 10, fill: "var(--fg-tertiary)" }}
            axisLine={false}
            tickLine={false}
            tickFormatter={(v: number) =>
              v === 0 ? "0" : fmtCentsTotal(v, "cny", v < 100 ? 2 : 0)
            }
            width={48}
            allowDecimals={false}
          />
          <Tooltip
            cursor={{ fill: "color-mix(in oklch, var(--accent) 10%, transparent)" }}
            contentStyle={{
              background: "var(--bg-elev)",
              border: "1px solid var(--border)",
              borderRadius: 6,
              fontSize: 12,
              padding: "6px 10px",
              boxShadow: "var(--shadow-md)",
            }}
            labelStyle={{ color: "var(--fg-tertiary)", fontSize: 11, marginBottom: 4 }}
            itemStyle={{ color: "var(--fg)", padding: 0 }}
            formatter={(v) => [fmtCentsTotal(Number(v ?? 0)), "消耗"]}
          />
          <Bar
            dataKey="value"
            fill="url(#spendBarGradient)"
            radius={[3, 3, 0, 0]}
            maxBarSize={32}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
