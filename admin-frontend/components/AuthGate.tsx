"use client";

import { useEffect } from "react";

import { useMe } from "@/lib/auth";

const MAIN_SITE =
  process.env.NEXT_PUBLIC_MAIN_SITE_URL || "http://localhost:3000";

export function AuthGate({ children }: { children: React.ReactNode }) {
  const { data, isPending, error } = useMe();

  useEffect(() => {
    if (isPending) return;
    if (error) return;
    if (data === null) {
      // Not logged in → main site login
      window.location.href = `${MAIN_SITE}/login?next=${encodeURIComponent(window.location.href)}`;
      return;
    }
    if (data && !data.is_admin) {
      // Logged in but not admin → main site home
      window.location.href = MAIN_SITE;
    }
  }, [data, isPending, error]);

  if (isPending) {
    return <div className="auth-loading">校验权限…</div>;
  }

  if (error) {
    return (
      <div className="auth-loading">
        无法连接到后端（{(error as Error).message}）
      </div>
    );
  }

  if (!data || !data.is_admin) {
    return <div className="auth-loading">跳转中…</div>;
  }

  return <>{children}</>;
}
