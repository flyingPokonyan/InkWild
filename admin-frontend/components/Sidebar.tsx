"use client";

import { ChevronDown, ChevronLeft, ChevronRight, MoreHorizontal } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { useMe } from "@/lib/auth";
import { NAV, activeIdFromPath } from "@/lib/nav";

interface Props {
  collapsed: boolean;
  onToggleCollapsed: () => void;
}

export function Sidebar({ collapsed, onToggleCollapsed }: Props) {
  const pathname = usePathname() || "/";
  const activeId = activeIdFromPath(pathname);
  const { data: me } = useMe();

  const initials = (me?.nickname || "?").slice(0, 2).toUpperCase();

  return (
    <aside className="sb">
      <div className="sb-brand">
        <div className="sb-logo">T</div>
        <div className="sb-brand-text">
          <div className="sb-brand-name">InkWild</div>
          <div className="sb-brand-sub">Admin Console</div>
        </div>
        <button
          className="sb-collapse-btn"
          onClick={onToggleCollapsed}
          title={collapsed ? "展开侧栏" : "折叠侧栏"}
        >
          {collapsed ? <ChevronRight size={12} /> : <ChevronLeft size={12} />}
        </button>
      </div>

      <div className="sb-env" title="切换环境">
        <span className="sb-env-dot" />
        <span className="sb-env-label">环境</span>
        <span className="sb-env-name">
          {process.env.NODE_ENV === "production" ? "production" : "dev"}
        </span>
        <span className="sb-env-caret">
          <ChevronDown size={10} />
        </span>
      </div>

      {NAV.map((sec) => (
        <div key={sec.label} className="sb-section">
          <div className="sb-section-label">{sec.label}</div>
          <div className="sb-nav">
            {sec.items.map((item) => {
              const Icon = item.icon;
              const isActive = item.id === activeId;
              const content = (
                <>
                  <span className="sb-item-ico">
                    <Icon size={15} />
                  </span>
                  <span className="sb-item-text">{item.label}</span>
                  {item.tag && <span className="sb-item-tag">{item.tag}</span>}
                </>
              );

              if (item.disabled || !item.href) {
                return (
                  <button
                    key={item.id}
                    className="sb-item"
                    data-disabled
                    title={collapsed ? item.label : undefined}
                    type="button"
                  >
                    {content}
                  </button>
                );
              }

              return (
                <Link
                  key={item.id}
                  className="sb-item"
                  data-active={isActive || undefined}
                  href={item.href}
                  title={collapsed ? item.label : undefined}
                >
                  {content}
                </Link>
              );
            })}
          </div>
        </div>
      ))}

      <div className="sb-footer">
        <div className="sb-avatar">{initials}</div>
        <div className="sb-user">
          <div className="sb-user-name">{me?.nickname || "—"}</div>
          <div className="sb-user-role">Super Admin</div>
        </div>
        <div className="sb-user-menu">
          <MoreHorizontal size={14} />
        </div>
      </div>
    </aside>
  );
}
