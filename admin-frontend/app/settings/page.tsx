"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { PageHeader } from "@/components/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Btn } from "@/components/ui/Btn";
import { Card } from "@/components/ui/Card";
import { Segmented } from "@/components/ui/Segmented";
import { apiFetch } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";

interface SignupStatus {
  signup_mode: "open" | "capped" | "closed";
  signup_cap: number;
  signup_batch_start: string | null;
  batch_used: number;
  batch_remaining: number | null;
  updated_at: string | null;
}

const MODE_OPTIONS = [
  { value: "open", label: "不限注册" },
  { value: "capped", label: "批次放量" },
  { value: "closed", label: "暂停注册" },
];

const MODE_TONE: Record<string, "success" | "warning" | "danger"> = {
  open: "success",
  capped: "warning",
  closed: "danger",
};

const QK = ["admin-signup-config"];

export default function SettingsPage() {
  const qc = useQueryClient();
  const [mode, setMode] = useState<string>("open");
  const [cap, setCap] = useState<string>("100");
  const [startNewBatch, setStartNewBatch] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const statusQuery = useQuery({
    queryKey: QK,
    queryFn: () => apiFetch<SignupStatus>("/api/admin/system/signup"),
  });

  // 拉到配置后同步进表单（仅首次 / 刷新时）
  useEffect(() => {
    const s = statusQuery.data;
    if (s) {
      setMode(s.signup_mode);
      setCap(String(s.signup_cap || 100));
    }
  }, [statusQuery.data]);

  const saveMutation = useMutation({
    mutationFn: () =>
      apiFetch<SignupStatus>("/api/admin/system/signup", {
        method: "PUT",
        body: JSON.stringify({
          signup_mode: mode,
          signup_cap: mode === "capped" ? Number(cap) : undefined,
          start_new_batch: startNewBatch,
        }),
      }),
    onSuccess: () => {
      setErr(null);
      setStartNewBatch(false);
      qc.invalidateQueries({ queryKey: QK });
    },
    onError: (e: unknown) => setErr(e instanceof Error ? e.message : "保存失败"),
  });

  const s = statusQuery.data;
  const capNum = Number(cap);
  const capInvalid = mode === "capped" && (!Number.isFinite(capNum) || capNum < 0);

  return (
    <>
      <PageHeader
        title="系统设置"
        sub="注册放量控制 · 冷启动 / 邀请波次按批次放号，满额自动关闭"
      />

      <Card>
        <div style={{ display: "grid", gap: 22, maxWidth: 560 }}>
          {/* 当前状态 */}
          <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
            <span className="dim" style={{ fontSize: 12 }}>当前状态</span>
            {s ? (
              <>
                <Badge tone={MODE_TONE[s.signup_mode]}>
                  {MODE_OPTIONS.find((o) => o.value === s.signup_mode)?.label ?? s.signup_mode}
                </Badge>
                {s.signup_mode === "capped" && (
                  <span style={{ fontSize: 13 }}>
                    本批已注册 <b>{s.batch_used}</b> / {s.signup_cap}
                    {s.batch_remaining !== null && (
                      <span className="dim">（剩 {s.batch_remaining}）</span>
                    )}
                  </span>
                )}
                {s.signup_mode === "capped" && s.signup_batch_start && (
                  <span className="dim" style={{ fontSize: 11.5 }}>
                    起算 {fmtDateTime(s.signup_batch_start)}
                  </span>
                )}
              </>
            ) : (
              <span className="dim">加载中…</span>
            )}
          </div>

          {/* 模式 */}
          <div className="field">
            <label className="field-label">注册模式</label>
            <Segmented
              value={mode}
              options={MODE_OPTIONS}
              onChange={(v) => setMode(v)}
            />
            <span className="field-hint">
              {mode === "open" && "任何人都能注册，无名额限制。"}
              {mode === "capped" && "从本批起点开始，最多放 N 个新账号；满额后自动停止注册。"}
              {mode === "closed" && "完全关闭注册（邮箱 + OAuth 均拦截）。"}
            </span>
          </div>

          {/* 批次名额 */}
          {mode === "capped" && (
            <>
              <div className="field">
                <label className="field-label">本批名额 N</label>
                <input
                  className="input"
                  type="number"
                  min={0}
                  value={cap}
                  style={{ maxWidth: 160 }}
                  onChange={(e) => setCap(e.target.value)}
                />
                <span className="field-hint">
                  统计「批次起点」之后新建的账号数，达到 N 即拒绝。
                </span>
              </div>

              <label
                style={{ display: "flex", alignItems: "center", gap: 9, fontSize: 13, cursor: "pointer" }}
              >
                <input
                  type="checkbox"
                  checked={startNewBatch}
                  onChange={(e) => setStartNewBatch(e.target.checked)}
                />
                <span>
                  开新一批（把计数起点重置为现在 = 「从现在起再放 N 人」）
                  <span className="dim" style={{ display: "block", fontSize: 11.5 }}>
                    勾上保存即清零当前已用计数；不勾则沿用现有批次累计。
                  </span>
                </span>
              </label>
            </>
          )}

          {err && <div className="field-error">{err}</div>}

          <div>
            <Btn
              variant="primary"
              onClick={() => saveMutation.mutate()}
              disabled={saveMutation.isPending || capInvalid}
            >
              {saveMutation.isPending ? "保存中…" : "保存配置"}
            </Btn>
          </div>
        </div>
      </Card>
    </>
  );
}
