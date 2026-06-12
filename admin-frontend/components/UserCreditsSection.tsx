"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiFetch } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";

interface LedgerItem {
  id: string;
  ts: string;
  kind: string;
  category: string | null;
  delta: number;
  balance_after: number;
  cost_cents: number | null;
  note: string | null;
}

interface UserCredits {
  balance: number;
  lifetime_granted: number;
  lifetime_spent: number;
  ledger: LedgerItem[];
}

const fmt = (n: number) => n.toLocaleString("zh-CN", { maximumFractionDigits: 1 });
const fmtTime = (ts: string) => fmtDateTime(ts).slice(5, 16);

export function UserCreditsSection({ userId }: { userId: string | null }) {
  const queryClient = useQueryClient();
  const [delta, setDelta] = useState("");
  const [note, setNote] = useState("");

  const creditsQuery = useQuery({
    queryKey: ["admin-user-credits", userId],
    queryFn: () => apiFetch<UserCredits>(`/api/admin/users/${userId}/credits`),
    enabled: !!userId,
  });

  const adjust = useMutation({
    mutationFn: (payload: { delta_credits: number; note?: string }) =>
      apiFetch<{ balance: number }>(`/api/admin/users/${userId}/credits/adjust`, {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    onSuccess: () => {
      setDelta("");
      setNote("");
      queryClient.invalidateQueries({ queryKey: ["admin-user-credits", userId] });
    },
  });

  const data = creditsQuery.data;
  const deltaNum = Number(delta);
  const canSubmit =
    delta.trim() !== "" && Number.isFinite(deltaNum) && deltaNum !== 0 && !adjust.isPending;

  return (
    <section className="drawer-section">
      <div className="drawer-section-label">积分</div>

      {creditsQuery.isPending && <div className="dim-2">加载中…</div>}
      {creditsQuery.isError && (
        <div style={{ color: "var(--danger)" }}>加载失败：{(creditsQuery.error as Error).message}</div>
      )}

      {data && (
        <>
          <div style={{ display: "flex", gap: 24, marginBottom: 14 }}>
            <div>
              <div className="dim" style={{ fontSize: 11 }}>余额</div>
              <div style={{ fontSize: 19, fontWeight: 700, marginTop: 2 }}>{fmt(data.balance)}</div>
            </div>
            <div>
              <div className="dim" style={{ fontSize: 11 }}>累计获得</div>
              <div style={{ fontSize: 13, marginTop: 5 }}>{fmt(data.lifetime_granted)}</div>
            </div>
            <div>
              <div className="dim" style={{ fontSize: 11 }}>累计消耗</div>
              <div style={{ fontSize: 13, marginTop: 5 }}>{fmt(data.lifetime_spent)}</div>
            </div>
          </div>

          <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 6 }}>
            <input
              className="input"
              type="number"
              placeholder="增减积分(可负)"
              value={delta}
              onChange={(e) => setDelta(e.target.value)}
              style={{ width: 130 }}
            />
            <input
              className="input"
              placeholder="原因(可选)"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              style={{ flex: 1, minWidth: 0 }}
            />
            <button
              className="btn btn-primary btn-sm"
              disabled={!canSubmit}
              onClick={() => adjust.mutate({ delta_credits: deltaNum, note: note.trim() || undefined })}
            >
              {adjust.isPending ? "…" : "调整"}
            </button>
          </div>
          {adjust.isError && (
            <div style={{ color: "var(--danger)", fontSize: 12, marginBottom: 8 }}>
              {(adjust.error as Error).message}
            </div>
          )}

          <div style={{ borderTop: "1px solid var(--border)", marginTop: 8 }}>
            {data.ledger.length === 0 ? (
              <div className="dim-2" style={{ paddingTop: 10 }}>暂无记录</div>
            ) : (
              data.ledger.slice(0, 12).map((row) => (
                <div
                  key={row.id}
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    gap: 12,
                    padding: "7px 0",
                    borderBottom: "1px solid var(--border)",
                    fontSize: 12.5,
                  }}
                >
                  <div style={{ minWidth: 0 }}>
                    <div>
                      {row.kind}
                      {row.note ? ` · ${row.note}` : ""}
                    </div>
                    <div className="dim mono" style={{ fontSize: 11, marginTop: 2 }}>{fmtTime(row.ts)}</div>
                  </div>
                  <div style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                    <div style={{ fontWeight: 600, color: row.delta >= 0 ? "var(--accent)" : "var(--fg)" }}>
                      {row.delta >= 0 ? "+" : ""}
                      {fmt(row.delta)}
                    </div>
                    <div className="dim mono" style={{ fontSize: 10.5, marginTop: 2 }}>{fmt(row.balance_after)}</div>
                  </div>
                </div>
              ))
            )}
          </div>
        </>
      )}
    </section>
  );
}
