"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { PageHeader } from "@/components/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Btn } from "@/components/ui/Btn";
import { Card } from "@/components/ui/Card";
import { Drawer } from "@/components/ui/Drawer";
import { Modal } from "@/components/ui/Modal";
import { Segmented } from "@/components/ui/Segmented";
import { apiFetch } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";
import type { PublishedContentItem } from "@/lib/types";

interface ReviewItem {
  kind: "world" | "script";
  draft_id: string;
  name: string;
  description: string;
  world_id: string | null;
  submitter: string;
  submitter_id: string;
  updated_at: string | null;
}

interface ReviewDetail {
  kind: string;
  draft_id: string;
  review_status: string;
  review_note: string | null;
  world_id: string | null;
  payload: Record<string, unknown>;
  quality_status?: string | null;
  quality?: {
    status: string;
    overall_score: number;
    blocking_flags: string[];
  } | null;
}

// 质量门放行状态：这两个之外，approve 会被质量门 400 挡下，需先豁免。
const QUALITY_PASSED = new Set(["passed", "waived"]);

function cleanFlag(f: string): string {
  return f
    .replace(/^quality_review:/, "")
    .replace(/^quality:/, "")
    .replace(/^moderation_flag:/, "")
    .replace(/_/g, " ");
}

const clampStyle: React.CSSProperties = {
  display: "-webkit-box",
  WebkitBoxOrient: "vertical",
  WebkitLineClamp: 1,
  overflow: "hidden",
};

type ContentView = "pending" | "published";

export default function ContentPage() {
  const [view, setView] = useState<ContentView>("pending");
  return (
    <>
      <PageHeader
        title="内容审核"
        sub="准入审核（草稿→发布）+ 已发布内容治理（强制下架）"
        actions={
          <Segmented<ContentView>
            value={view}
            options={[
              { value: "pending", label: "待审草稿" },
              { value: "published", label: "已发布内容" },
            ]}
            onChange={setView}
          />
        }
      />
      {view === "pending" ? <PendingReviews /> : <PublishedContent />}
    </>
  );
}

// ────────────── 待审草稿（准入：草稿 → 发布） ──────────────
function PendingReviews() {
  const qc = useQueryClient();
  const [selected, setSelected] = useState<ReviewItem | null>(null);
  const [note, setNote] = useState("");
  const [err, setErr] = useState<string | null>(null);

  const listQuery = useQuery({
    queryKey: ["admin-reviews"],
    queryFn: () => apiFetch<{ reviews: ReviewItem[] }>("/api/admin/reviews"),
  });

  const detailQuery = useQuery({
    queryKey: ["admin-review", selected?.kind, selected?.draft_id],
    queryFn: () =>
      apiFetch<ReviewDetail>(
        `/api/admin/reviews/${selected!.kind}/${selected!.draft_id}`,
      ),
    enabled: !!selected,
  });

  const close = () => {
    setSelected(null);
    setNote("");
    setErr(null);
  };

  const approve = useMutation({
    mutationFn: (it: ReviewItem) =>
      apiFetch(`/api/admin/reviews/${it.kind}/${it.draft_id}/approve`, {
        method: "POST",
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-reviews"] });
      close();
    },
    onError: (e) => setErr(e instanceof Error ? e.message : "通过失败"),
  });

  const reject = useMutation({
    mutationFn: (it: ReviewItem) =>
      apiFetch(`/api/admin/reviews/${it.kind}/${it.draft_id}/reject`, {
        method: "POST",
        body: JSON.stringify({ note: note.trim() || null }),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-reviews"] });
      close();
    },
    onError: (e) => setErr(e instanceof Error ? e.message : "驳回失败"),
  });

  // 质量门豁免 → 立即通过发布。备注即豁免原因（后端要求 ≥3 字），记入审计日志。
  const waiveAndPublish = useMutation({
    mutationFn: async (it: ReviewItem) => {
      await apiFetch(`/api/admin/reviews/world/${it.draft_id}/quality-waiver`, {
        method: "POST",
        body: JSON.stringify({ note: note.trim() }),
      });
      return apiFetch(`/api/admin/reviews/${it.kind}/${it.draft_id}/approve`, {
        method: "POST",
      });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-reviews"] });
      close();
    },
    onError: (e) => setErr(e instanceof Error ? e.message : "豁免并发布失败"),
  });

  const items = listQuery.data?.reviews ?? [];
  const busy = approve.isPending || reject.isPending || waiveAndPublish.isPending;
  const quality = detailQuery.data?.quality ?? null;
  const qStatus = detailQuery.data?.quality_status ?? null;
  // 世界且当前版本未 passed/waived → approve 会被质量门挡，露出豁免按钮。
  const needsWaiver =
    selected?.kind === "world" && !!qStatus && !QUALITY_PASSED.has(qStatus);

  return (
    <>
      <Card>
        <table className="tbl">
          <thead>
            <tr>
              <th style={{ width: 80 }}>类型</th>
              <th>名称</th>
              <th style={{ width: 150 }}>提交人</th>
              <th style={{ width: 160 }}>提交时间</th>
              <th style={{ width: 90 }} />
            </tr>
          </thead>
          <tbody>
            {listQuery.isPending ? (
              <tr>
                <td colSpan={5} className="dim" style={{ padding: 24, textAlign: "center" }}>
                  加载中…
                </td>
              </tr>
            ) : listQuery.isError ? (
              <tr>
                <td colSpan={5} style={{ padding: 24, textAlign: "center", color: "var(--danger)" }}>
                  加载失败：{(listQuery.error as Error).message}
                </td>
              </tr>
            ) : items.length === 0 ? (
              <tr>
                <td colSpan={5} className="dim" style={{ padding: 24, textAlign: "center" }}>
                  暂无待审内容
                </td>
              </tr>
            ) : (
              items.map((it) => (
                <tr key={`${it.kind}-${it.draft_id}`}>
                  <td>
                    <Badge tone={it.kind === "world" ? "info" : "accent"}>
                      {it.kind === "world" ? "世界" : "剧本"}
                    </Badge>
                  </td>
                  <td>
                    <div>{it.name}</div>
                    {it.description && (
                      <div className="dim-2" style={{ fontSize: 12, ...clampStyle }}>
                        {it.description}
                      </div>
                    )}
                  </td>
                  <td className="dim">{it.submitter || it.submitter_id.slice(0, 8)}</td>
                  <td className="dim" style={{ fontSize: 11.5 }}>
                    {it.updated_at ? fmtDateTime(it.updated_at) : "—"}
                  </td>
                  <td>
                    <Btn
                      variant="ghost"
                      onClick={() => {
                        setSelected(it);
                        setNote("");
                        setErr(null);
                      }}
                    >
                      审阅
                    </Btn>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </Card>

      <Drawer
        open={!!selected}
        onClose={close}
        title={selected?.name ?? "审阅"}
        sub={
          selected
            ? `${selected.kind === "world" ? "世界" : "剧本"} · 提交人 ${selected.submitter || "—"}`
            : undefined
        }
      >
        {detailQuery.isPending ? (
          <p className="dim">加载中…</p>
        ) : detailQuery.isError ? (
          <p style={{ color: "var(--danger)" }}>加载失败：{(detailQuery.error as Error).message}</p>
        ) : detailQuery.data ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            {typeof detailQuery.data.payload.description === "string" && (
              <p className="dim" style={{ lineHeight: 1.6 }}>
                {detailQuery.data.payload.description as string}
              </p>
            )}

            {selected?.kind === "world" && qStatus && (
              <div
                style={{
                  border: "1px solid var(--line)",
                  borderRadius: 8,
                  padding: "10px 12px",
                  display: "flex",
                  flexDirection: "column",
                  gap: 8,
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span className="dim-2" style={{ fontSize: 12 }}>
                    质量门
                  </span>
                  <Badge
                    tone={
                      QUALITY_PASSED.has(qStatus)
                        ? "success"
                        : qStatus === "failed"
                          ? "danger"
                          : "warning"
                    }
                  >
                    {qStatus}
                  </Badge>
                  {quality && (
                    <span className="dim" style={{ fontSize: 12 }}>
                      综合 {Math.round(quality.overall_score)}
                    </span>
                  )}
                </div>
                {quality && quality.blocking_flags.length > 0 && (
                  <ul
                    style={{
                      margin: 0,
                      paddingLeft: 18,
                      fontSize: 12,
                      color: "var(--fg-secondary)",
                      lineHeight: 1.5,
                    }}
                  >
                    {quality.blocking_flags.map((f, i) => (
                      <li key={i}>{cleanFlag(f)}</li>
                    ))}
                  </ul>
                )}
                {needsWaiver && (
                  <p className="dim-2" style={{ fontSize: 11.5, margin: 0 }}>
                    未通过质量门，直接「通过并发布」会被拦。确认内容没问题的话，填写下方备注作为豁免原因，再点「豁免并发布」。
                  </p>
                )}
              </div>
            )}

            {(() => {
              const warnings =
                (detailQuery.data.payload.quality_warnings as string[] | undefined) ?? [];
              const flags = warnings.filter(
                (w) => typeof w === "string" && w.startsWith("moderation_flag:"),
              );
              if (flags.length === 0) return null;
              return (
                <div
                  style={{
                    border: "1px solid var(--danger)",
                    borderRadius: 8,
                    padding: "10px 12px",
                    background: "rgba(220,60,60,0.06)",
                  }}
                >
                  <div style={{ fontWeight: 600, color: "var(--danger)", fontSize: 13 }}>
                    ⚠ AI 标记了 {flags.length} 处合规风险
                  </div>
                  <ul
                    style={{
                      margin: "4px 0 0",
                      paddingLeft: 18,
                      fontSize: 12.5,
                      color: "var(--fg-secondary)",
                    }}
                  >
                    {flags.map((f, i) => (
                      <li key={i}>{f.replace("moderation_flag:", "")}</li>
                    ))}
                  </ul>
                </div>
              );
            })()}

            <div>
              <div className="dim-2" style={{ fontSize: 12, marginBottom: 6 }}>
                完整内容
              </div>
              <pre
                style={{
                  maxHeight: 360,
                  overflow: "auto",
                  background: "var(--bg-subtle)",
                  border: "1px solid var(--line)",
                  borderRadius: 8,
                  padding: 12,
                  fontSize: 12,
                  lineHeight: 1.5,
                  whiteSpace: "pre-wrap",
                  wordBreak: "break-word",
                }}
              >
                {JSON.stringify(detailQuery.data.payload, null, 2)}
              </pre>
            </div>

            <div className="field">
              <label className="dim-2" style={{ fontSize: 12, display: "block", marginBottom: 6 }}>
                备注（驳回时回填给创作者；豁免质量门时作为豁免原因，需 ≥3 字）
              </label>
              <textarea
                className="input"
                rows={3}
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder={
                  needsWaiver
                    ? "例如：图已补齐，正典软旗为沙盒可接受取舍，予以放行"
                    : "例如：核心设定与题材不符，请调整后重新提交"
                }
              />
            </div>

            {err && <p style={{ color: "var(--danger)", fontSize: 12 }}>{err}</p>}

            <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", flexWrap: "wrap" }}>
              <Btn
                variant="danger"
                disabled={busy}
                onClick={() => selected && reject.mutate(selected)}
              >
                驳回
              </Btn>
              {needsWaiver ? (
                <Btn
                  variant="primary"
                  disabled={busy || note.trim().length < 3}
                  onClick={() => selected && waiveAndPublish.mutate(selected)}
                >
                  豁免并发布
                </Btn>
              ) : (
                <Btn
                  variant="primary"
                  disabled={busy}
                  onClick={() => selected && approve.mutate(selected)}
                >
                  通过并发布
                </Btn>
              )}
            </div>
          </div>
        ) : null}
      </Drawer>
    </>
  );
}

// ────────────── 已发布 / 已下架内容（事后治理：强制下架 + 恢复） ──────────────
type ContentStatus = "published" | "withdrawn";

function PublishedContent() {
  const qc = useQueryClient();
  const [kind, setKind] = useState<"worlds" | "scripts">("worlds");
  const [status, setStatus] = useState<ContentStatus>("published");
  const [target, setTarget] = useState<PublishedContentItem | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const listKey = ["admin-content", kind, status] as const;
  const listQuery = useQuery({
    queryKey: listKey,
    queryFn: () =>
      apiFetch<{ items: PublishedContentItem[] }>(
        `/api/admin/content/${kind}?status=${status}`,
      ),
  });

  const closeModal = () => {
    setTarget(null);
    setErr(null);
  };

  // published → 强制下架；withdrawn → 恢复。两套互斥，按当前 status 决定动作。
  const action = status === "published" ? "withdraw" : "restore";
  const mutate = useMutation({
    mutationFn: (it: PublishedContentItem) =>
      apiFetch(`/api/admin/content/${kind}/${it.id}/${action}`, { method: "POST" }),
    onSuccess: () => {
      // 失效两边列表：下架后该项从已发布移到已下架，恢复反之。
      qc.invalidateQueries({ queryKey: ["admin-content", kind] });
      closeModal();
    },
    onError: (e) =>
      setErr(e instanceof Error ? e.message : action === "withdraw" ? "下架失败" : "恢复失败"),
  });

  const items = listQuery.data?.items ?? [];
  const kindLabel = kind === "worlds" ? "世界" : "剧本";
  const statusLabel = status === "published" ? "已发布" : "已下架";

  return (
    <>
      <div style={{ marginBottom: 12, display: "flex", gap: 12, flexWrap: "wrap" }}>
        <Segmented<"worlds" | "scripts">
          value={kind}
          options={[
            { value: "worlds", label: "世界" },
            { value: "scripts", label: "剧本" },
          ]}
          onChange={setKind}
        />
        <Segmented<ContentStatus>
          value={status}
          options={[
            { value: "published", label: "已发布" },
            { value: "withdrawn", label: "已下架" },
          ]}
          onChange={(v) => {
            setStatus(v);
            closeModal();
          }}
        />
      </div>

      <Card flush>
        <table className="tbl">
          <thead>
            <tr>
              <th>名称</th>
              <th style={{ width: 160 }}>作者</th>
              <th style={{ width: 160 }}>创建时间</th>
              <th style={{ width: 110 }} />
            </tr>
          </thead>
          <tbody>
            {listQuery.isPending ? (
              <tr>
                <td colSpan={4} className="dim" style={{ padding: 24, textAlign: "center" }}>
                  加载中…
                </td>
              </tr>
            ) : listQuery.isError ? (
              <tr>
                <td colSpan={4} style={{ padding: 24, textAlign: "center", color: "var(--danger)" }}>
                  加载失败：{(listQuery.error as Error).message}
                </td>
              </tr>
            ) : items.length === 0 ? (
              <tr>
                <td colSpan={4} className="dim" style={{ padding: 24, textAlign: "center" }}>
                  暂无{statusLabel}{kindLabel}
                </td>
              </tr>
            ) : (
              items.map((it) => (
                <tr key={it.id}>
                  <td>{it.name}</td>
                  <td className="dim">
                    {it.author || (it.author_id ? it.author_id.slice(0, 8) : "—")}
                  </td>
                  <td className="dim" style={{ fontSize: 11.5 }}>
                    {it.created_at ? fmtDateTime(it.created_at) : "—"}
                  </td>
                  <td>
                    <Btn
                      variant={action === "withdraw" ? "danger" : "primary"}
                      onClick={() => {
                        setTarget(it);
                        setErr(null);
                      }}
                    >
                      {action === "withdraw" ? "强制下架" : "恢复"}
                    </Btn>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </Card>

      <Modal
        open={!!target}
        onClose={closeModal}
        title={action === "withdraw" ? "强制下架" : "恢复内容"}
        footer={
          <>
            <Btn variant="ghost" onClick={closeModal}>
              取消
            </Btn>
            <Btn
              variant={action === "withdraw" ? "danger" : "primary"}
              disabled={mutate.isPending}
              onClick={() => target && mutate.mutate(target)}
            >
              {action === "withdraw" ? "确认强制下架" : "确认恢复"}
            </Btn>
          </>
        }
      >
        {action === "withdraw" ? (
          <>
            <p style={{ marginBottom: 8 }}>确认强制下架《{target?.name}》？</p>
            <p className="dim" style={{ fontSize: 12.5, lineHeight: 1.6 }}>
              下架后内容对全网不可见，配下已发布的剧本会一并下架。作者无法自助恢复，但管理员可在「已下架」中恢复。操作会记入审计日志。
            </p>
          </>
        ) : (
          <>
            <p style={{ marginBottom: 8 }}>确认恢复《{target?.name}》？</p>
            <p className="dim" style={{ fontSize: 12.5, lineHeight: 1.6 }}>
              恢复后内容重新对全网可见（重新上架）。
              {kind === "scripts"
                ? "若所属世界仍处于下架状态，需先恢复世界。"
                : "配下剧本不会自动恢复，需在「剧本 · 已下架」中分别恢复。"}
              操作会记入审计日志。
            </p>
          </>
        )}
        {err && (
          <p style={{ color: "var(--danger)", fontSize: 12, marginTop: 8 }}>{err}</p>
        )}
      </Modal>
    </>
  );
}
