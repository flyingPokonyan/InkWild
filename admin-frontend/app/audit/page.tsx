"use client";

import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, Copy, MoreHorizontal } from "lucide-react";
import { Fragment, useMemo, useState } from "react";

import { PageHeader } from "@/components/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Btn } from "@/components/ui/Btn";
import { Card } from "@/components/ui/Card";
import { Segmented } from "@/components/ui/Segmented";
import { Select } from "@/components/ui/Select";
import { apiFetch } from "@/lib/api";
import { colorFromString, daysAgoIso, fmtDateTime, initials } from "@/lib/format";
import type { AuditLogItem, AuditLogListResponse } from "@/lib/types";

type Range = "today" | "7d" | "30d" | "all";

const PAGE_SIZE = 50;

function rangeToSince(r: Range): string | undefined {
  if (r === "all") return undefined;
  if (r === "today") return daysAgoIso(0);
  if (r === "7d") return daysAgoIso(7);
  return daysAgoIso(30);
}

function actionTone(
  action: string,
): "success" | "danger" | "info" | "default" {
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

function formatPayloadHtml(p: Record<string, unknown>): string {
  const json = JSON.stringify(p, null, 2);
  // Escape HTML, then highlight
  const esc = json
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
  return esc
    .replace(/&quot;([^&]+)&quot;:/g, '<span class="k">"$1"</span>:')
    .replace(/: &quot;([^&]*)&quot;/g, ': <span class="s">"$1"</span>')
    .replace(/: (-?\d+\.?\d*)/g, ': <span class="n">$1</span>')
    .replace(/: (true|false|null)/g, ': <span class="n">$1</span>');
}

export default function AuditPage() {
  const [range, setRange] = useState<Range>("7d");
  const [namespace, setNamespace] = useState<string>("all");
  const [page, setPage] = useState(1);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  const since = useMemo(() => rangeToSince(range), [range]);

  const namespacesQuery = useQuery({
    queryKey: ["audit-namespaces"],
    queryFn: () => apiFetch<string[]>("/api/admin/audit-logs/namespaces"),
    staleTime: 5 * 60_000,
  });

  const listQuery = useQuery({
    queryKey: ["audit-logs", page, namespace, since],
    queryFn: () => {
      const params = new URLSearchParams({
        page: String(page),
        limit: String(PAGE_SIZE),
      });
      if (namespace !== "all") params.set("action_prefix", namespace);
      if (since) params.set("since", since);
      return apiFetch<AuditLogListResponse>(
        `/api/admin/audit-logs?${params.toString()}`,
      );
    },
    placeholderData: (prev) => prev,
  });

  const data = listQuery.data;
  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;

  const namespaceOptions = [
    { value: "all", label: "全部操作类型" },
    ...(namespacesQuery.data ?? []).map((ns) => ({
      value: ns,
      label: ns,
    })),
  ];

  const onCopy = (item: AuditLogItem) => {
    navigator.clipboard
      .writeText(JSON.stringify(item.payload, null, 2))
      .catch(() => {});
  };

  return (
    <>
      <PageHeader
        title="审计日志"
        sub={
          data
            ? `记录所有 admin 操作 · 共 ${data.total} 条`
            : "记录所有 admin 操作"
        }
      />

      <Card flush>
        <div className="filter-bar">
          <Select
            value={namespace}
            onChange={(v) => {
              setNamespace(v);
              setPage(1);
            }}
            options={namespaceOptions}
            minWidth={170}
            menuWidth={200}
          />
          <Segmented<Range>
            value={range}
            options={[
              { value: "today", label: "今日" },
              { value: "7d", label: "近 7 天" },
              { value: "30d", label: "近 30 天" },
              { value: "all", label: "全部" },
            ]}
            onChange={(v) => {
              setRange(v);
              setPage(1);
            }}
          />
          <span
            className="dim-2"
            style={{ marginLeft: "auto", fontSize: 12 }}
          >
            {listQuery.isFetching ? "加载中…" : data ? `${data.items.length} 条` : ""}
          </span>
        </div>

        <table className="tbl">
          <thead>
            <tr>
              <th style={{ width: 28 }}></th>
              <th style={{ width: 170 }}>时间</th>
              <th style={{ width: 130 }}>操作人</th>
              <th style={{ width: 230 }}>操作</th>
              <th>目标 / 资源 ID</th>
              <th style={{ width: 50 }}></th>
            </tr>
          </thead>
          <tbody>
            {listQuery.isPending ? (
              <tr>
                <td colSpan={6} className="dim" style={{ padding: 24, textAlign: "center" }}>
                  加载中…
                </td>
              </tr>
            ) : listQuery.isError ? (
              <tr>
                <td colSpan={6} style={{ padding: 24, textAlign: "center", color: "var(--danger)" }}>
                  加载失败：{(listQuery.error as Error).message}
                </td>
              </tr>
            ) : !data || data.items.length === 0 ? (
              <tr>
                <td colSpan={6} className="dim" style={{ padding: 24, textAlign: "center" }}>
                  无数据
                </td>
              </tr>
            ) : (
              data.items.map((item) => {
                const isOpen = !!expanded[item.id];
                const adminName = item.admin?.nickname || item.admin_user_id || "system";
                return (
                  <Fragment key={item.id}>
                    <tr
                      style={{ cursor: "pointer" }}
                      onClick={() =>
                        setExpanded((s) => ({ ...s, [item.id]: !isOpen }))
                      }
                    >
                      <td>
                        <span
                          style={{
                            display: "inline-grid",
                            placeItems: "center",
                            width: 18,
                            height: 18,
                            color: "var(--fg-muted)",
                            transform: isOpen ? "rotate(90deg)" : "none",
                            transition: "transform 120ms",
                          }}
                        >
                          <ChevronRight size={10} />
                        </span>
                      </td>
                      <td className="mono dim" style={{ fontSize: 11.5 }}>
                        {fmtDateTime(item.created_at)}
                      </td>
                      <td>
                        {item.admin ? (
                          <span className="cluster">
                            <span
                              className="av-inline"
                              style={{
                                background: colorFromString(item.admin.id),
                              }}
                            >
                              {initials(item.admin.nickname || item.admin.id)}
                            </span>
                            <span>{adminName}</span>
                          </span>
                        ) : (
                          <Badge tone="default" dot>
                            system
                          </Badge>
                        )}
                      </td>
                      <td>
                        <Badge tone={actionTone(item.action)}>
                          <span className="mono" style={{ fontSize: 11 }}>
                            {item.action}
                          </span>
                        </Badge>
                      </td>
                      <td>
                        <span style={{ color: "var(--fg)", fontWeight: 500 }}>
                          {item.resource_type}
                        </span>
                        {item.resource_id && (
                          <span
                            className="mono dim"
                            style={{ marginLeft: 8, fontSize: 11 }}
                          >
                            {item.resource_id}
                          </span>
                        )}
                      </td>
                      <td className="num">
                        <Btn variant="ghost" size="xs" icon={MoreHorizontal} title="更多" />
                      </td>
                    </tr>
                    {isOpen && (
                      <tr>
                        <td
                          colSpan={6}
                          style={{
                            background: "var(--bg-subtle)",
                            padding: "12px 24px 16px 52px",
                          }}
                        >
                          <div style={{ display: "flex", gap: 24, fontSize: 12, flexWrap: "wrap" }}>
                            <div>
                              <div
                                className="dim-2"
                                style={{
                                  fontSize: 10.5,
                                  textTransform: "uppercase",
                                  letterSpacing: "0.05em",
                                  marginBottom: 4,
                                }}
                              >
                                记录 ID
                              </div>
                              <div className="mono" style={{ fontSize: 11.5 }}>
                                {item.id}
                              </div>
                            </div>
                            <div>
                              <div
                                className="dim-2"
                                style={{
                                  fontSize: 10.5,
                                  textTransform: "uppercase",
                                  letterSpacing: "0.05em",
                                  marginBottom: 4,
                                }}
                              >
                                来源 IP
                              </div>
                              <div className="mono" style={{ fontSize: 11.5 }}>
                                {item.ip_address || "—"}
                              </div>
                            </div>
                            <div style={{ minWidth: 200 }}>
                              <div
                                className="dim-2"
                                style={{
                                  fontSize: 10.5,
                                  textTransform: "uppercase",
                                  letterSpacing: "0.05em",
                                  marginBottom: 4,
                                }}
                              >
                                User-Agent
                              </div>
                              <div className="mono dim" style={{ fontSize: 11 }}>
                                {item.user_agent || "—"}
                              </div>
                            </div>
                          </div>
                          <div
                            className="dim-2"
                            style={{
                              fontSize: 10.5,
                              textTransform: "uppercase",
                              letterSpacing: "0.05em",
                              marginTop: 12,
                              marginBottom: 4,
                            }}
                          >
                            Payload
                          </div>
                          <pre
                            className="payload"
                            dangerouslySetInnerHTML={{
                              __html: formatPayloadHtml(item.payload),
                            }}
                          />
                          <div style={{ marginTop: 10, display: "flex", gap: 6 }}>
                            <Btn
                              size="xs"
                              icon={Copy}
                              onClick={(e) => {
                                e.stopPropagation();
                                onCopy(item);
                              }}
                            >
                              复制 JSON
                            </Btn>
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })
            )}
          </tbody>
        </table>

        <div className="card-ft">
          <div className="spread">
            <span>
              {data
                ? `第 ${(page - 1) * PAGE_SIZE + 1}-${Math.min(page * PAGE_SIZE, data.total)} 条，共 ${data.total} 条`
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
