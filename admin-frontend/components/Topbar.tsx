"use client";

import { Bell, ChevronRight, HelpCircle, Search } from "lucide-react";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { crumbsFromPath } from "@/lib/nav";

type Currency = "cny" | "usd";

export function Topbar() {
  const pathname = usePathname() || "/";
  const crumbs = crumbsFromPath(pathname);
  const [currency, setCurrency] = useState<Currency>("cny");

  // Read persisted currency once on mount
  useEffect(() => {
    try {
      const v = localStorage.getItem("admin.currency");
      if (v === "cny" || v === "usd") setCurrency(v);
    } catch {
      /* localStorage 不可用，忽略 */
    }
  }, []);

  const onCurrency = (c: Currency) => {
    setCurrency(c);
    try {
      localStorage.setItem("admin.currency", c);
    } catch {
      /* localStorage 不可用，忽略 */
    }
  };

  return (
    <div className="topbar">
      <div className="topbar-crumb">
        {crumbs.map((c, i) => (
          <span key={i} style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
            {i > 0 && (
              <span className="topbar-sep">
                <ChevronRight size={11} />
              </span>
            )}
            {i === crumbs.length - 1 ? <b>{c}</b> : <span>{c}</span>}
          </span>
        ))}
      </div>
      <div className="topbar-spacer" />
      <div className="ccy-switch" title="切换显示币种">
        <button
          data-active={currency === "cny" || undefined}
          onClick={() => onCurrency("cny")}
        >
          ¥ CNY
        </button>
        <button
          data-active={currency === "usd" || undefined}
          onClick={() => onCurrency("usd")}
        >
          $ USD
        </button>
      </div>
      <div className="topbar-search">
        <Search size={13} />
        <span>跳转到模型、用户、世界…</span>
        <kbd>⌘K</kbd>
      </div>
      <button className="topbar-ibtn" title="帮助">
        <HelpCircle size={15} />
      </button>
      <button className="topbar-ibtn" title="通知">
        <Bell size={15} />
        <span className="topbar-ibtn-dot" />
      </button>
    </div>
  );
}
