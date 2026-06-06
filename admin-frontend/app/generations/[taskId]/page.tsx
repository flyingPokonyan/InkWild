"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, FileText, Globe2, RefreshCw } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";

import { PageHeader } from "@/components/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Btn } from "@/components/ui/Btn";
import { Card } from "@/components/ui/Card";
import { apiFetch } from "@/lib/api";
import { fmtDateTime, phaseLabel } from "@/lib/format";
import type {
  GenerationTaskDetail,
  GenerationTaskEvent,
  GenerationTaskStatus,
} from "@/lib/types";

function statusTone(
  s: GenerationTaskStatus,
): "success" | "danger" | "info" | "warning" | "default" {
  if (s === "succeeded") return "success";
  if (s === "failed") return "danger";
  if (s === "running" || s === "pending") return "info";
  if (s === "cancelled") return "warning";
  return "default";
}

function statusLabel(s: GenerationTaskStatus): string {
  const m: Record<GenerationTaskStatus, string> = {
    pending: "排队中",
    running: "运行中",
    succeeded: "成功",
    failed: "失败",
    cancelled: "已取消",
  };
  return m[s] ?? s;
}

function eventTone(name: string): "success" | "danger" | "warning" | "info" | "default" {
  if (name === "result" || name === "done") return "success";
  if (name === "error") return "danger";
  if (name === "warning") return "warning";
  if (name === "progress") return "info";
  return "default";
}

export default function GenerationTaskDetailPage() {
  const params = useParams<{ taskId: string }>();
  const taskId = params.taskId;

  const query = useQuery({
    queryKey: ["generation-task", taskId],
    queryFn: () =>
      apiFetch<GenerationTaskDetail>(
        `/api/admin/generation-tasks/${taskId}`,
      ),
    refetchInterval: (q) => {
      const d = q.state.data;
      if (!d) return 5_000;
      if (d.status === "running" || d.status === "pending") return 3_000;
      return false;
    },
  });

  const t = query.data;

  return (
    <>
      <PageHeader
        title={
          t
            ? t.generated_name
              ? `《${t.generated_name}》· ${t.kind === "world" ? "世界" : "剧本"}`
              : `生成任务 · ${t.kind === "world" ? "世界" : "剧本"}`
            : "生成任务"
        }
        sub={t ? `任务 ID ${t.id}` : taskId}
        actions={
          <div className="cluster">
            <Link href="/generations">
              <Btn size="sm" icon={ArrowLeft}>
                返回列表
              </Btn>
            </Link>
            <Btn
              size="sm"
              icon={RefreshCw}
              onClick={() => query.refetch()}
              disabled={query.isFetching}
            >
              刷新
            </Btn>
          </div>
        }
      />

      {query.isPending ? (
        <Card>
          <div className="dim" style={{ padding: 24, textAlign: "center" }}>
            加载中…
          </div>
        </Card>
      ) : query.isError ? (
        <Card>
          <div
            style={{
              padding: 24,
              textAlign: "center",
              color: "var(--danger)",
            }}
          >
            加载失败：{(query.error as Error).message}
          </div>
        </Card>
      ) : !t ? (
        <Card>
          <div className="dim" style={{ padding: 24, textAlign: "center" }}>
            任务不存在
          </div>
        </Card>
      ) : (
        <>
          {/* Summary card */}
          <Card title="摘要">
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
                gap: 16,
                padding: 16,
              }}
            >
              <KV label="类型">
                <Badge tone={t.kind === "world" ? "accent" : "info"}>
                  {t.kind === "world" ? "世界" : "剧本"}
                </Badge>
              </KV>
              <KV label="状态">
                <Badge tone={statusTone(t.status)} dot>
                  {statusLabel(t.status)}
                </Badge>
              </KV>
              <KV label="当前阶段">
                {t.current_phase ? (
                  <span style={{ fontSize: 12 }}>
                    {phaseLabel(t.current_phase)}
                    {t.current_code && (
                      <span
                        className="mono dim-2"
                        style={{ marginLeft: 6, fontSize: 11 }}
                      >
                        / {t.current_code}
                      </span>
                    )}
                  </span>
                ) : (
                  <span className="dim-2">—</span>
                )}
              </KV>
              <KV label="事件总数">
                <span className="mono">{t.last_event_seq}</span>
              </KV>
              <KV label="IP">
                {t.ip_name ? `《${t.ip_name}》` : "—"}
              </KV>
              <KV label="Fidelity">
                {t.fidelity_mode ? (
                  <span className="mono">{t.fidelity_mode}</span>
                ) : (
                  <span className="dim-2">—</span>
                )}
              </KV>
              <KV label="创建时间">
                <span className="mono" style={{ fontSize: 11.5 }}>
                  {fmtDateTime(t.created_at)}
                </span>
              </KV>
              <KV label="开始时间">
                <span className="mono" style={{ fontSize: 11.5 }}>
                  {t.started_at ? fmtDateTime(t.started_at) : "—"}
                </span>
              </KV>
              <KV label="结束时间">
                <span className="mono" style={{ fontSize: 11.5 }}>
                  {t.finished_at ? fmtDateTime(t.finished_at) : "—"}
                </span>
              </KV>
              <KV label="草稿 ID">
                {t.draft_id ? (
                  <span className="mono" style={{ fontSize: 11.5 }}>
                    {t.draft_id}
                  </span>
                ) : (
                  <span className="dim-2">—</span>
                )}
              </KV>
            </div>

            {t.error_message && (
              <div
                style={{
                  margin: "0 16px 16px",
                  padding: 12,
                  background: "color-mix(in oklab, var(--danger) 12%, transparent)",
                  border: "1px solid color-mix(in oklab, var(--danger) 30%, transparent)",
                  borderRadius: 6,
                  color: "var(--danger)",
                  fontSize: 12.5,
                  lineHeight: 1.5,
                  whiteSpace: "pre-wrap",
                }}
              >
                {t.error_message}
              </div>
            )}
          </Card>

          {/* Request payload */}
          <Card title="原始请求">
            <pre
              className="payload"
              style={{ margin: 16, fontSize: 11.5, lineHeight: 1.5 }}
            >
              {JSON.stringify(t.request_payload || {}, null, 2)}
            </pre>
          </Card>

          {/* Stage 0: IP recognition events (from companion phase_a task) */}
          {t.companion_task && t.companion_task.phase_kind === "phase_a" && (
            <Card
              title={`Stage 0：IP 识别（${t.companion_task.events.length}）`}
              sub="生成开始前的前置探针：识别用户描述是否指向已知 IP，并由 admin 选择 fidelity 模式。"
              flush
            >
              <EventsTable events={t.companion_task.events} />
            </Card>
          )}

          {/* Events timeline */}
          <Card
            title={`事件流（${t.events.length}）`}
            sub={
              t.companion_task && t.companion_task.phase_kind === "phase_a"
                ? "Stage 0 之后的完整生成事件"
                : undefined
            }
            flush
          >
            <EventsTable events={t.events} />
          </Card>
        </>
      )}
    </>
  );
}

function EventsTable({ events }: { events: GenerationTaskEvent[] }) {
  return (
    <table className="tbl">
      <thead>
        <tr>
          <th style={{ width: 50 }}>seq</th>
          <th style={{ width: 80 }}>类型</th>
          <th>载荷</th>
        </tr>
      </thead>
      <tbody>
        {events.length === 0 ? (
          <tr>
            <td
              colSpan={3}
              className="dim"
              style={{ padding: 24, textAlign: "center" }}
            >
              暂无事件
            </td>
          </tr>
        ) : (
          events.map((ev) => (
            <tr key={ev.id}>
              <td className="mono dim" style={{ fontSize: 11 }}>
                {ev.seq}
              </td>
              <td>
                <Badge tone={eventTone(ev.event)}>{ev.event}</Badge>
              </td>
              <td>
                <EventPayload payload={ev.payload} />
              </td>
            </tr>
          ))
        )}
      </tbody>
    </table>
  );
}

function KV({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div
        className="dim-2"
        style={{
          fontSize: 10.5,
          textTransform: "uppercase",
          letterSpacing: "0.05em",
          marginBottom: 6,
        }}
      >
        {label}
      </div>
      <div>{children}</div>
    </div>
  );
}

function EventPayload({ payload }: { payload: Record<string, unknown> }) {
  const phase = typeof payload.phase === "string" ? payload.phase : null;
  const code = typeof payload.code === "string" ? payload.code : null;
  const message = typeof payload.message === "string" ? payload.message : null;
  const meta = (payload.meta && typeof payload.meta === "object"
    ? (payload.meta as Record<string, unknown>)
    : null);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      {(phase || code) && (
        <div style={{ fontSize: 11 }}>
          {phase && (
            <span>
              {phaseLabel(phase)}
              <span className="mono dim-2" style={{ marginLeft: 4, fontSize: 10.5 }}>
                {phase}
              </span>
            </span>
          )}
          {code && (
            <span className="mono dim-2" style={{ marginLeft: 6 }}>
              / {code}
            </span>
          )}
        </div>
      )}
      {message && (
        <div style={{ fontSize: 12, color: "var(--fg)" }}>{message}</div>
      )}
      {meta && Object.keys(meta).length > 0 && (
        <details>
          <summary
            className="dim-2"
            style={{ fontSize: 11, cursor: "pointer" }}
          >
            meta
          </summary>
          <pre
            className="payload"
            style={{ marginTop: 4, fontSize: 11, lineHeight: 1.5 }}
          >
            {JSON.stringify(meta, null, 2)}
          </pre>
        </details>
      )}
    </div>
  );
}
