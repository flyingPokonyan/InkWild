"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Edit, Play, Plus, Trash2 } from "lucide-react";
import { useState } from "react";

import { PageHeader } from "@/components/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Btn } from "@/components/ui/Btn";
import { Card } from "@/components/ui/Card";
import { CurlHover } from "@/components/ui/CurlHover";
import { Modal } from "@/components/ui/Modal";
import { ProviderChip } from "@/components/ui/ProviderChip";
import { Segmented } from "@/components/ui/Segmented";
import { Select } from "@/components/ui/Select";
import { Tabs } from "@/components/ui/Tabs";
import { apiFetch, apiUrl } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";
import { fmtPricePerImage, fmtPricePerM } from "@/lib/pricing";
import type {
  ModelDashboardResponse,
  ModelKind,
  ModelProviderSummary,
  ModelProviderType,
  ProviderModelSummary,
} from "@/lib/types";

type TabKey = "providers" | "models" | "slots";

type ProbeState =
  | { state: "running" }
  | { state: "ok"; latency_ms: number; note?: string }
  | { state: "fail"; error: string }
  | undefined;

/** Compose a copy-pasteable curl command from a relative path + method + body. */
function buildCurl(
  path: string,
  opts?: { method?: string; body?: Record<string, unknown> },
): string {
  const method = (opts?.method ?? "POST").toUpperCase();
  const url = apiUrl(path);
  const lines: string[] = [`curl -X ${method} '${url}' \\`];
  lines.push(`  -H 'Content-Type: application/json' \\`);
  lines.push(`  -b 'admin_session=<your admin cookie>'`);
  if (opts?.body !== undefined) {
    const body = JSON.stringify(opts.body);
    lines[lines.length - 1] += " \\";
    lines.push(`  -d '${body.replace(/'/g, "'\\''")}'`);
  }
  return lines.join("\n");
}

const PROVIDER_TYPE_LABELS: Record<ModelProviderType, string> = {
  openai_compatible: "openai_compatible",
  xai: "xai (Grok)",
  gemini: "gemini",
  seedream_image: "seedream_image",
};

const KIND_LABEL: Record<ModelKind, string> = {
  text: "文本",
  image: "图像",
};

export default function ModelsPage() {
  const [tab, setTab] = useState<TabKey>("models");
  const [modal, setModal] = useState<
    | { kind: "provider"; item?: ModelProviderSummary }
    | { kind: "model"; item?: ProviderModelSummary }
    | null
  >(null);

  const dashboardQuery = useQuery({
    queryKey: ["admin", "model-dashboard"],
    queryFn: () =>
      apiFetch<ModelDashboardResponse>("/api/admin/model-dashboard"),
  });

  const data = dashboardQuery.data;

  return (
    <>
      <PageHeader
        title="模型管理"
        sub="配置 Provider、Model 单价以及功能槽位绑定"
        actions={
          tab === "providers" ? (
            <Btn
              variant="primary"
              icon={Plus}
              onClick={() => setModal({ kind: "provider" })}
            >
              新建 Provider
            </Btn>
          ) : tab === "models" ? (
            <Btn
              variant="primary"
              icon={Plus}
              onClick={() => setModal({ kind: "model" })}
            >
              新建 Model
            </Btn>
          ) : null
        }
      />

      <Tabs<TabKey>
        value={tab}
        onChange={setTab}
        options={[
          {
            value: "providers",
            label: "Providers",
            count: data?.providers.length,
          },
          { value: "models", label: "Models", count: data?.models.length },
          {
            value: "slots",
            label: "Slot Bindings",
            count: data?.slots.length,
          },
        ]}
      />

      {dashboardQuery.isPending ? (
        <div className="dim" style={{ padding: 24 }}>加载中…</div>
      ) : dashboardQuery.isError ? (
        <div style={{ padding: 24, color: "var(--danger)" }}>
          加载失败：{(dashboardQuery.error as Error).message}
        </div>
      ) : data ? (
        <>
          {tab === "providers" && (
            <ProvidersTab data={data} onEdit={(p) => setModal({ kind: "provider", item: p })} />
          )}
          {tab === "models" && (
            <ModelsTab data={data} onEdit={(m) => setModal({ kind: "model", item: m })} />
          )}
          {tab === "slots" && <SlotsTab data={data} />}
        </>
      ) : null}

      {modal?.kind === "provider" && (
        <ProviderModal item={modal.item} onClose={() => setModal(null)} />
      )}
      {modal?.kind === "model" && (
        <ModelModal item={modal.item} data={data} onClose={() => setModal(null)} />
      )}
    </>
  );
}

// ────────────── Providers tab ──────────────
function ProvidersTab({
  data,
  onEdit,
}: {
  data: ModelDashboardResponse;
  onEdit: (p: ModelProviderSummary) => void;
}) {
  const queryClient = useQueryClient();
  const [probe, setProbe] = useState<Record<string, ProbeState>>({});
  const [statusFilter, setStatusFilter] = useState<"all" | "active" | "disabled">("all");

  const rows = data.providers.filter((p) =>
    statusFilter === "all" ? true : p.status === statusFilter,
  );

  const healthcheck = useMutation({
    mutationFn: (id: string) =>
      apiFetch<{ ok: boolean; error: string | null }>(
        `/api/admin/model-providers/${id}/healthcheck`,
        { method: "POST" },
      ),
    onMutate: (id) => {
      setProbe((s) => ({ ...s, [id]: { state: "running" } }));
    },
    onSuccess: (res, id) => {
      if (res.ok) {
        setProbe((s) => ({ ...s, [id]: { state: "ok", latency_ms: 0 } }));
      } else {
        setProbe((s) => ({
          ...s,
          [id]: { state: "fail", error: res.error || "失败" },
        }));
      }
      queryClient.invalidateQueries({ queryKey: ["admin", "model-dashboard"] });
    },
    onError: (err, id) => {
      setProbe((s) => ({
        ...s,
        [id]: { state: "fail", error: (err as Error).message },
      }));
    },
  });

  const del = useMutation({
    mutationFn: (id: string) =>
      apiFetch<{ affected_slots: string[] }>(
        `/api/admin/model-providers/${id}`,
        { method: "DELETE" },
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "model-dashboard"] });
    },
    onError: (err) => alert((err as Error).message),
  });

  const onDelete = (p: ModelProviderSummary) => {
    const msg =
      p.model_count > 0
        ? `确认删除 Provider "${p.name}"？\n\n会一并删除其下 ${p.model_count} 个模型 + 所有 slot 绑定。`
        : `确认删除 Provider "${p.name}"？`;
    if (confirm(msg)) del.mutate(p.id);
  };

  const activeCount = data.providers.filter((p) => p.status === "active").length;

  return (
    <Card flush>
      <div className="filter-bar">
        <input
          className="input"
          placeholder="搜索 Provider 名称 / base_url…"
          style={{ width: 280 }}
        />
        <Segmented<"all" | "active" | "disabled">
          value={statusFilter}
          options={[
            { value: "all", label: "全部" },
            { value: "active", label: "启用" },
            { value: "disabled", label: "禁用" },
          ]}
          onChange={setStatusFilter}
        />
        <div className="cluster" style={{ marginLeft: "auto", gap: 8 }}>
          <span className="dim-2" style={{ fontSize: 12 }}>
            {data.providers.length} 个 Provider · {activeCount} 启用中
          </span>
          <CurlHover
            side="right"
            title={`对 ${data.providers.length} 个 provider 各发一次`}
            hint="鼠标移开关闭；点击复制"
            curl={data.providers
              .map((p) =>
                buildCurl(`/api/admin/model-providers/${p.id}/healthcheck`, {
                  method: "POST",
                }),
              )
              .join("\n\n")}
          >
            <Btn
              size="sm"
              icon={Play}
              onClick={() => data.providers.forEach((p) => healthcheck.mutate(p.id))}
              disabled={healthcheck.isPending}
            >
              全部健康检查
            </Btn>
          </CurlHover>
        </div>
      </div>
      <table className="tbl">
        <thead>
          <tr>
            <th style={{ width: 240 }}>名称</th>
            <th style={{ width: 140 }}>类型</th>
            <th>Base URL</th>
            <th style={{ width: 150 }}>API Key 环境变量</th>
            <th style={{ width: 100 }}>状态</th>
            <th style={{ width: 200 }}>健康检查</th>
            <th style={{ width: 60 }} className="num"></th>
          </tr>
        </thead>
        <tbody>
          {rows.map((p) => (
            <tr key={p.id} data-disabled={p.status === "disabled" || undefined}>
              <td>
                <div className="cluster">
                  <ProviderChip provider={p} />
                </div>
              </td>
              <td>
                <span className="mono">{PROVIDER_TYPE_LABELS[p.provider_type] || p.provider_type}</span>
              </td>
              <td className="mono dim">{p.base_url || "—"}</td>
              <td>
                <span className="mono" style={{ fontSize: 11 }}>
                  {p.api_key_count > 0
                    ? `${p.api_key_count} key：${p.api_key_previews.join("、")}`
                    : p.api_key_env_name || "—"}
                </span>
                {!p.api_key_available && (
                  <Badge tone="danger" style={{ marginLeft: 6 }}>缺 key</Badge>
                )}
              </td>
              <td>
                {p.status === "active" ? (
                  <Badge tone="success" dot>启用中</Badge>
                ) : p.status === "invalid" ? (
                  <Badge tone="danger" dot>异常</Badge>
                ) : (
                  <Badge tone="default" dot>已禁用</Badge>
                )}
              </td>
              <td>
                <ProbeCell
                  state={probe[p.id]}
                  defaultLabel={
                    p.last_healthcheck_at
                      ? `✓ ${fmtDateTime(p.last_healthcheck_at)}`
                      : p.last_healthcheck_error || null
                  }
                />
              </td>
              <td className="num">
                <div className="row-act">
                  <CurlHover
                    title={`POST  /model-providers/${p.id}/healthcheck`}
                    curl={buildCurl(
                      `/api/admin/model-providers/${p.id}/healthcheck`,
                      { method: "POST" },
                    )}
                  >
                    <Btn
                      variant="ghost"
                      size="xs"
                      icon={Play}
                      title="健康检查"
                      onClick={() => healthcheck.mutate(p.id)}
                    />
                  </CurlHover>
                  <Btn variant="ghost" size="xs" icon={Edit} title="编辑" onClick={() => onEdit(p)} />
                  <Btn
                    variant="ghost"
                    size="xs"
                    icon={Trash2}
                    title="删除"
                    onClick={() => onDelete(p)}
                    disabled={del.isPending}
                  />
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}

// ────────────── Models tab ──────────────
function ModelsTab({
  data,
  onEdit,
}: {
  data: ModelDashboardResponse;
  onEdit: (m: ProviderModelSummary) => void;
}) {
  const queryClient = useQueryClient();
  const [provFilter, setProvFilter] = useState<string>("all");
  const [kindFilter, setKindFilter] = useState<"all" | ModelKind>("all");

  const del = useMutation({
    mutationFn: (id: string) =>
      apiFetch(`/api/admin/provider-models/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "model-dashboard"] });
    },
    onError: (err) => alert((err as Error).message),
  });

  const onDelete = (m: ProviderModelSummary) => {
    const bound = m.binding_slots.length;
    const msg =
      bound > 0
        ? `确认删除模型 "${m.display_name}"？\n\n该模型已绑定到 ${bound} 个 slot，删除后这些 slot 会变成"未绑定"。`
        : `确认删除模型 "${m.display_name}"？`;
    if (confirm(msg)) del.mutate(m.id);
  };

  let rows = data.models;
  if (provFilter !== "all") rows = rows.filter((m) => m.provider_id === provFilter);
  if (kindFilter !== "all") rows = rows.filter((m) => m.model_kind === kindFilter);
  // 按 provider 名字 → 模型类别（text 在前，image 在后）→ display_name 排序
  rows = [...rows].sort((a, b) => {
    const pa = a.provider?.name || "";
    const pb = b.provider?.name || "";
    if (pa !== pb) return pa.localeCompare(pb, "zh");
    if (a.model_kind !== b.model_kind) return a.model_kind === "text" ? -1 : 1;
    return a.display_name.localeCompare(b.display_name, "zh");
  });

  const missing = data.models.filter((m) => {
    if (m.model_kind === "image") return m.image_price_cents_per_image == null;
    return (
      m.input_price_cents_per_million_tokens == null ||
      m.output_price_cents_per_million_tokens == null
    );
  }).length;

  return (
    <Card flush>
      <div className="filter-bar">
        <input
          className="input"
          placeholder="搜索模型名 / model_id…"
          style={{ width: 240 }}
        />
        <Select
          value={provFilter}
          onChange={setProvFilter}
          minWidth={170}
          menuWidth={220}
          options={[
            { value: "all", label: "全部 Provider" },
            ...data.providers.map((p) => ({
              value: p.id,
              label: p.name,
            })),
          ]}
        />
        <Segmented<"all" | ModelKind>
          value={kindFilter}
          options={[
            { value: "all", label: "全部" },
            { value: "text", label: "文本" },
            { value: "image", label: "图像" },
          ]}
          onChange={setKindFilter}
        />
        {missing > 0 && (
          <Badge tone="danger" dot style={{ marginLeft: "auto" }}>
            {missing} 个模型缺单价
          </Badge>
        )}
      </div>

      <table className="tbl">
        <thead>
          <tr>
            <th style={{ width: 220 }}>名称</th>
            <th style={{ width: 160 }}>Provider</th>
            <th style={{ width: 80 }}>类型</th>
            <th className="num" style={{ width: 130 }}>Input</th>
            <th className="num" style={{ width: 130 }}>Output</th>
            <th style={{ width: 100 }}>状态</th>
            <th style={{ width: 130 }}>更新时间</th>
            <th style={{ width: 64 }} className="num"></th>
          </tr>
        </thead>
        <tbody>
          {rows.map((m) => {
            const hasMissing =
              m.model_kind === "image"
                ? m.image_price_cents_per_image == null
                : m.input_price_cents_per_million_tokens == null ||
                  m.output_price_cents_per_million_tokens == null;
            return (
              <tr key={m.id} data-disabled={!m.is_enabled || undefined}>
                <td>
                  <div style={{ fontWeight: 500 }}>{m.display_name}</div>
                  <div className="mono dim" style={{ fontSize: 11, marginTop: 2 }}>
                    {m.model_id}
                  </div>
                </td>
                <td><ProviderChip provider={m.provider} /></td>
                <td>
                  <Badge tone={m.model_kind === "text" ? "default" : "info"}>
                    {KIND_LABEL[m.model_kind]}
                  </Badge>
                </td>
                <td className="num">
                  {m.model_kind === "image" ? (
                    m.image_price_cents_per_image == null ? (
                      <span className="cell-missing-price">未配置</span>
                    ) : (
                      <span className="tabular" style={{ fontWeight: 500 }}>
                        {fmtPricePerImage(m.image_price_cents_per_image)}
                      </span>
                    )
                  ) : m.input_price_cents_per_million_tokens == null ? (
                    <span className="cell-missing-price">未配置</span>
                  ) : (
                    <span className="tabular" style={{ fontWeight: 500 }}>
                      {fmtPricePerM(m.input_price_cents_per_million_tokens)}
                    </span>
                  )}
                </td>
                <td className="num">
                  {m.model_kind === "image" ? (
                    <span className="dim-2">—</span>
                  ) : m.output_price_cents_per_million_tokens == null ? (
                    <span className="cell-missing-price">未配置</span>
                  ) : (
                    <span className="tabular" style={{ fontWeight: 500 }}>
                      {fmtPricePerM(m.output_price_cents_per_million_tokens)}
                    </span>
                  )}
                </td>
                <td>
                  {m.is_enabled ? (
                    <Badge tone="success" dot>启用中</Badge>
                  ) : (
                    <Badge tone="default" dot>已禁用</Badge>
                  )}
                  {hasMissing && m.is_enabled && (
                    <Badge tone="warning" style={{ marginLeft: 4 }}>缺价</Badge>
                  )}
                </td>
                <td className="dim" style={{ fontSize: 11.5 }}>
                  {m.price_updated_at ? fmtDateTime(m.price_updated_at) : "—"}
                </td>
                <td className="num">
                  <div className="row-act">
                    <Btn variant="ghost" size="xs" icon={Edit} title="编辑" onClick={() => onEdit(m)} />
                    <Btn
                      variant="ghost"
                      size="xs"
                      icon={Trash2}
                      title="删除"
                      onClick={() => onDelete(m)}
                      disabled={del.isPending}
                    />
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </Card>
  );
}

// ────────────── Slots tab ──────────────
function SlotsTab({ data }: { data: ModelDashboardResponse }) {
  const queryClient = useQueryClient();
  const [probe, setProbe] = useState<Record<string, ProbeState>>({});

  const bindMutation = useMutation({
    mutationFn: ({ slot, model_id }: { slot: string; model_id: string | null }) =>
      apiFetch(`/api/admin/model-slots/${slot}`, {
        method: "PUT",
        body: JSON.stringify({ model_id }),
      }),
    onMutate: ({ slot }) => {
      setProbe((s) => ({ ...s, [slot]: { state: "running" } }));
    },
    onSuccess: (_res, { slot }) => {
      setProbe((s) => ({ ...s, [slot]: { state: "ok", latency_ms: 0 } }));
      queryClient.invalidateQueries({ queryKey: ["admin", "model-dashboard"] });
    },
    onError: (err, { slot }) => {
      setProbe((s) => ({
        ...s,
        [slot]: { state: "fail", error: (err as Error).message },
      }));
    },
  });

  // 按 slot 触发能力探测：复用 /provider-models/{id}/probe（body 是 capabilities 列表）
  const probeMutation = useMutation({
    mutationFn: async ({
      slotName,
      modelId,
      capabilities,
    }: {
      slotName: string;
      modelId: string;
      capabilities: string[];
    }) => {
      setProbe((s) => ({ ...s, [slotName]: { state: "running" } }));
      return apiFetch(`/api/admin/provider-models/${modelId}/probe`, {
        method: "POST",
        body: JSON.stringify({ capabilities }),
      });
    },
    onSuccess: (_res, { slotName }) => {
      setProbe((s) => ({ ...s, [slotName]: { state: "ok", latency_ms: 0 } }));
      queryClient.invalidateQueries({ queryKey: ["admin", "model-dashboard"] });
    },
    onError: (err, { slotName }) => {
      setProbe((s) => ({
        ...s,
        [slotName]: { state: "fail", error: (err as Error).message },
      }));
    },
  });

  const verifyAll = () => {
    data.slots.forEach((s) => {
      if (s.binding?.model?.id) {
        probeMutation.mutate({
          slotName: s.slot_name,
          modelId: s.binding.model.id,
          capabilities: s.required_capabilities,
        });
      }
    });
  };

  // Group model options by provider, filter by enabled
  const groupsByKind = (kind: ModelKind) =>
    data.providers
      .filter((p) => p.status === "active")
      .map((p) => ({
        label: p.name,
        options: data.models
          .filter(
            (m) => m.provider_id === p.id && m.is_enabled && m.model_kind === kind,
          )
          .map((m) => ({
            value: m.id,
            label: m.display_name,
            meta:
              m.model_kind === "image"
                ? fmtPricePerImage(m.image_price_cents_per_image)
                : `${fmtPricePerM(m.input_price_cents_per_million_tokens)} / ${fmtPricePerM(m.output_price_cents_per_million_tokens)}`,
          })),
      }))
      .filter((g) => g.options.length > 0);

  return (
    <Card flush>
      <div className="filter-bar">
        <input className="input" placeholder="搜索 slot 名…" style={{ width: 240 }} />
        <div className="cluster" style={{ marginLeft: "auto", gap: 8 }}>
          <span className="dim-2" style={{ fontSize: 12 }}>
            每个 slot 可独立换绑模型，无需改代码
          </span>
          <CurlHover
            side="right"
            title={`对每个有绑定的 slot 发一次 probe`}
            hint="鼠标移开关闭；点击复制"
            curl={data.slots
              .filter((s) => s.binding?.model?.id)
              .map((s) =>
                buildCurl(`/api/admin/provider-models/${s.binding!.model!.id}/probe`, {
                  method: "POST",
                  body: { capabilities: s.required_capabilities },
                }),
              )
              .join("\n\n")}
          >
            <Btn
              size="sm"
              icon={Play}
              onClick={verifyAll}
              disabled={probeMutation.isPending}
            >
              全部验证
            </Btn>
          </CurlHover>
        </div>
      </div>

      <table className="tbl">
        <thead>
          <tr>
            <th style={{ width: 240 }}>Slot</th>
            <th>说明</th>
            <th style={{ width: 320 }}>当前绑定</th>
            <th style={{ width: 200 }}>最近验证</th>
            <th style={{ width: 60 }} className="num"></th>
          </tr>
        </thead>
        <tbody>
          {data.slots.map((s) => {
            const bound = s.binding?.model;
            const probeState =
              probe[s.slot_name] ??
              (s.binding?.last_verified_error
                ? { state: "fail" as const, error: s.binding.last_verified_error }
                : s.binding?.last_verified_at
                ? { state: "ok" as const, latency_ms: 0 }
                : undefined);
            const defaultLabel = s.binding?.last_verified_at
              ? `✓ ${fmtDateTime(s.binding.last_verified_at)}`
              : null;
            return (
              <tr key={s.slot_name}>
                <td>
                  <div className="cluster">
                    <span className="mono" style={{ fontSize: 12, fontWeight: 500 }}>
                      {s.slot_name}
                    </span>
                    <Badge tone="accent">{KIND_LABEL[s.model_kind]}</Badge>
                  </div>
                  <div className="dim-2" style={{ fontSize: 10.5, marginTop: 3 }}>
                    {s.label}
                  </div>
                </td>
                <td className="dim" style={{ fontSize: 12 }}>
                  {s.description}
                </td>
                <td>
                  <Select
                    value={bound?.id || ""}
                    onChange={(v) =>
                      bindMutation.mutate({ slot: s.slot_name, model_id: v || null })
                    }
                    groups={groupsByKind(s.model_kind)}
                    minWidth={280}
                    menuWidth={320}
                    placeholder="未绑定"
                    renderValue={() =>
                      bound ? (
                        <span style={{ display: "inline-flex", alignItems: "center", gap: 8, overflow: "hidden" }}>
                          <ProviderChip provider={bound.provider} withName={false} />
                          <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                            {bound.display_name}
                          </span>
                        </span>
                      ) : (
                        <span className="dim-2">未绑定</span>
                      )
                    }
                  />
                </td>
                <td>
                  <ProbeCell state={probeState} defaultLabel={defaultLabel} />
                </td>
                <td className="num">
                  <div className="row-act">
                    {bound?.id ? (
                      <CurlHover
                        title={`POST  /provider-models/${bound.id}/probe`}
                        hint={`capabilities: ${s.required_capabilities.join(", ") || "(none)"}`}
                        curl={buildCurl(
                          `/api/admin/provider-models/${bound.id}/probe`,
                          {
                            method: "POST",
                            body: { capabilities: s.required_capabilities },
                          },
                        )}
                      >
                        <Btn
                          variant="ghost"
                          size="xs"
                          icon={Play}
                          title="验证此 slot"
                          onClick={() =>
                            probeMutation.mutate({
                              slotName: s.slot_name,
                              modelId: bound.id,
                              capabilities: s.required_capabilities,
                            })
                          }
                          disabled={
                            probeState?.state === "running"
                          }
                        />
                      </CurlHover>
                    ) : (
                      <Btn
                        variant="ghost"
                        size="xs"
                        icon={Play}
                        title="未绑定模型，无法验证"
                        disabled
                      />
                    )}
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </Card>
  );
}

// ────────────── Probe cell ──────────────
function ProbeCell({
  state,
  defaultLabel,
}: {
  state: ProbeState;
  defaultLabel: string | null;
}) {
  if (state?.state === "running") {
    return (
      <span className="probe probe-running">
        <span className="probe-spin" /> 验证中…
      </span>
    );
  }
  if (state?.state === "ok") {
    return (
      <span className="probe probe-ok">
        ✓ {state.latency_ms ? `${state.latency_ms} ms` : "通过"}
      </span>
    );
  }
  if (state?.state === "fail") {
    return (
      <span className="probe probe-fail" title={state.error}>
        ✗ {state.error}
      </span>
    );
  }
  return <span className="dim" style={{ fontSize: 11.5 }}>{defaultLabel || "—"}</span>;
}

// ────────────── Provider Modal ──────────────
function ProviderModal({
  item,
  onClose,
}: {
  item?: ModelProviderSummary;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const isNew = !item;
  const [form, setForm] = useState({
    name: item?.name || "",
    provider_type: (item?.provider_type as ModelProviderType) || "openai_compatible",
    base_url: item?.base_url || "",
    api_key_env_name: item?.api_key_env_name || "",
    api_keys_text: "", // 编辑时不回填明文；留空=保持原有
    status: (item?.status as string) || "active",
  });
  const [error, setError] = useState<string | null>(null);

  const save = useMutation({
    mutationFn: async () => {
      // 注意：不再发 extra_config —— 后端 update 已会保留 source 标记，
      // 前端发 {} 仍然安全，但少发一个字段更清晰。
      const body = JSON.stringify({
        name: form.name,
        provider_type: form.provider_type,
        base_url: form.base_url || null,
        api_key_env_name: form.api_key_env_name || null,
        // 一行/一个逗号一个 key；留空时编辑=不动(null)、新建=不发
        ...(() => {
          const parsed = form.api_keys_text
            .split(/[\n,]+/)
            .map((k) => k.trim())
            .filter(Boolean);
          if (parsed.length) return { api_keys: parsed };
          return isNew ? {} : { api_keys: null };
        })(),
        extra_config: item?.extra_config || {},
        ...(isNew ? {} : { status: form.status }),
      });
      const path = isNew
        ? "/api/admin/model-providers"
        : `/api/admin/model-providers/${item!.id}`;
      return apiFetch(path, { method: isNew ? "POST" : "PUT", body });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "model-dashboard"] });
      onClose();
    },
    onError: (err) => setError((err as Error).message),
  });

  const del = useMutation({
    mutationFn: () =>
      apiFetch(`/api/admin/model-providers/${item!.id}`, { method: "DELETE" }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "model-dashboard"] });
      onClose();
    },
    onError: (err) => setError((err as Error).message),
  });

  return (
    <Modal
      open
      onClose={onClose}
      title={isNew ? "新建 Provider" : "编辑 Provider"}
      sub={isNew ? "添加一个 LLM 服务商" : item?.name}
      footer={
        <>
          {!isNew && (
            <Btn variant="danger" onClick={() => del.mutate()} disabled={del.isPending}>
              删除
            </Btn>
          )}
          <div style={{ flex: 1 }} />
          <Btn onClick={onClose}>取消</Btn>
          <Btn variant="primary" onClick={() => save.mutate()} disabled={save.isPending}>
            {save.isPending ? "保存中…" : isNew ? "创建" : "保存"}
          </Btn>
        </>
      }
    >
      {error && (
        <div className="field-error" style={{ marginBottom: 12 }}>{error}</div>
      )}
      <div className="field">
        <label className="field-label field-label-req">名称</label>
        <input
          className="input"
          value={form.name}
          onChange={(e) => setForm({ ...form, name: e.target.value })}
          placeholder="例如 DeepSeek"
        />
      </div>

      <div className="field-row">
        <div className="field">
          <label className="field-label field-label-req">类型</label>
          <select
            className="input"
            value={form.provider_type}
            onChange={(e) =>
              setForm({ ...form, provider_type: e.target.value as ModelProviderType })
            }
          >
            <option value="openai_compatible">openai_compatible</option>
            <option value="xai">xai (Grok)</option>
            <option value="gemini">gemini</option>
            <option value="seedream_image">seedream_image</option>
          </select>
        </div>
        {!isNew && (
          <div className="field">
            <label className="field-label">状态</label>
            <select
              className="input"
              value={form.status}
              onChange={(e) => setForm({ ...form, status: e.target.value })}
            >
              <option value="active">启用</option>
              <option value="disabled">禁用</option>
            </select>
          </div>
        )}
      </div>

      <div className="field">
        <label className="field-label">Base URL</label>
        <input
          className="input"
          value={form.base_url}
          onChange={(e) => setForm({ ...form, base_url: e.target.value })}
          placeholder="https://api.example.com/v1"
        />
      </div>

      <div className="field">
        <label className="field-label">API Keys（直填，一行一个）</label>
        <textarea
          className="input mono"
          rows={3}
          value={form.api_keys_text}
          onChange={(e) => setForm({ ...form, api_keys_text: e.target.value })}
          placeholder={isNew ? "sk-xxx\nsk-yyy" : "留空 = 保持原有 key 不变"}
        />
        <div className="field-hint">
          {isNew
            ? "直填的 key 存数据库（优先于环境变量名）；多个 key 会按会话轮询分散并发"
            : `当前 ${item?.api_key_count ?? 0} 个 key：${
                (item?.api_key_previews || []).join("、") || "—"
              }。重填将整组替换。`}
        </div>
      </div>

      <div className="field">
        <label className="field-label">API Key 环境变量名（可选）</label>
        <input
          className="input mono"
          value={form.api_key_env_name}
          onChange={(e) => setForm({ ...form, api_key_env_name: e.target.value })}
          placeholder="EXAMPLE_API_KEY"
        />
        <div className="field-hint">未直填 key 时，从该环境变量读取（值可逗号分隔多个）</div>
      </div>
    </Modal>
  );
}

// ────────────── Model Modal ──────────────
function ModelModal({
  item,
  data,
  onClose,
}: {
  item?: ProviderModelSummary;
  data?: ModelDashboardResponse;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const isNew = !item;
  const [form, setForm] = useState({
    provider_id: item?.provider_id || data?.providers[0]?.id || "",
    model_id: item?.model_id || "",
    display_name: item?.display_name || "",
    model_kind: (item?.model_kind as ModelKind) || "text",
    is_enabled: item?.is_enabled ?? true,
    notes: item?.notes || "",
    input_price_cents_per_million_tokens:
      item?.input_price_cents_per_million_tokens?.toString() || "",
    output_price_cents_per_million_tokens:
      item?.output_price_cents_per_million_tokens?.toString() || "",
    image_price_cents_per_image: item?.image_price_cents_per_image?.toString() || "",
  });
  const [error, setError] = useState<string | null>(null);

  const save = useMutation({
    mutationFn: async () => {
      const body: Record<string, unknown> = {
        display_name: form.display_name,
        model_kind: form.model_kind,
        is_enabled: form.is_enabled,
        notes: form.notes || null,
        input_price_cents_per_million_tokens: form.input_price_cents_per_million_tokens
          ? Number(form.input_price_cents_per_million_tokens)
          : null,
        output_price_cents_per_million_tokens: form.output_price_cents_per_million_tokens
          ? Number(form.output_price_cents_per_million_tokens)
          : null,
        image_price_cents_per_image: form.image_price_cents_per_image
          ? Number(form.image_price_cents_per_image)
          : null,
      };
      if (isNew) {
        body.provider_id = form.provider_id;
        body.model_id = form.model_id;
      }
      const path = isNew
        ? "/api/admin/provider-models"
        : `/api/admin/provider-models/${item!.id}`;
      return apiFetch(path, {
        method: isNew ? "POST" : "PUT",
        body: JSON.stringify(body),
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "model-dashboard"] });
      onClose();
    },
    onError: (err) => setError((err as Error).message),
  });

  const del = useMutation({
    mutationFn: () =>
      apiFetch(`/api/admin/provider-models/${item!.id}`, { method: "DELETE" }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "model-dashboard"] });
      onClose();
    },
    onError: (err) => setError((err as Error).message),
  });

  return (
    <Modal
      open
      onClose={onClose}
      title={isNew ? "新建 Model" : "编辑 Model"}
      sub={isNew ? "在已有 Provider 下添加一个具体模型" : `${item!.display_name} · ${item!.model_id}`}
      width={620}
      footer={
        <>
          {!isNew && (
            <Btn variant="danger" onClick={() => del.mutate()} disabled={del.isPending}>
              删除
            </Btn>
          )}
          <div style={{ flex: 1 }} />
          <Btn onClick={onClose}>取消</Btn>
          <Btn variant="primary" onClick={() => save.mutate()} disabled={save.isPending}>
            {save.isPending ? "保存中…" : isNew ? "创建" : "保存"}
          </Btn>
        </>
      }
    >
      {error && (
        <div className="field-error" style={{ marginBottom: 12 }}>{error}</div>
      )}
      <div className="field-row">
        <div className="field">
          <label className="field-label field-label-req">Provider</label>
          <select
            className="input"
            value={form.provider_id}
            onChange={(e) => setForm({ ...form, provider_id: e.target.value })}
            disabled={!isNew}
          >
            {data?.providers.map((p) => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
        </div>
        <div className="field">
          <label className="field-label field-label-req">类型</label>
          <select
            className="input"
            value={form.model_kind}
            onChange={(e) => setForm({ ...form, model_kind: e.target.value as ModelKind })}
            disabled={!isNew}
          >
            <option value="text">text（文本生成）</option>
            <option value="image">image（图像生成）</option>
          </select>
        </div>
      </div>

      <div className="field">
        <label className="field-label field-label-req">显示名</label>
        <input
          className="input"
          value={form.display_name}
          onChange={(e) => setForm({ ...form, display_name: e.target.value })}
          placeholder="Claude Sonnet 4.5"
        />
      </div>

      <div className="field">
        <label className="field-label field-label-req">Model ID</label>
        <input
          className="input mono"
          value={form.model_id}
          onChange={(e) => setForm({ ...form, model_id: e.target.value })}
          placeholder="claude-sonnet-4-5"
          disabled={!isNew}
        />
        <div className="field-hint">调用 API 时使用的标识，创建后不可改</div>
      </div>

      <div
        style={{
          margin: "8px 0 14px",
          padding: "12px 14px",
          background: "var(--accent-soft)",
          borderRadius: 7,
          border: "1px solid color-mix(in oklch, var(--accent) 18%, transparent)",
        }}
      >
        <div
          style={{
            fontSize: 11,
            fontWeight: 600,
            textTransform: "uppercase",
            letterSpacing: "0.05em",
            color: "var(--accent)",
            marginBottom: 10,
          }}
        >
          单价 · {form.model_kind === "text" ? "按 token 计费" : "按张计费"}
        </div>
        {form.model_kind === "text" ? (
          <div className="field-row">
            <div className="field" style={{ marginBottom: 0 }}>
              <label className="field-label field-label-req">Input 单价</label>
              <div className="field-suffix">
                <input
                  className="input mono"
                  value={form.input_price_cents_per_million_tokens}
                  onChange={(e) =>
                    setForm({ ...form, input_price_cents_per_million_tokens: e.target.value })
                  }
                  placeholder="300"
                />
                <span className="field-suffix-tag">分/百万 token</span>
              </div>
            </div>
            <div className="field" style={{ marginBottom: 0 }}>
              <label className="field-label field-label-req">Output 单价</label>
              <div className="field-suffix">
                <input
                  className="input mono"
                  value={form.output_price_cents_per_million_tokens}
                  onChange={(e) =>
                    setForm({ ...form, output_price_cents_per_million_tokens: e.target.value })
                  }
                  placeholder="1500"
                />
                <span className="field-suffix-tag">分/百万 token</span>
              </div>
            </div>
          </div>
        ) : (
          <div className="field" style={{ marginBottom: 0 }}>
            <label className="field-label field-label-req">单价</label>
            <div className="field-suffix">
              <input
                className="input mono"
                value={form.image_price_cents_per_image}
                onChange={(e) =>
                  setForm({ ...form, image_price_cents_per_image: e.target.value })
                }
                placeholder="390"
              />
              <span className="field-suffix-tag">分/张</span>
            </div>
          </div>
        )}
      </div>

      <div className="field">
        <label className="field-label">备注</label>
        <textarea
          className="input"
          value={form.notes}
          onChange={(e) => setForm({ ...form, notes: e.target.value })}
          placeholder="给团队看的说明"
        />
      </div>

      <div className="field" style={{ marginBottom: 0 }}>
        <label className="field-label">
          <span>启用</span>
          <button
            type="button"
            className="tgl"
            data-on={form.is_enabled || undefined}
            onClick={() => setForm({ ...form, is_enabled: !form.is_enabled })}
            aria-label="启用模型"
          />
        </label>
      </div>
    </Modal>
  );
}
