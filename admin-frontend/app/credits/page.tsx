"use client";

import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { PageHeader } from "@/components/PageHeader";
import { Btn } from "@/components/ui/Btn";
import { Card } from "@/components/ui/Card";
import { apiFetch } from "@/lib/api";

interface CreditConfig {
  billing_multiplier: number;
  signup_grant: number;
  estimate_game: number;
  estimate_world: number;
  estimate_script: number;
}

type FieldKey = keyof CreditConfig;

const FIELDS: { key: FieldKey; label: string; hint?: string; step?: string }[] = [
  { key: "billing_multiplier", label: "计费倍率", hint: "扣的积分 = 真实成本 × 倍率；毛利 = 1 − 1/倍率", step: "0.1" },
  { key: "signup_grant", label: "注册初始额度（积分）" },
  { key: "estimate_game", label: "回合预检额（积分）", hint: "余额低于此值则拦截一回合（L2 闸门）" },
  { key: "estimate_world", label: "世界生成预检额（积分）" },
  { key: "estimate_script", label: "剧本生成预检额（积分）" },
];

export default function CreditsConfigPage() {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<Record<string, string>>({});
  const [dirty, setDirty] = useState(false);

  const configQuery = useQuery({
    queryKey: ["admin-credit-config"],
    queryFn: () => apiFetch<CreditConfig>("/api/admin/credits/config"),
  });

  useEffect(() => {
    if (configQuery.data && !dirty) {
      const d = configQuery.data;
      setForm({
        billing_multiplier: String(d.billing_multiplier),
        signup_grant: String(d.signup_grant),
        estimate_game: String(d.estimate_game),
        estimate_world: String(d.estimate_world),
        estimate_script: String(d.estimate_script),
      });
    }
  }, [configQuery.data, dirty]);

  const save = useMutation({
    mutationFn: (payload: Partial<CreditConfig>) =>
      apiFetch<CreditConfig>("/api/admin/credits/config", {
        method: "PUT",
        body: JSON.stringify(payload),
      }),
    onSuccess: (data) => {
      setDirty(false);
      queryClient.setQueryData(["admin-credit-config"], data);
    },
  });

  const onChange = (key: string, value: string) => {
    setForm((f) => ({ ...f, [key]: value }));
    setDirty(true);
  };

  const onSave = () => {
    const payload: Record<string, number> = {};
    for (const f of FIELDS) {
      const n = Number(form[f.key]);
      if (Number.isFinite(n)) payload[f.key] = n;
    }
    save.mutate(payload as Partial<CreditConfig>);
  };

  const multiplier = Number(form.billing_multiplier);
  const margin =
    Number.isFinite(multiplier) && multiplier > 0 ? Math.round((1 - 1 / multiplier) * 100) : null;

  return (
    <>
      <PageHeader
        title="积分经济"
        sub="计费倍率 / 初始额度 / 各动作预检额 —— 改动即时生效"
        actions={
          <Btn variant="primary" onClick={onSave} disabled={!dirty || save.isPending}>
            {save.isPending ? "保存中…" : "保存"}
          </Btn>
        }
      />
      <Card title="参数">
        {configQuery.isPending ? (
          <div className="dim-2">加载中…</div>
        ) : configQuery.isError ? (
          <div style={{ color: "var(--danger)" }}>加载失败：{(configQuery.error as Error).message}</div>
        ) : (
          <div style={{ display: "grid", gap: 16, maxWidth: 460 }}>
            {FIELDS.map((f) => (
              <div className="field" key={f.key}>
                <label>{f.label}</label>
                <input
                  className="input"
                  type="number"
                  step={f.step ?? "1"}
                  value={form[f.key] ?? ""}
                  onChange={(e) => onChange(f.key, e.target.value)}
                />
                {f.key === "billing_multiplier" && margin !== null ? (
                  <div className="dim" style={{ fontSize: 11.5, marginTop: 4 }}>
                    当前毛利 ≈ {margin}%（{f.hint}）
                  </div>
                ) : f.hint ? (
                  <div className="dim" style={{ fontSize: 11.5, marginTop: 4 }}>{f.hint}</div>
                ) : null}
              </div>
            ))}
            {save.isError && (
              <div style={{ color: "var(--danger)", fontSize: 12 }}>{(save.error as Error).message}</div>
            )}
            {save.isSuccess && !dirty && (
              <div style={{ color: "var(--accent)", fontSize: 12 }}>已保存</div>
            )}
          </div>
        )}
      </Card>
    </>
  );
}
