"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, ClipboardList } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { PageHeader } from "@/components/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Btn } from "@/components/ui/Btn";
import { Card } from "@/components/ui/Card";
import { Drawer } from "@/components/ui/Drawer";
import { UserCreditsSection } from "@/components/UserCreditsSection";
import { Segmented } from "@/components/ui/Segmented";
import { Select } from "@/components/ui/Select";
import { Toggle } from "@/components/ui/Toggle";
import { apiFetch } from "@/lib/api";
import { useMe } from "@/lib/auth";
import { colorFromString, fmtDateTime, initials } from "@/lib/format";
import { fmtCentsTotal } from "@/lib/pricing";
import type {
  AdminUserDetail,
  AdminUserListItem,
  AdminUserListResponse,
  UpdateUserPayload,
  UserPermissionFilter,
  UserStatus,
} from "@/lib/types";

const PAGE_SIZE = 50;

type StatusFilter = "all" | UserStatus;
type OrderBy = "created_at" | "last_login_at";

export default function UsersPage() {
  const [q, setQ] = useState("");
  const [permission, setPermission] = useState<UserPermissionFilter>("all");
  const [status, setStatus] = useState<StatusFilter>("all");
  const [orderBy, setOrderBy] = useState<OrderBy>("created_at");
  const [page, setPage] = useState(1);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const listQuery = useQuery({
    queryKey: ["admin-users", page, q, permission, status, orderBy],
    queryFn: () => {
      const params = new URLSearchParams({
        page: String(page),
        limit: String(PAGE_SIZE),
        permission,
        status,
        order_by: orderBy,
      });
      if (q.trim()) params.set("q", q.trim());
      return apiFetch<AdminUserListResponse>(
        `/api/admin/users?${params.toString()}`,
      );
    },
    placeholderData: (p) => p,
  });

  const data = listQuery.data;
  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;

  return (
    <>
      <PageHeader
        title="用户管理"
        sub={
          data
            ? `共 ${data.summary.total} 个用户 · ${data.summary.admin_count} 个 admin · ${data.summary.can_create_count} 个 can_create · ${data.summary.banned_count} 个 banned`
            : "—"
        }
      />

      <Card flush>
        <div className="filter-bar">
          <input
            className="input"
            placeholder="搜索 nickname / id / email…"
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              setPage(1);
            }}
            style={{ width: 280 }}
          />
          <Select
            value={permission}
            onChange={(v) => {
              setPermission(v as UserPermissionFilter);
              setPage(1);
            }}
            minWidth={150}
            options={[
              { value: "all", label: "全部权限" },
              { value: "admin", label: "仅 admin" },
              { value: "can_create", label: "可创作" },
              { value: "no_perm", label: "普通用户" },
            ]}
          />
          <Segmented<StatusFilter>
            value={status}
            options={[
              { value: "all", label: "全部" },
              { value: "active", label: "active" },
              { value: "banned", label: "banned" },
            ]}
            onChange={(v) => {
              setStatus(v);
              setPage(1);
            }}
          />
          <Select
            value={orderBy}
            onChange={(v) => setOrderBy(v as OrderBy)}
            minWidth={140}
            options={[
              { value: "created_at", label: "按 注册时间" },
              { value: "last_login_at", label: "按 最近登录" },
            ]}
          />
          <span
            className="dim-2"
            style={{ marginLeft: "auto", fontSize: 12 }}
          >
            {listQuery.isFetching ? "加载中…" : data ? `${data.items.length} / ${data.total}` : ""}
          </span>
        </div>

        <table className="tbl">
          <thead>
            <tr>
              <th style={{ width: 240 }}>用户</th>
              <th style={{ width: 160 }}>权限</th>
              <th style={{ width: 90 }}>状态</th>
              <th style={{ width: 130 }}>注册时间</th>
              <th style={{ width: 130 }}>最近登录</th>
              <th className="num" style={{ width: 130 }}>草稿 / 已发布</th>
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
                  无匹配用户
                </td>
              </tr>
            ) : (
              data.items.map((u) => (
                <UserRow key={u.id} u={u} onClick={() => setSelectedId(u.id)} />
              ))
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

      <UserDrawer
        userId={selectedId}
        onClose={() => setSelectedId(null)}
      />
    </>
  );
}

// ────────────── Row ──────────────
function UserRow({
  u,
  onClick,
}: {
  u: AdminUserListItem;
  onClick: () => void;
}) {
  const email = u.identities.find((i) => i.email)?.email;
  return (
    <tr style={{ cursor: "pointer" }} onClick={onClick}>
      <td>
        <div className="cluster">
          <span
            className="av-inline"
            style={{
              background: colorFromString(u.id),
              width: 24,
              height: 24,
              fontSize: 11,
            }}
          >
            {initials(u.nickname || u.id)}
          </span>
          <div style={{ minWidth: 0 }}>
            <div style={{ fontWeight: 500 }}>
              {u.nickname || <span className="dim-2">未设置昵称</span>}
            </div>
            <div
              className="mono dim"
              style={{
                fontSize: 11,
                marginTop: 2,
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
            >
              {email || u.id.slice(0, 12) + "…"}
            </div>
          </div>
        </div>
      </td>
      <td>
        <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
          {u.is_admin && <Badge tone="accent">admin</Badge>}
          {u.can_create && <Badge tone="info">can_create</Badge>}
          {!u.is_admin && !u.can_create && <span className="dim-2">普通</span>}
        </div>
      </td>
      <td>
        {u.status === "banned" ? (
          <Badge tone="danger" dot>banned</Badge>
        ) : (
          <Badge tone="success" dot>active</Badge>
        )}
      </td>
      <td className="dim" style={{ fontSize: 11.5 }}>
        {u.created_at ? fmtDateTime(u.created_at).slice(0, 10) : "—"}
      </td>
      <td className="dim" style={{ fontSize: 11.5 }}>
        {u.last_login_at ? fmtDateTime(u.last_login_at) : "—"}
      </td>
      <td className="num tabular">
        <span style={{ color: "var(--fg-secondary)" }}>{u.drafts_count}</span>
        <span className="dim-2"> / </span>
        <span style={{ fontWeight: 500 }}>
          {u.published_worlds_count + u.published_scripts_count}
        </span>
      </td>
    </tr>
  );
}

// ────────────── Drawer ──────────────
function UserDrawer({
  userId,
  onClose,
}: {
  userId: string | null;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();

  const { data: me } = useMe();

  const detailQuery = useQuery({
    queryKey: ["admin-user-detail", userId],
    queryFn: () =>
      apiFetch<AdminUserDetail>(`/api/admin/users/${userId}`),
    enabled: !!userId,
  });

  const patch = useMutation({
    mutationFn: (payload: UpdateUserPayload) =>
      apiFetch<{ id: string; changes: Record<string, { from: unknown; to: unknown }> }>(
        `/api/admin/users/${userId}`,
        {
          method: "PATCH",
          body: JSON.stringify(payload),
        },
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin-user-detail", userId] });
      queryClient.invalidateQueries({ queryKey: ["admin-users"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard-kpis"] });
    },
  });

  const u = detailQuery.data;
  const isSelf = me?.id === userId;

  return (
    <Drawer
      open={!!userId}
      onClose={onClose}
      title={u?.nickname || "用户详情"}
      sub={userId ?? undefined}
    >
      {detailQuery.isPending && (
        <div className="dim" style={{ padding: 24 }}>加载中…</div>
      )}
      {detailQuery.isError && (
        <div style={{ padding: 24, color: "var(--danger)" }}>
          加载失败：{(detailQuery.error as Error).message}
        </div>
      )}
      {u && (
        <>
          <section className="drawer-section">
            <div className="drawer-section-label">基本信息</div>
            <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 12 }}>
              <span
                className="av-inline"
                style={{
                  background: colorFromString(u.id),
                  width: 44,
                  height: 44,
                  fontSize: 16,
                }}
              >
                {initials(u.nickname || u.id)}
              </span>
              <div style={{ minWidth: 0 }}>
                <div style={{ fontSize: 14, fontWeight: 600 }}>
                  {u.nickname || <span className="dim-2">未设置昵称</span>}
                </div>
                <div className="mono dim" style={{ fontSize: 11, marginTop: 2 }}>
                  {u.id}
                </div>
              </div>
            </div>
            <Row label="注册时间" value={u.created_at ? fmtDateTime(u.created_at) : "—"} />
            <Row label="最近登录" value={u.last_login_at ? fmtDateTime(u.last_login_at) : "—"} />
          </section>

          <UserCreditsSection userId={userId} />

          <section className="drawer-section">
            <div className="drawer-section-label">登录方式</div>
            {u.identities.length === 0 ? (
              <div className="dim-2">无登录身份</div>
            ) : (
              u.identities.map((ident, i) => (
                <div
                  key={i}
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "baseline",
                    padding: "6px 0",
                    fontSize: 12.5,
                    borderBottom:
                      i < u.identities.length - 1
                        ? "1px solid var(--divider)"
                        : "none",
                  }}
                >
                  <span className="mono dim">{ident.provider}</span>
                  <span>{ident.email || ident.phone || "—"}</span>
                </div>
              ))
            )}
          </section>

          <section className="drawer-section">
            <div className="drawer-section-label">权限</div>
            {isSelf && (
              <div
                className="dim"
                style={{ fontSize: 11, marginBottom: 10, padding: "6px 10px", background: "var(--bg-subtle)", borderRadius: 6 }}
              >
                ⚠ 这是你自己 — 不能撤销自己的 admin 或封禁自己
              </div>
            )}
            <PermRow
              label="is_admin"
              hint="admin.inkwild.app 访问权限"
              value={u.is_admin}
              disabled={isSelf && u.is_admin}
              onChange={(v) => patch.mutate({ is_admin: v })}
              loading={patch.isPending}
            />
            <PermRow
              label="can_create"
              hint="允许创作世界/剧本（白名单制，默认关）"
              value={u.can_create}
              onChange={(v) => patch.mutate({ can_create: v })}
              loading={patch.isPending}
            />
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                padding: "10px 0",
                fontSize: 12.5,
              }}
            >
              <div>
                <div style={{ fontWeight: 500 }}>status</div>
                <div className="dim" style={{ fontSize: 11, marginTop: 1 }}>
                  banned 不会主动踢离线，但会阻挡新请求
                </div>
              </div>
              <Segmented<UserStatus>
                value={u.status === "banned" ? "banned" : "active"}
                options={[
                  { value: "active", label: "active" },
                  { value: "banned", label: "banned" },
                ]}
                onChange={(v) => {
                  if (isSelf && v === "banned") return;
                  patch.mutate({ status: v });
                }}
              />
            </div>
            {patch.isError && (
              <div className="field-error" style={{ marginTop: 6 }}>
                {(patch.error as Error).message}
              </div>
            )}
          </section>

          <section className="drawer-section">
            <div className="drawer-section-label">创作统计</div>
            <Row label="草稿" value={`${u.drafts_count}`} />
            <Row label="已发布世界" value={`${u.published_worlds_count}`} />
            <Row label="已发布剧本" value={`${u.published_scripts_count}`} />
            <Row label="累计 LLM 消耗" value={fmtCentsTotal(u.lifetime_cost_cents)} />
          </section>

          <section className="drawer-section">
            <div className="drawer-section-label">最近 session</div>
            {u.recent_sessions.length === 0 ? (
              <div className="dim-2">无 session</div>
            ) : (
              u.recent_sessions.map((s) => (
                <div
                  key={s.id}
                  style={{
                    padding: "8px 0",
                    fontSize: 12.5,
                    borderBottom: "1px solid var(--divider)",
                  }}
                >
                  <div className="spread" style={{ marginBottom: 2 }}>
                    <span style={{ fontWeight: 500 }}>{s.world_name || "—"}</span>
                    <span className="tabular" style={{ fontWeight: 500 }}>
                      {fmtCentsTotal(s.cost_cents)}
                    </span>
                  </div>
                  <div className="spread dim" style={{ fontSize: 11 }}>
                    <span>{s.rounds_played} 回合 · {s.status}</span>
                    <span>{s.last_played_at ? fmtDateTime(s.last_played_at) : "—"}</span>
                  </div>
                </div>
              ))
            )}
          </section>

          <section className="drawer-section" style={{ marginBottom: 0 }}>
            <Link href={`/audit?admin_user_id=${u.id}`}>
              <Btn variant="ghost" size="sm" icon={ClipboardList}>
                查看此用户的审计日志
              </Btn>
            </Link>
          </section>
        </>
      )}
    </Drawer>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div
      style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "baseline",
        padding: "5px 0",
        fontSize: 12.5,
      }}
    >
      <span className="dim">{label}</span>
      <span style={{ fontWeight: 500 }}>{value}</span>
    </div>
  );
}

function PermRow({
  label,
  hint,
  value,
  onChange,
  disabled,
  loading,
}: {
  label: string;
  hint: string;
  value: boolean;
  onChange: (v: boolean) => void;
  disabled?: boolean;
  loading?: boolean;
}) {
  return (
    <div
      style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        padding: "10px 0",
        fontSize: 12.5,
      }}
    >
      <div>
        <div style={{ fontWeight: 500 }}>{label}</div>
        <div className="dim" style={{ fontSize: 11, marginTop: 1 }}>
          {hint}
        </div>
      </div>
      <Toggle
        value={value}
        onChange={onChange}
        disabled={disabled || loading}
        ariaLabel={label}
      />
    </div>
  );
}
