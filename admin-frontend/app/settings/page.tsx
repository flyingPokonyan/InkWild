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

interface RuntimeConfig {
  llm_global_concurrency: number;
  llm_call_timeout_seconds: number;
  llm_call_max_retries: number;
  llm_call_retry_backoff_seconds: number;
  generation_task_active_limit_per_user: number;
  image_generation_concurrency: number;
  image_generation_global_concurrency: number;
  image_generation_timeout_seconds: number;
  image_generation_quality: "low" | "medium" | "high" | "auto";
  lore_pack_concurrency: number;
  character_batch_concurrency: number;
  events_data_concurrency: number;
  updated_at: string | null;
}

type RuntimeFieldKey = Exclude<keyof RuntimeConfig, "updated_at" | "image_generation_quality">;

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

const SIGNUP_QK = ["admin-signup-config"];
const RUNTIME_QK = ["admin-runtime-config"];

const RUNTIME_FIELDS: { key: RuntimeFieldKey; label: string; hint?: string; step?: string }[] = [
  { key: "llm_global_concurrency", label: "全局 LLM 并发", hint: "全站文本模型同时调用上限。" },
  { key: "generation_task_active_limit_per_user", label: "用户 active 任务上限", hint: "同一用户/管理员同时 pending/running 的生成任务数。" },
  { key: "image_generation_concurrency", label: "图片并发 / 任务", hint: "单个世界生成任务内头像/封面批量并发。" },
  { key: "image_generation_global_concurrency", label: "全站图片并发", hint: "0 表示不额外限流；>0 时所有生图入口共享。" },
  { key: "image_generation_timeout_seconds", label: "单张图超时（秒）", step: "1" },
  { key: "llm_call_timeout_seconds", label: "LLM 分片超时（秒）", hint: "首 token / 后续 chunk 超时窗口。", step: "1" },
  { key: "llm_call_max_retries", label: "LLM 重试次数" },
  { key: "llm_call_retry_backoff_seconds", label: "LLM 重试退避（秒）", step: "0.5" },
  { key: "lore_pack_concurrency", label: "设定包并发" },
  { key: "character_batch_concurrency", label: "角色批次并发" },
  { key: "events_data_concurrency", label: "事件批次并发" },
];

const QUALITY_OPTIONS = [
  { value: "low", label: "low" },
  { value: "medium", label: "medium" },
  { value: "high", label: "high" },
  { value: "auto", label: "auto" },
];

export default function SettingsPage() {
  const qc = useQueryClient();
  const [mode, setMode] = useState<string>("open");
  const [cap, setCap] = useState<string>("100");
  const [startNewBatch, setStartNewBatch] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [runtimeForm, setRuntimeForm] = useState<Record<string, string>>({});
  const [runtimeDirty, setRuntimeDirty] = useState(false);
  const [runtimeErr, setRuntimeErr] = useState<string | null>(null);

  const statusQuery = useQuery({
    queryKey: SIGNUP_QK,
    queryFn: () => apiFetch<SignupStatus>("/api/admin/system/signup"),
  });

  const runtimeQuery = useQuery({
    queryKey: RUNTIME_QK,
    queryFn: () => apiFetch<RuntimeConfig>("/api/admin/system/runtime"),
  });

  // 拉到配置后同步进表单（仅首次 / 刷新时）
  useEffect(() => {
    const s = statusQuery.data;
    if (s) {
      setMode(s.signup_mode);
      setCap(String(s.signup_cap || 100));
    }
  }, [statusQuery.data]);

  useEffect(() => {
    const d = runtimeQuery.data;
    if (d && !runtimeDirty) {
      setRuntimeForm({
        llm_global_concurrency: String(d.llm_global_concurrency),
        llm_call_timeout_seconds: String(d.llm_call_timeout_seconds),
        llm_call_max_retries: String(d.llm_call_max_retries),
        llm_call_retry_backoff_seconds: String(d.llm_call_retry_backoff_seconds),
        generation_task_active_limit_per_user: String(d.generation_task_active_limit_per_user),
        image_generation_concurrency: String(d.image_generation_concurrency),
        image_generation_global_concurrency: String(d.image_generation_global_concurrency),
        image_generation_timeout_seconds: String(d.image_generation_timeout_seconds),
        image_generation_quality: d.image_generation_quality,
        lore_pack_concurrency: String(d.lore_pack_concurrency),
        character_batch_concurrency: String(d.character_batch_concurrency),
        events_data_concurrency: String(d.events_data_concurrency),
      });
    }
  }, [runtimeQuery.data, runtimeDirty]);

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
      qc.invalidateQueries({ queryKey: SIGNUP_QK });
    },
    onError: (e: unknown) => setErr(e instanceof Error ? e.message : "保存失败"),
  });

  const saveRuntimeMutation = useMutation({
    mutationFn: () => {
      const payload: Record<string, number | string> = {
        image_generation_quality: runtimeForm.image_generation_quality || "high",
      };
      for (const f of RUNTIME_FIELDS) {
        const n = Number(runtimeForm[f.key]);
        if (Number.isFinite(n)) {
          payload[f.key] = n;
        }
      }
      return apiFetch<RuntimeConfig>("/api/admin/system/runtime", {
        method: "PUT",
        body: JSON.stringify(payload),
      });
    },
    onSuccess: (data) => {
      setRuntimeErr(null);
      setRuntimeDirty(false);
      qc.setQueryData(RUNTIME_QK, data);
    },
    onError: (e: unknown) => setRuntimeErr(e instanceof Error ? e.message : "保存失败"),
  });

  const onRuntimeChange = (key: string, value: string) => {
    setRuntimeForm((f) => ({ ...f, [key]: value }));
    setRuntimeDirty(true);
  };

  const s = statusQuery.data;
  const capNum = Number(cap);
  const capInvalid = mode === "capped" && (!Number.isFinite(capNum) || capNum < 0);
  const runtimeInvalid = RUNTIME_FIELDS.some((f) => {
    const n = Number(runtimeForm[f.key]);
    return !Number.isFinite(n) || n < 0;
  });

  return (
    <>
      <PageHeader
        title="系统设置"
        sub="注册放量 · 生成并发 / 超时 / 图片质量"
      />

      <Card title="注册放量">
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

      <Card
        title="运行时生成参数"
        sub={runtimeQuery.data?.updated_at ? `上次更新：${fmtDateTime(runtimeQuery.data.updated_at)}` : undefined}
        style={{ marginTop: 18 }}
      >
        {runtimeQuery.isPending ? (
          <div className="dim-2">加载中…</div>
        ) : runtimeQuery.isError ? (
          <div style={{ color: "var(--danger)" }}>
            加载失败：{(runtimeQuery.error as Error).message}
          </div>
        ) : (
          <div style={{ display: "grid", gap: 18 }}>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
                gap: 16,
                maxWidth: 900,
              }}
            >
              {RUNTIME_FIELDS.map((f) => (
                <div className="field" key={f.key}>
                  <label className="field-label">{f.label}</label>
                  <input
                    className="input"
                    type="number"
                    min={f.key === "image_generation_global_concurrency" ? 0 : 1}
                    step={f.step ?? "1"}
                    value={runtimeForm[f.key] ?? ""}
                    onChange={(e) => onRuntimeChange(f.key, e.target.value)}
                  />
                  {f.hint && <span className="field-hint">{f.hint}</span>}
                </div>
              ))}

              <div className="field">
                <label className="field-label">图片质量</label>
                <select
                  className="input"
                  value={runtimeForm.image_generation_quality ?? "high"}
                  onChange={(e) => onRuntimeChange("image_generation_quality", e.target.value)}
                >
                  {QUALITY_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>{o.label}</option>
                  ))}
                </select>
                <span className="field-hint">gpt-image-2 支持 low / medium / high / auto。</span>
              </div>
            </div>

            {runtimeErr && <div className="field-error">{runtimeErr}</div>}
            {saveRuntimeMutation.isSuccess && !runtimeDirty && (
              <div style={{ color: "var(--accent)", fontSize: 12 }}>已保存</div>
            )}
            <div>
              <Btn
                variant="primary"
                onClick={() => saveRuntimeMutation.mutate()}
                disabled={!runtimeDirty || saveRuntimeMutation.isPending || runtimeInvalid}
              >
                {saveRuntimeMutation.isPending ? "保存中…" : "保存运行时配置"}
              </Btn>
            </div>
          </div>
        )}
      </Card>
    </>
  );
}
