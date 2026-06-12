"use client";

import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowUpRight,
  ClipboardList,
  Coins,
  FileText,
  Play,
  RefreshCcw,
  UserPlus,
  Zap,
} from "lucide-react";
import Link from "next/link";

import { PageHeader } from "@/components/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { BreakdownBars } from "@/components/ui/BreakdownBars";
import { Btn } from "@/components/ui/Btn";
import { Card } from "@/components/ui/Card";
import { KpiCard } from "@/components/ui/KpiCard";
import { SpendBarChart } from "@/components/ui/SpendBarChart";
import { SpendDonut } from "@/components/ui/SpendDonut";
import { apiFetch } from "@/lib/api";
import { fillDailySeries } from "@/lib/chartData";
import { colorFromString, fmtDateTime, initials } from "@/lib/format";
import { fmtCentsTotal } from "@/lib/pricing";
import type {
  AuditLogListResponse,
  CostByProvider,
  CostByPurpose,
  CostTrend,
  DashboardKpis,
  ExpensiveSessions,
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

function actionTone(action: string): "success" | "danger" | "info" | "default" {
  const verb = action.split(".")[1] || "";
  if (verb.includes("create") || verb.includes("grant")) return "success";
  if (
    verb.includes("delete") ||
    verb.includes("withdraw") ||
    verb.includes("ban") ||
    verb.includes("fail")
  ) {
    return "danger";
  }
  if (verb.includes("update") || verb.includes("bind") || verb.includes("publish"))
    return "info";
  return "default";
}

function deltaPctLabel(d: number | null): {
  text: React.ReactNode;
  dir: "up" | "down" | undefined;
} {
  if (d == null) return { text: null, dir: undefined };
  return {
    text: `${d >= 0 ? "+" : ""}${d}%`,
    dir: d >= 0 ? "up" : "down",
  };
}

export default function DashboardPage() {
  const kpisQuery = useQuery({
    queryKey: ["dashboard-kpis"],
    queryFn: () => apiFetch<DashboardKpis>("/api/admin/dashboard/kpis"),
    refetchInterval: 60_000,
  });

  const trendQuery = useQuery({
    queryKey: ["dashboard-cost-trend"],
    queryFn: () =>
      apiFetch<CostTrend>("/api/admin/analytics/cost-trend?days=30"),
  });

  const providerQuery = useQuery({
    queryKey: ["dashboard-cost-by-provider"],
    queryFn: () =>
      apiFetch<CostByProvider>(
        "/api/admin/analytics/cost-by-provider?days=30",
      ),
  });

  const purposeQuery = useQuery({
    queryKey: ["dashboard-cost-by-purpose"],
    queryFn: () =>
      apiFetch<CostByPurpose>(
        "/api/admin/analytics/cost-by-purpose?days=30",
      ),
  });

  const expensiveQuery = useQuery({
    queryKey: ["dashboard-expensive-sessions"],
    queryFn: () =>
      apiFetch<ExpensiveSessions>(
        "/api/admin/analytics/expensive-sessions?days=7&limit=8",
      ),
  });

  const eventsQuery = useQuery({
    queryKey: ["dashboard-recent-events"],
    queryFn: () =>
      apiFetch<AuditLogListResponse>("/api/admin/audit-logs?page=1&limit=8"),
    refetchInterval: 30_000,
  });

  const kpis = kpisQuery.data;
  const trend = trendQuery.data;
  const provider = providerQuery.data;
  const purpose = purposeQuery.data;
  const expensive = expensiveQuery.data;
  const events = eventsQuery.data?.items || [];

  const todayDelta = deltaPctLabel(kpis?.spend.today_delta_pct ?? null);
  const weekDelta = deltaPctLabel(kpis?.spend.week_delta_pct ?? null);
  const trendData = trend ? fillDailySeries(trend.series, 30) : [];

  const refreshAll = () => {
    kpisQuery.refetch();
    trendQuery.refetch();
    providerQuery.refetch();
    purposeQuery.refetch();
    expensiveQuery.refetch();
    eventsQuery.refetch();
  };

  return (
    <>
      <PageHeader
        title="仪表盘"
        sub="过去 30 天的总体运行状况 · KPI 每 60 秒、事件每 30 秒自动刷新"
        actions={
          <>
            <Btn icon={RefreshCcw} size="sm" onClick={refreshAll}>
              刷新
            </Btn>
          </>
        }
      />

      {kpis && kpis.models_missing_pricing > 0 && (
        <div className="notice" style={{ marginBottom: "var(--gap)" }}>
          <span className="notice-ico">
            <AlertTriangle size={15} />
          </span>
          <div style={{ flex: 1 }}>
            <b>{kpis.models_missing_pricing} 个启用中的模型缺单价</b>
            <span style={{ marginLeft: 8, color: "oklch(0.45 0.13 75)" }}>
              · 缺单价会导致 token_usage 累计成本偏低
            </span>
          </div>
          <Link href="/models">
            <Btn variant="ghost" size="sm" icon={ArrowUpRight}>
              前往模型管理
            </Btn>
          </Link>
        </div>
      )}

      <div className="kpi-grid">
        <KpiCard
          icon={Coins}
          label="今日 LLM 消耗"
          value={kpis ? fmtCentsTotal(kpis.spend.today_cents) : "—"}
          delta={todayDelta.text}
          deltaDir={
            todayDelta.dir === "up"
              ? "up-bad"
              : todayDelta.dir === "down"
                ? "down-good"
                : undefined
          }
          deltaLabel="较昨日"
        />
        <KpiCard
          icon={Zap}
          label="近 7 天累计"
          value={kpis ? fmtCentsTotal(kpis.spend.week_cents) : "—"}
          delta={weekDelta.text}
          deltaDir={
            weekDelta.dir === "up"
              ? "up-bad"
              : weekDelta.dir === "down"
                ? "down-good"
                : undefined
          }
          deltaLabel="环比上周"
        />
        <KpiCard
          icon={Play}
          label="24 小时活跃 session"
          value={kpis?.active_sessions_24h ?? "—"}
          unit="个"
          deltaLabel="最近一次游玩 < 24h"
        />
        <KpiCard
          icon={AlertTriangle}
          label="24 小时失败任务"
          value={kpis?.failed_generations_24h ?? "—"}
          unit="个"
          deltaLabel={
            kpis?.failed_generations_24h ? "需检查创作工坊任务" : "无失败任务"
          }
        />
        <KpiCard
          icon={UserPlus}
          label="7 天新增用户"
          value={kpis?.new_users_7d ?? "—"}
          unit="人"
        />
        <KpiCard
          icon={FileText}
          label="7 天新发布内容"
          value={kpis ? `${kpis.new_worlds_7d}·${kpis.new_scripts_7d}` : "—"}
          deltaLabel="世界 · 剧本"
        />
        <KpiCard
          icon={ClipboardList}
          label="待审内容"
          value={kpis?.pending_reviews ?? "—"}
          unit="项"
          deltaLabel={kpis?.pending_reviews ? "需在内容审核处理" : "暂无待审"}
        />
      </div>

      <div className="grid-cost" style={{ marginBottom: "var(--gap)" }}>
        <Card
          title="近 30 天每日消耗"
          sub="按北京时间日切"
          actions={
            <Link href="/cost">
              <Btn variant="ghost" size="xs" icon={ArrowUpRight}>
                成本分析
              </Btn>
            </Link>
          }
        >
          {trendQuery.isPending ? (
            <div className="dim" style={{ padding: 24, textAlign: "center", height: 200 }}>
              加载中…
            </div>
          ) : (
            <SpendBarChart data={trendData} height={200} compact />
          )}
        </Card>

        <Card title="按 Provider 分布" sub="近 30 天">
          {providerQuery.isPending ? (
            <div className="dim" style={{ padding: 24 }}>加载中…</div>
          ) : (
            <SpendDonut
              data={(provider?.items ?? []).slice(0, 6).map((item) => ({
                label: item.provider,
                cost_cents: item.cost_cents,
              }))}
              size={170}
            />
          )}
        </Card>
      </div>

      <div className="grid-cost" style={{ marginBottom: "var(--gap)" }}>
        <Card
          title="近 7 天高成本 session"
          sub="按金额 top 8"
          actions={
            <Link href="/cost">
              <Btn variant="ghost" size="xs" icon={ArrowUpRight}>
                看全部
              </Btn>
            </Link>
          }
          flush
        >
          {expensiveQuery.isPending ? (
            <div className="dim" style={{ padding: 24 }}>加载中…</div>
          ) : !expensive || expensive.items.length === 0 ? (
            <div className="dim" style={{ padding: 24, textAlign: "center" }}>
              暂无消耗 &gt; 0 的 session
            </div>
          ) : (
            <table className="tbl">
              <thead>
                <tr>
                  <th>玩家</th>
                  <th>世界</th>
                  <th className="num">回合</th>
                  <th className="num" style={{ width: 100 }}>消耗</th>
                </tr>
              </thead>
              <tbody>
                {expensive.items.map((s) => (
                  <tr key={s.session_id}>
                    <td>
                      <span className="cluster">
                        <span
                          className="av-inline"
                          style={{ background: colorFromString(s.user_id) }}
                        >
                          {initials(s.user_nickname || s.user_id)}
                        </span>
                        <span>{s.user_nickname || s.user_id.slice(0, 8)}</span>
                      </span>
                    </td>
                    <td>{s.world_name || "—"}</td>
                    <td className="num tabular">{s.rounds_played}</td>
                    <td className="num tabular" style={{ fontWeight: 600 }}>
                      {fmtCentsTotal(s.cost_cents)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>

        <Card title="按用途分布" sub="近 30 天 · purpose 维度">
          {purposeQuery.isPending ? (
            <div className="dim" style={{ padding: 24 }}>加载中…</div>
          ) : (
            <BreakdownBars
              rows={(purpose?.items ?? []).map((item) => ({
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

      <Card
        title="最近事件"
        sub="审计日志最新 8 条"
        actions={
          <Link href="/audit">
            <Btn variant="ghost" size="xs" icon={ArrowUpRight}>
              全部
            </Btn>
          </Link>
        }
        flush
      >
        <table className="tbl">
          <thead>
            <tr>
              <th style={{ width: 170 }}>时间</th>
              <th style={{ width: 130 }}>操作人</th>
              <th style={{ width: 220 }}>操作</th>
              <th>目标 / 资源 ID</th>
            </tr>
          </thead>
          <tbody>
            {eventsQuery.isPending ? (
              <tr>
                <td colSpan={4} className="dim" style={{ padding: 24, textAlign: "center" }}>
                  加载中…
                </td>
              </tr>
            ) : events.length === 0 ? (
              <tr>
                <td colSpan={4} className="dim" style={{ padding: 24, textAlign: "center" }}>
                  暂无事件
                </td>
              </tr>
            ) : (
              events.map((e) => (
                <tr key={e.id}>
                  <td className="mono dim" style={{ fontSize: 11.5 }}>
                    {fmtDateTime(e.created_at)}
                  </td>
                  <td>
                    {e.admin ? (
                      <span className="cluster">
                        <span
                          className="av-inline"
                          style={{ background: colorFromString(e.admin.id) }}
                        >
                          {initials(e.admin.nickname || e.admin.id)}
                        </span>
                        <span>{e.admin.nickname || e.admin_user_id}</span>
                      </span>
                    ) : (
                      <Badge tone="default" dot>system</Badge>
                    )}
                  </td>
                  <td>
                    <Badge tone={actionTone(e.action)}>
                      <span className="mono" style={{ fontSize: 11 }}>
                        {e.action}
                      </span>
                    </Badge>
                  </td>
                  <td>
                    <span style={{ color: "var(--fg)", fontWeight: 500 }}>
                      {e.resource_type}
                    </span>
                    {e.resource_id && (
                      <span className="mono dim" style={{ marginLeft: 8, fontSize: 11 }}>
                        {e.resource_id}
                      </span>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </Card>
    </>
  );
}
