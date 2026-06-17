"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { PageHeader } from "@/components/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Btn } from "@/components/ui/Btn";
import { Card } from "@/components/ui/Card";
import { Modal } from "@/components/ui/Modal";
import { Segmented } from "@/components/ui/Segmented";
import { Select } from "@/components/ui/Select";
import { apiFetch } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";

interface FeedbackItem {
  id: string;
  user_id: string | null;
  category: string;
  content: string;
  image_url: string | null;
  page_url: string | null;
  contact: string | null;
  user_agent: string | null;
  status: string;
  admin_note: string | null;
  reply: string | null;
  created_at: string;
  updated_at: string;
}

const STATUS_FILTERS = [
  { value: "", label: "全部" },
  { value: "new", label: "待处理" },
  { value: "triaged", label: "处理中" },
  { value: "resolved", label: "已解决" },
];

const STATUS_OPTIONS = [
  { value: "new", label: "待处理 new" },
  { value: "triaged", label: "处理中 triaged" },
  { value: "resolved", label: "已解决 resolved" },
];

const STATUS_TONE: Record<string, "default" | "warning" | "success"> = {
  new: "warning",
  triaged: "default",
  resolved: "success",
};

const STATUS_LABEL: Record<string, string> = { new: "待处理", triaged: "处理中", resolved: "已解决" };
const CATEGORY_LABEL: Record<string, string> = { bug: "问题反馈", suggestion: "优化建议" };

export default function FeedbackPage() {
  const qc = useQueryClient();
  const [filter, setFilter] = useState<string>("");
  const [detail, setDetail] = useState<FeedbackItem | null>(null);
  const [draftStatus, setDraftStatus] = useState("new");
  const [draftNote, setDraftNote] = useState("");
  const [draftReply, setDraftReply] = useState("");

  const QK = ["admin-feedback", filter];
  const listQuery = useQuery({
    queryKey: QK,
    queryFn: () =>
      apiFetch<FeedbackItem[]>(`/api/admin/feedback${filter ? `?status=${filter}` : ""}`),
  });

  const updateMutation = useMutation({
    mutationFn: (args: { id: string; status: string; admin_note: string; reply: string }) =>
      apiFetch(`/api/admin/feedback/${args.id}`, {
        method: "PATCH",
        body: JSON.stringify({ status: args.status, admin_note: args.admin_note, reply: args.reply }),
      }),
    onSuccess: () => {
      setDetail(null);
      qc.invalidateQueries({ queryKey: ["admin-feedback"] });
    },
  });

  function openDetail(it: FeedbackItem) {
    setDetail(it);
    setDraftStatus(it.status);
    setDraftNote(it.admin_note ?? "");
    setDraftReply(""); // 回复框每次清空：写新回复才发通知，不重复推历史回复
  }

  const items = listQuery.data ?? [];

  return (
    <>
      <PageHeader title="用户反馈" sub="bug / 优化建议 · 处理流转 new → triaged → resolved" />

      <div style={{ marginBottom: 14 }}>
        <Segmented value={filter} options={STATUS_FILTERS} onChange={(v) => setFilter(v)} />
      </div>

      <Card>
        <table className="tbl">
          <thead>
            <tr>
              <th style={{ width: 92 }}>类型</th>
              <th>内容</th>
              <th style={{ width: 90 }}>状态</th>
              <th style={{ width: 150 }}>提交时间</th>
              <th style={{ width: 90 }}>操作</th>
            </tr>
          </thead>
          <tbody>
            {listQuery.isLoading ? (
              <tr><td colSpan={5} className="dim" style={{ padding: 24, textAlign: "center" }}>加载中…</td></tr>
            ) : items.length === 0 ? (
              <tr><td colSpan={5} className="dim" style={{ padding: 24, textAlign: "center" }}>暂无反馈</td></tr>
            ) : (
              items.map((it) => (
                <tr key={it.id}>
                  <td>
                    <Badge tone={it.category === "bug" ? "danger" : "default"}>
                      {CATEGORY_LABEL[it.category] ?? it.category}
                    </Badge>
                  </td>
                  <td>
                    <div style={{ maxWidth: 460, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {it.content}
                    </div>
                    {it.page_url && <div className="dim" style={{ fontSize: 11 }}>{it.page_url}</div>}
                  </td>
                  <td><Badge tone={STATUS_TONE[it.status] ?? "default"}>{STATUS_LABEL[it.status] ?? it.status}</Badge></td>
                  <td className="dim" style={{ fontSize: 11.5 }}>{fmtDateTime(it.created_at)}</td>
                  <td><Btn variant="ghost" onClick={() => openDetail(it)}>查看</Btn></td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </Card>

      <Modal
        open={detail !== null}
        onClose={() => setDetail(null)}
        title="反馈详情"
        footer={
          detail && (
            <>
              <Btn variant="ghost" onClick={() => setDetail(null)}>取消</Btn>
              <Btn
                variant="primary"
                disabled={updateMutation.isPending}
                onClick={() => updateMutation.mutate({ id: detail.id, status: draftStatus, admin_note: draftNote, reply: draftReply })}
              >
                {updateMutation.isPending ? "保存中…" : "保存"}
              </Btn>
            </>
          )
        }
      >
        {detail && (
          <div>
            <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
              <Badge tone={detail.category === "bug" ? "danger" : "default"}>
                {CATEGORY_LABEL[detail.category] ?? detail.category}
              </Badge>
              <span className="dim" style={{ fontSize: 11.5, alignSelf: "center" }}>
                {fmtDateTime(detail.created_at)}
              </span>
            </div>

            <p style={{ whiteSpace: "pre-wrap", margin: "0 0 14px", lineHeight: 1.7 }}>{detail.content}</p>

            {detail.image_url && (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={detail.image_url}
                alt=""
                style={{ maxWidth: "100%", borderRadius: 8, marginBottom: 14, border: "1px solid var(--line, #2a2a32)" }}
              />
            )}

            <div className="dim" style={{ fontSize: 11.5, display: "grid", gap: 3, marginBottom: 16 }}>
              {detail.page_url && <div>页面：{detail.page_url}</div>}
              {detail.contact && <div>联系：{detail.contact}</div>}
              {detail.user_id && <div>用户：{detail.user_id}</div>}
              {detail.user_agent && <div style={{ wordBreak: "break-all" }}>UA：{detail.user_agent}</div>}
            </div>

            {detail.reply && (
              <div style={{ marginBottom: 14, padding: "10px 12px", borderRadius: 8, background: "rgba(255,255,255,0.03)", border: "1px solid var(--line, #2a2a32)" }}>
                <div className="dim" style={{ fontSize: 11, marginBottom: 4 }}>最近一次对用户的回复</div>
                <div style={{ fontSize: 13, whiteSpace: "pre-wrap" }}>{detail.reply}</div>
              </div>
            )}

            <div className="field">
              <label className="field-label">状态</label>
              <Select value={draftStatus} options={STATUS_OPTIONS} onChange={(v) => setDraftStatus(v)} />
            </div>
            <div className="field">
              <label className="field-label">回复用户（对外，会发通知）</label>
              <textarea
                className="input"
                rows={3}
                value={draftReply}
                placeholder="给用户的回复…改状态或写回复都会通知到 TA"
                onChange={(e) => setDraftReply(e.target.value)}
              />
            </div>
            <div className="field">
              <label className="field-label">内部备注（仅管理员可见）</label>
              <textarea
                className="input"
                rows={2}
                value={draftNote}
                placeholder="内部排查记录 / 跟进，不发给用户…"
                onChange={(e) => setDraftNote(e.target.value)}
              />
            </div>
          </div>
        )}
      </Modal>
    </>
  );
}
