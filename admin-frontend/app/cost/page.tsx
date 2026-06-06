"use client";

import { useQuery } from "@tanstack/react-query";
import { Coins, Play, Users, Zap } from "lucide-react";
import { useState } from "react";

import { PageHeader } from "@/components/PageHeader";
import { BreakdownBars } from "@/components/ui/BreakdownBars";
import { Btn } from "@/components/ui/Btn";
import { Card } from "@/components/ui/Card";
import { KpiCard } from "@/components/ui/KpiCard";
import { Segmented } from "@/components/ui/Segmented";
import { SpendBarChart } from "@/components/ui/SpendBarChart";
import { apiFetch } from "@/lib/api";
import { fillDailySeries } from "@/lib/chartData";
import { colorFromString } from "@/lib/format";
import { fmtCentsTotal } from "@/lib/pricing";
import type {
  CostByModel,
  CostByProvider,
  CostByPurpose,
  CostKpis,
  CostTrend,
  SessionCostSummary,
} from "@/lib/types";

const PURPOSE_LABELS: Record<string, string> = {
  game: "游戏对话",
  world_gen: "世界生成",
  script_gen: "剧本生成",
  compression: "上下文压缩",
  moderation: "内容审核",
  reflection: "记忆反思",
  image_gen: "图像生成",
  unknown: "未标记",
};

type Range = "7d" | "30d" | "90d";
const RANGE_DAYS: Record<Range, number> = { "7d": 7, "30d": 30, "90d": 90 };

export default function CostPage() {
  const [range, setRange] = useState<Range>("30d");
  const days = RANGE_DAYS[range];

  const kpisQuery = useQuery({
    queryKey: ["cost-kpis"],
    queryFn: () => apiFetch<CostKpis>("/api/admin/analytics/cost-kpis"),
  });

  const trendQuery = useQuery({
    queryKey: ["cost-trend", days],
    queryFn: () =>
      apiFetch<CostTrend>(`/api/admin/analytics/cost-trend?days=${days}`),
  });

  const providerQuery = useQuery({
    queryKey: ["cost-by-provider", days],
    queryFn: () =>
      apiFetch<CostByProvider>(
        `/api/admin/analytics/cost-by-provider?days=${days}`,
      ),
  });

  const modelQuery = useQuery({
    queryKey: ["cost-by-model", days],
    queryFn: () =>
      apiFetch<CostByModel>(`/api/admin/analytics/cost-by-model?days=${days}`),
  });

  const purposeQuery = useQuery({
    queryKey: ["cost-by-purpose", days],
    queryFn: () =>
      apiFetch<CostByPurpose>(
        `/api/admin/analytics/cost-by-purpose?days=${days}`,
      ),
  });

  const sessionSummaryQuery = useQuery({
    queryKey: ["session-summary", days],
    queryFn: () =>
      apiFetch<SessionCostSummary>(
        `/api/admin/analytics/sessions?days=${days}`,
      ),
  });

  const kpis = kpisQuery.data;
  const trend = trendQuery.data;
  const trendData = trend ? fillDailySeries(trend.series, days) : [];

  return (
    <>
      <PageHeader
        title="成本分析"
        sub="基于 token_usage 表的真实计费数据 · 单价从 provider_models 表读取"
        actions={
          <>
            <Segmented<Range>
              value={range}
              options={[
                { value: "7d", label: "7 天" },
                { value: "30d", label: "30 天" },
                { value: "90d", label: "90 天" },
              ]}
              onChange={setRange}
            />
          </>
        }
      />

      <div className="kpi-grid">
        <KpiCard
          icon={Coins}
          label="今日消耗"
          value={kpis ? fmtCentsTotal(kpis.today_cents) : "—"}
          delta={kpis?.today_delta_pct != null ? `${kpis.today_delta_pct >= 0 ? "+" : ""}${kpis.today_delta_pct}%` : null}
          deltaDir={
            kpis?.today_delta_pct == null
              ? undefined
              : kpis.today_delta_pct >= 0
                ? "up-bad"
                : "down-good"
          }
          deltaLabel="较昨日"
        />
        <KpiCard
          icon={Zap}
          label="近 7 天累计"
          value={kpis ? fmtCentsTotal(kpis.week_cents) : "—"}
          delta={kpis?.week_delta_pct != null ? `${kpis.week_delta_pct >= 0 ? "+" : ""}${kpis.week_delta_pct}%` : null}
          deltaDir={
            kpis?.week_delta_pct == null
              ? undefined
              : kpis.week_delta_pct >= 0
                ? "up-bad"
                : "down-good"
          }
          deltaLabel="环比上周"
        />
        <KpiCard
          icon={Play}
          label={`近 ${days} 天 session`}
          value={sessionSummaryQuery.data?.total_sessions ?? "—"}
          unit="个"
          deltaLabel={
            sessionSummaryQuery.data
              ? `均 ${fmtCentsTotal(sessionSummaryQuery.data.avg_cost_cents)} / 局`
              : undefined
          }
        />
        <KpiCard
          icon={Users}
          label="近 30 天月度消耗"
          value={kpis ? fmtCentsTotal(kpis.month_cents) : "—"}
          delta={kpis?.month_delta_pct != null ? `${kpis.month_delta_pct >= 0 ? "+" : ""}${kpis.month_delta_pct}%` : null}
          deltaDir={
            kpis?.month_delta_pct == null
              ? undefined
              : kpis.month_delta_pct >= 0
                ? "up-bad"
                : "down-good"
          }
          deltaLabel="环比上月"
        />
      </div>

      <Card
        title={`近 ${days} 天每日消耗`}
        sub="按 UTC 日切"
        style={{ marginBottom: "var(--gap)" }}
      >
        {trendQuery.isPending ? (
          <div className="dim" style={{ padding: 40, textAlign: "center", height: 260 }}>
            加载中…
          </div>
        ) : (
          <SpendBarChart data={trendData} height={260} />
        )}
        {trend && (
          <div
            style={{
              display: "flex",
              gap: 20,
              padding: "12px 4px 0",
              fontSize: 12,
              borderTop: "1px solid var(--divider)",
              marginTop: 8,
            }}
          >
            <Stat label={`${days} 天总和`} value={fmtCentsTotal(trend.total_cents)} />
            <Stat
              label="日均"
              value={fmtCentsTotal(
                trend.series.length > 0
                  ? trend.total_cents / trend.series.length
                  : 0,
              )}
            />
            <Stat
              label="峰值"
              value={fmtCentsTotal(
                trend.series.length > 0
                  ? Math.max(...trend.series.map((p) => p.cost_cents))
                  : 0,
              )}
            />
          </div>
        )}
      </Card>

      <div className="grid-2" style={{ marginBottom: "var(--gap)" }}>
        <Card title="按 Provider 分布" sub={`近 ${days} 天`}>
          {providerQuery.isPending ? (
            <div className="dim" style={{ padding: 24 }}>加载中…</div>
          ) : (
            <BreakdownBars
              rows={(providerQuery.data?.items ?? []).map((item) => ({
                label: item.provider,
                cost_cents: item.cost_cents,
                share: item.share,
                meta: `${item.sessions} sess`,
              }))}
            />
          )}
        </Card>
        <Card title="按用途分布" sub={`近 ${days} 天 · purpose 维度`}>
          {purposeQuery.isPending ? (
            <div className="dim" style={{ padding: 24 }}>加载中…</div>
          ) : (
            <BreakdownBars
              rows={(purposeQuery.data?.items ?? []).map((item) => ({
                label: PURPOSE_LABELS[item.purpose] || item.purpose,
                colorKey: item.purpose,
                cost_cents: item.cost_cents,
                share: item.share,
                meta: `${item.calls} 次`,
              }))}
            />
          )}
        </Card>
      </div>

      <div className="grid-cost" style={{ marginBottom: "var(--gap)" }}>
        <Card
          title="按 Model 拆分"
          sub={`近 ${days} 天 · token 消耗 + 调用次数 + 计费金额`}
          flush
        >
          <ModelBreakdownTable q={modelQuery} />
        </Card>
        <Card title="session 成本分布" sub={`近 ${days} 天`}>
          <SessionStats q={sessionSummaryQuery} />
        </Card>
      </div>
    </>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="dim-2" style={{ fontSize: 11 }}>{label}</div>
      <div className="tabular" style={{ fontWeight: 600, fontSize: 15, marginTop: 2 }}>
        {value}
      </div>
    </div>
  );
}

// ────────────── tables ──────────────
function ModelBreakdownTable({
  q,
}: {
  q: { data: CostByModel | undefined; isPending: boolean };
}) {
  if (q.isPending) return <div className="dim" style={{ padding: 24 }}>加载中…</div>;
  const data = q.data;
  if (!data || data.items.length === 0)
    return <div className="dim" style={{ padding: 24, textAlign: "center" }}>无数据</div>;

  return (
    <table className="tbl">
      <thead>
        <tr>
          <th style={{ width: 240 }}>Model</th>
          <th style={{ width: 140 }}>Provider</th>
          <th className="num">Input · M tok</th>
          <th className="num">Output · M tok</th>
          <th className="num">调用</th>
          <th className="num" style={{ width: 130 }}>消耗</th>
          <th className="num" style={{ width: 110 }}>占比</th>
        </tr>
      </thead>
      <tbody>
        {data.items.map((item) => (
          <tr key={`${item.provider}__${item.model_id}`}>
            <td>
              <div style={{ fontWeight: 500 }}>{item.display_name}</div>
              <div className="mono dim" style={{ fontSize: 11, marginTop: 2 }}>
                {item.model_id}
              </div>
            </td>
            <td className="dim">{item.provider}</td>
            <td className="num tabular">{(item.input_tokens / 1_000_000).toFixed(2)}</td>
            <td className="num tabular">{(item.output_tokens / 1_000_000).toFixed(2)}</td>
            <td className="num tabular">{item.calls.toLocaleString()}</td>
            <td className="num tabular" style={{ fontWeight: 600 }}>
              {fmtCentsTotal(item.cost_cents)}
            </td>
            <td className="num">
              <ShareBar share={item.share} color={colorFromString(item.provider)} />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function SessionStats({
  q,
}: {
  q: { data: SessionCostSummary | undefined; isPending: boolean };
}) {
  if (q.isPending) return <div className="dim" style={{ padding: 24 }}>加载中…</div>;
  const d = q.data;
  if (!d || d.total_sessions === 0)
    return <div className="dim" style={{ padding: 24, textAlign: "center" }}>无 session</div>;

  return (
    <div style={{ padding: 16, display: "flex", flexDirection: "column", gap: 14 }}>
      <Row label="总 session 数" value={`${d.total_sessions}`} />
      <Row label="累计成本" value={fmtCentsTotal(d.total_cost_cents)} highlight />
      <Row label="平均 / 局" value={fmtCentsTotal(d.avg_cost_cents, "cny", 3)} />
      <Row label="P50" value={fmtCentsTotal(d.p50_cost_cents, "cny", 3)} />
      <Row label="P90" value={fmtCentsTotal(d.p90_cost_cents, "cny", 3)} />
      <Row label="单局最高" value={fmtCentsTotal(d.max_cost_cents)} />
    </div>
  );
}

function Row({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", fontSize: 12.5 }}>
      <span className="dim">{label}</span>
      <span
        className="tabular"
        style={{ fontWeight: highlight ? 700 : 500, fontSize: highlight ? 14 : 13 }}
      >
        {value}
      </span>
    </div>
  );
}

function ShareBar({ share, color }: { share: number; color: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, justifyContent: "flex-end" }}>
      <div
        style={{
          width: 50,
          height: 4,
          background: "var(--bg-subtle)",
          borderRadius: 2,
          overflow: "hidden",
        }}
      >
        <div
          style={{
            height: "100%",
            width: `${share * 100}%`,
            background: color,
            borderRadius: 2,
          }}
        />
      </div>
      <span className="tabular dim" style={{ fontSize: 11.5, minWidth: 40 }}>
        {(share * 100).toFixed(1)}%
      </span>
    </div>
  );
}

