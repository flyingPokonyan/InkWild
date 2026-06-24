"use client";

import { useQuery } from "@tanstack/react-query";
import {
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  FileText,
  Globe2,
} from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";

import { PageHeader } from "@/components/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Btn } from "@/components/ui/Btn";
import { Card } from "@/components/ui/Card";
import { Segmented } from "@/components/ui/Segmented";
import { Toggle } from "@/components/ui/Toggle";
import { apiFetch } from "@/lib/api";
import { fmtDateTime, phaseLabel } from "@/lib/format";
import type {
  GenerationTaskKind,
  GenerationTaskListResponse,
  GenerationTaskStatus,
} from "@/lib/types";

type KindFilter = "all" | GenerationTaskKind;
type StatusFilter = "all" | GenerationTaskStatus;

const PAGE_SIZE = 30;

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

// 质量分配色：≥85 绿 / ≥70 黄 / <70 红。仅硬指标加权（软分不进总分）。
function scoreColor(score: number): string {
  if (score >= 85) return "var(--success, #16A34A)";
  if (score >= 70) return "var(--warning, #D97706)";
  return "var(--danger, #DC2626)";
}

function durationLabel(startedAt: string | null, finishedAt: string | null): string {
  if (!startedAt) return "—";
  const start = new Date(_normalizeIso(startedAt)).getTime();
  const end = finishedAt ? new Date(_normalizeIso(finishedAt)).getTime() : Date.now();
  const sec = Math.max(0, Math.round((end - start) / 1000));
  if (sec < 60) return `${sec}s`;
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m}m ${s}s`;
}

// Backend writes naive UTC; treat suffix-less ISO as UTC.
function _normalizeIso(iso: string): string {
  return /(Z|[+-]\d{2}:?\d{2})$/.test(iso) ? iso : `${iso}Z`;
}

export default function GenerationsPage() {
  const [kind, setKind] = useState<KindFilter>("all");
  const [status, setStatus] = useState<StatusFilter>("all");
  const [includeIpRecognition, setIncludeIpRecognition] = useState(false);
  const [page, setPage] = useState(1);

  const params = useMemo(() => {
    const p = new URLSearchParams({
      page: String(page),
      limit: String(PAGE_SIZE),
    });
    if (kind !== "all") p.set("kind", kind);
    if (status !== "all") p.set("status", status);
    if (includeIpRecognition) p.set("include_ip_recognition", "true");
    return p.toString();
  }, [kind, status, includeIpRecognition, page]);

  const query = useQuery({
    queryKey: ["generation-tasks", params],
    queryFn: () =>
      apiFetch<GenerationTaskListResponse>(
        `/api/admin/generation-tasks?${params}`,
      ),
    placeholderData: (prev) => prev,
    refetchInterval: 10_000,
  });

  const data = query.data;
  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;

  return (
    <>
      <PageHeader
        title="生成记录"
        sub={
          data
            ? `世界 / 剧本 AI 生成任务 · 共 ${data.total} 条`
            : "世界 / 剧本 AI 生成任务"
        }
      />

      <Card flush>
        <div className="filter-bar">
          <Segmented<KindFilter>
            value={kind}
            options={[
              { value: "all", label: "全部" },
              { value: "world", label: "世界" },
              { value: "script", label: "剧本" },
            ]}
            onChange={(v) => {
              setKind(v);
              setPage(1);
            }}
          />
          <Segmented<StatusFilter>
            value={status}
            options={[
              { value: "all", label: "全部状态" },
              { value: "running", label: "运行中" },
              { value: "succeeded", label: "成功" },
              { value: "failed", label: "失败" },
            ]}
            onChange={(v) => {
              setStatus(v);
              setPage(1);
            }}
          />
          <label
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 8,
              fontSize: 12,
              color: "var(--fg-muted)",
              cursor: "pointer",
            }}
            title="phase_a 仅做 IP 识别，几秒就完成；默认隐藏。"
          >
            <Toggle
              value={includeIpRecognition}
              onChange={(v) => {
                setIncludeIpRecognition(v);
                setPage(1);
              }}
              ariaLabel="显示 IP 识别阶段"
            />
            显示 IP 识别阶段
          </label>
          <span
            className="dim-2"
            style={{ marginLeft: "auto", fontSize: 12 }}
          >
            {query.isFetching ? "加载中…" : data ? `${data.items.length} 条` : ""}
          </span>
        </div>

        <table className="tbl">
          <thead>
            <tr>
              <th style={{ width: 110 }}>类型</th>
              <th style={{ width: 90 }}>状态</th>
              <th style={{ width: 170 }}>创建时间</th>
              <th style={{ width: 80 }}>耗时</th>
              <th style={{ width: 76 }}>质量</th>
              <th style={{ width: 160 }}>IP</th>
              <th>提示词 / 当前阶段</th>
              <th style={{ width: 60 }}></th>
            </tr>
          </thead>
          <tbody>
            {query.isPending ? (
              <tr>
                <td
                  colSpan={8}
                  className="dim"
                  style={{ padding: 24, textAlign: "center" }}
                >
                  加载中…
                </td>
              </tr>
            ) : query.isError ? (
              <tr>
                <td
                  colSpan={8}
                  style={{
                    padding: 24,
                    textAlign: "center",
                    color: "var(--danger)",
                  }}
                >
                  加载失败：{(query.error as Error).message}
                </td>
              </tr>
            ) : !data || data.items.length === 0 ? (
              <tr>
                <td
                  colSpan={8}
                  className="dim"
                  style={{ padding: 24, textAlign: "center" }}
                >
                  无生成记录
                </td>
              </tr>
            ) : (
              data.items.map((t) => {
                const isWorld = t.kind === "world";
                const Icon = isWorld ? Globe2 : FileText;
                const kindColor = isWorld
                  ? "var(--accent, #7B5CFF)"
                  : "var(--info, #0EA5E9)";
                return (
                <tr key={t.id}>
                  <td>
                    <span
                      style={{
                        display: "inline-flex",
                        alignItems: "center",
                        gap: 6,
                        padding: "3px 8px",
                        borderRadius: 4,
                        background: `color-mix(in oklab, ${kindColor} 14%, transparent)`,
                        color: kindColor,
                        fontSize: 12,
                        fontWeight: 600,
                        lineHeight: 1.5,
                      }}
                    >
                      <Icon size={14} />
                      {isWorld ? "世界" : "剧本"}
                    </span>
                  </td>
                  <td>
                    <Badge tone={statusTone(t.status)} dot>
                      {statusLabel(t.status)}
                    </Badge>
                  </td>
                  <td className="mono dim" style={{ fontSize: 11.5 }}>
                    {fmtDateTime(t.created_at)}
                  </td>
                  <td className="mono dim" style={{ fontSize: 11.5 }}>
                    {durationLabel(t.started_at, t.finished_at)}
                  </td>
                  <td>
                    {t.quality_score != null ? (
                      <span
                        title={
                          t.quality_must_have
                            ? `must_have ${t.quality_must_have}${t.quality_backfill ? ` · backfill 补了 ${t.quality_backfill}` : ""}`
                            : t.quality_backfill
                              ? `backfill 补了 ${t.quality_backfill}`
                              : undefined
                        }
                        style={{
                          display: "inline-flex",
                          alignItems: "center",
                          gap: 3,
                          padding: "2px 7px",
                          borderRadius: 4,
                          fontSize: 12,
                          fontWeight: 600,
                          fontVariantNumeric: "tabular-nums",
                          background: `color-mix(in oklab, ${scoreColor(t.quality_score)} 14%, transparent)`,
                          color: scoreColor(t.quality_score),
                        }}
                      >
                        {Math.round(t.quality_score)}
                        {t.quality_backfill ? <span title="靠 backfill 补救">⚠</span> : null}
                      </span>
                    ) : (
                      <span className="dim-2">—</span>
                    )}
                  </td>
                  <td>
                    {t.ip_name ? (
                      <span style={{ fontSize: 12 }}>
                        《{t.ip_name}》
                        {t.fidelity_mode && (
                          <span
                            className="dim-2"
                            style={{ marginLeft: 6, fontSize: 11 }}
                          >
                            {t.fidelity_mode}
                          </span>
                        )}
                      </span>
                    ) : (
                      <span className="dim-2">—</span>
                    )}
                  </td>
                  <td style={{ maxWidth: 0, minWidth: 0 }}>
                    {t.error_message ? (
                      <div
                        style={{
                          color: "var(--danger)",
                          fontSize: 12,
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                        }}
                        title={t.error_message}
                      >
                        {t.error_message}
                      </div>
                    ) : (
                      <div
                        style={{
                          display: "flex",
                          flexDirection: "column",
                          gap: 2,
                          minWidth: 0,
                        }}
                      >
                        <div
                          style={{
                            fontSize: 13,
                            fontWeight: 500,
                            color: "var(--fg)",
                            overflow: "hidden",
                            textOverflow: "ellipsis",
                            whiteSpace: "nowrap",
                          }}
                          title={
                            t.generated_name ||
                            t.prompt_preview ||
                            ""
                          }
                        >
                          {t.generated_name ? (
                            <>《{t.generated_name}》</>
                          ) : (
                            <span className="dim-2" style={{ fontWeight: 400 }}>
                              {t.prompt_preview || "（待命名）"}
                            </span>
                          )}
                        </div>
                        <div
                          className="dim-2"
                          style={{
                            fontSize: 11,
                            overflow: "hidden",
                            textOverflow: "ellipsis",
                            whiteSpace: "nowrap",
                          }}
                          title={[
                            t.prompt_preview,
                            t.current_phase ? phaseLabel(t.current_phase) : "",
                            t.current_message,
                          ]
                            .filter(Boolean)
                            .join(" · ")}
                        >
                          {t.generated_name && t.prompt_preview && (
                            <span>{t.prompt_preview}</span>
                          )}
                          {(t.current_phase || t.current_message) && (
                            <>
                              {t.generated_name && t.prompt_preview ? " · " : ""}
                              {t.current_phase && (
                                <span>{phaseLabel(t.current_phase)}</span>
                              )}
                              {t.current_phase && t.current_message ? " · " : ""}
                              {t.current_message}
                            </>
                          )}
                        </div>
                      </div>
                    )}
                  </td>
                  <td className="num">
                    <Link href={`/generations/${t.id}`}>
                      <Btn
                        variant="ghost"
                        size="xs"
                        icon={ExternalLink}
                        title="详情"
                      />
                    </Link>
                  </td>
                </tr>
                );
              })
            )}
          </tbody>
        </table>

        <div className="card-ft">
          <div className="spread">
            <span>
              {data
                ? `第 ${(page - 1) * PAGE_SIZE + 1}-${Math.min(
                    page * PAGE_SIZE,
                    data.total,
                  )} 条，共 ${data.total} 条`
                : "—"}
            </span>
            <div className="cluster">
              <Btn
                size="xs"
                icon={ChevronLeft}
                disabled={page <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
              />
              <span className="mono dim">
                {page} / {totalPages}
              </span>
              <Btn
                size="xs"
                icon={ChevronRight}
                disabled={page >= totalPages}
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              />
            </div>
          </div>
        </div>
      </Card>
    </>
  );
}
