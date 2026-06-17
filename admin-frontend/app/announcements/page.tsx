"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { PageHeader } from "@/components/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Btn } from "@/components/ui/Btn";
import { Card } from "@/components/ui/Card";
import { Modal } from "@/components/ui/Modal";
import { Select } from "@/components/ui/Select";
import { apiFetch } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";

interface AnnouncementItem {
  id: string;
  title: string;
  body: string;
  image_url: string | null;
  level: string;
  status: string;
  published_at: string | null;
  expires_at: string | null;
  created_at: string;
}

const LEVEL_OPTIONS = [
  { value: "info", label: "普通 info" },
  { value: "warning", label: "提醒 warning" },
  { value: "critical", label: "重要 critical" },
];

const LEVEL_TONE: Record<string, "default" | "warning" | "danger"> = {
  info: "default",
  warning: "warning",
  critical: "danger",
};

const QK = ["admin-announcements"];

interface FormState {
  id: string | null;
  title: string;
  body: string;
  image_url: string;
  level: string;
  expires_at: string; // datetime-local 字符串，空 = 不过期
}

const EMPTY_FORM: FormState = { id: null, title: "", body: "", image_url: "", level: "info", expires_at: "" };

function readFileAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as string);
    reader.onerror = () => reject(new Error("读取图片失败"));
    reader.readAsDataURL(file);
  });
}

export default function AnnouncementsPage() {
  const qc = useQueryClient();
  const [form, setForm] = useState<FormState | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const listQuery = useQuery({
    queryKey: QK,
    queryFn: () => apiFetch<AnnouncementItem[]>("/api/admin/announcements"),
  });

  const invalidate = () => qc.invalidateQueries({ queryKey: QK });

  const saveMutation = useMutation({
    mutationFn: async (f: FormState) => {
      const body = {
        title: f.title.trim(),
        body: f.body.trim(),
        level: f.level,
        image_url: f.image_url, // "" = 清除配图
        expires_at: f.expires_at ? f.expires_at : null,
      };
      if (f.id) {
        return apiFetch(`/api/admin/announcements/${f.id}`, {
          method: "PATCH",
          body: JSON.stringify(body),
        });
      }
      return apiFetch("/api/admin/announcements", {
        method: "POST",
        body: JSON.stringify(body),
      });
    },
    onSuccess: () => {
      setForm(null);
      setErr(null);
      invalidate();
    },
    onError: (e: unknown) => setErr(e instanceof Error ? e.message : "保存失败"),
  });

  const uploadMutation = useMutation({
    mutationFn: async (file: File) => {
      const dataUrl = await readFileAsDataUrl(file);
      return apiFetch<{ image_url: string }>("/api/admin/announcements/upload-image", {
        method: "POST",
        body: JSON.stringify({ image: dataUrl }),
      });
    },
    onSuccess: (res) => setForm((f) => (f ? { ...f, image_url: res.image_url } : f)),
    onError: (e: unknown) => setErr(e instanceof Error ? e.message : "图片上传失败"),
  });

  const toggleMutation = useMutation({
    mutationFn: (item: AnnouncementItem) => {
      const action = item.status === "published" ? "unpublish" : "publish";
      return apiFetch(`/api/admin/announcements/${item.id}/${action}`, { method: "POST" });
    },
    onSuccess: invalidate,
  });

  const items = listQuery.data ?? [];

  return (
    <>
      <PageHeader
        title="系统公告"
        sub="向全体用户广播 · 草稿 → 发布 → 下架 · 可设过期时间自动消失"
        actions={
          <Btn variant="primary" onClick={() => { setErr(null); setForm({ ...EMPTY_FORM }); }}>
            新建公告
          </Btn>
        }
      />

      <Card>
        <table className="tbl">
          <thead>
            <tr>
              <th>标题</th>
              <th style={{ width: 96 }}>等级</th>
              <th style={{ width: 80 }}>状态</th>
              <th style={{ width: 160 }}>发布时间</th>
              <th style={{ width: 170 }}>操作</th>
            </tr>
          </thead>
          <tbody>
            {listQuery.isLoading ? (
              <tr><td colSpan={5} className="dim" style={{ padding: 24, textAlign: "center" }}>加载中…</td></tr>
            ) : items.length === 0 ? (
              <tr><td colSpan={5} className="dim" style={{ padding: 24, textAlign: "center" }}>暂无公告</td></tr>
            ) : (
              items.map((it) => (
                <tr key={it.id}>
                  <td>
                    <div style={{ fontWeight: 600 }}>{it.title}</div>
                    <div className="dim" style={{ fontSize: 11.5, maxWidth: 420, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {it.body}
                    </div>
                  </td>
                  <td><Badge tone={LEVEL_TONE[it.level] ?? "default"}>{it.level}</Badge></td>
                  <td>
                    <Badge tone={it.status === "published" ? "success" : "default"}>
                      {it.status === "published" ? "已发布" : "草稿"}
                    </Badge>
                  </td>
                  <td className="dim" style={{ fontSize: 11.5 }}>
                    {it.published_at ? fmtDateTime(it.published_at) : "—"}
                  </td>
                  <td>
                    <div style={{ display: "flex", gap: 6 }}>
                      <Btn
                        variant="ghost"
                        onClick={() => {
                          setErr(null);
                          setForm({
                            id: it.id, title: it.title, body: it.body, level: it.level,
                            image_url: it.image_url ?? "",
                            expires_at: it.expires_at ? it.expires_at.slice(0, 16) : "",
                          });
                        }}
                      >
                        编辑
                      </Btn>
                      <Btn
                        variant={it.status === "published" ? "danger" : "primary"}
                        onClick={() => toggleMutation.mutate(it)}
                        disabled={toggleMutation.isPending}
                      >
                        {it.status === "published" ? "下架" : "发布"}
                      </Btn>
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </Card>

      <Modal
        open={form !== null}
        onClose={() => setForm(null)}
        title={form?.id ? "编辑公告" : "新建公告"}
        sub="发布后进入用户端铃铛「系统公告」"
        footer={
          form && (
            <>
              <Btn variant="ghost" onClick={() => setForm(null)}>取消</Btn>
              <Btn
                variant="primary"
                onClick={() => saveMutation.mutate(form)}
                disabled={saveMutation.isPending || !form.title.trim() || !form.body.trim()}
              >
                {saveMutation.isPending ? "保存中…" : "保存"}
              </Btn>
            </>
          )
        }
      >
        {form && (
          <div>
            <div className="field">
              <label className="field-label field-label-req">标题</label>
              <input
                className="input"
                value={form.title}
                maxLength={200}
                placeholder="如：服务器维护通知"
                onChange={(e) => setForm({ ...form, title: e.target.value })}
              />
            </div>
            <div className="field">
              <label className="field-label field-label-req">正文</label>
              <textarea
                className="input"
                rows={5}
                value={form.body}
                placeholder="公告内容…支持 Markdown（**加粗**、[链接](url)、列表等）"
                onChange={(e) => setForm({ ...form, body: e.target.value })}
              />
              <span className="field-hint">支持 Markdown · 用户端详情弹窗按富文本渲染</span>
            </div>

            <div className="field">
              <label className="field-label">配图（可选）</label>
              {form.image_url ? (
                <div style={{ display: "flex", alignItems: "flex-start", gap: 12 }}>
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={form.image_url}
                    alt=""
                    style={{ width: 120, height: 72, objectFit: "cover", borderRadius: 8, border: "1px solid var(--line, #2a2a32)" }}
                  />
                  <Btn variant="ghost" onClick={() => setForm({ ...form, image_url: "" })}>
                    移除
                  </Btn>
                </div>
              ) : (
                <label className="btn btn-ghost" style={{ cursor: "pointer", display: "inline-flex", width: "fit-content" }}>
                  {uploadMutation.isPending ? "上传中…" : "上传图片"}
                  <input
                    type="file"
                    accept="image/png,image/jpeg,image/webp"
                    style={{ display: "none" }}
                    disabled={uploadMutation.isPending}
                    onChange={(e) => {
                      const file = e.target.files?.[0];
                      if (file) uploadMutation.mutate(file);
                      e.target.value = "";
                    }}
                  />
                </label>
              )}
              <span className="field-hint">PNG / JPEG / WebP，≤ 4MB</span>
            </div>
            <div className="field-row">
              <div className="field">
                <label className="field-label">等级</label>
                <Select
                  value={form.level}
                  options={LEVEL_OPTIONS}
                  onChange={(v) => setForm({ ...form, level: v })}
                />
              </div>
              <div className="field">
                <label className="field-label">过期时间（可选）</label>
                <input
                  className="input"
                  type="datetime-local"
                  value={form.expires_at}
                  onChange={(e) => setForm({ ...form, expires_at: e.target.value })}
                />
                <span className="field-hint">留空 = 长期有效</span>
              </div>
            </div>
            {err && <div className="field-error">{err}</div>}
          </div>
        )}
      </Modal>
    </>
  );
}
