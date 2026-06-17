"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { Bell } from "lucide-react";
import { useTranslations } from "next-intl";

import { NotificationPanel } from "@/components/notifications/NotificationPanel";
import { NotificationDetailView, type DetailItem } from "@/components/notifications/NotificationDetailView";
import { Drawer } from "@/components/ui/Drawer";
import { Modal } from "@/components/ui/Modal";
import { useIsMobile } from "@/lib/use-viewport";
import {
  ANN_LIST_KEY,
  NOTIF_LIST_KEY,
  NOTIF_SUMMARY_KEY,
  badgeText,
  totalUnread,
  useNotificationSummary,
} from "@/lib/notifications";
import { useAuthStore } from "@/stores/auth";

export function NotificationBell() {
  const t = useTranslations("notifications");
  const router = useRouter();
  const user = useAuthStore((s) => s.user);
  const isMobile = useIsMobile();
  const [open, setOpen] = useState(false);
  const [detail, setDetail] = useState<DetailItem | null>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const qc = useQueryClient();

  // 每次打开铃铛都拉最新（移动端 Drawer 常驻挂载，靠这个而非 remount 刷新）
  useEffect(() => {
    if (!open) return;
    qc.invalidateQueries({ queryKey: NOTIF_SUMMARY_KEY });
    qc.invalidateQueries({ queryKey: NOTIF_LIST_KEY });
    qc.invalidateQueries({ queryKey: ANN_LIST_KEY });
  }, [open, qc]);

  const { data: summary } = useNotificationSummary(!!user);
  const unread = totalUnread(summary);

  // 桌面下拉：点击外部 / Esc 关闭
  useEffect(() => {
    if (!open || isMobile) return;
    const onDown = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open, isMobile]);

  if (!user) return null;

  const navigate = (link: string) => {
    setOpen(false);
    setDetail(null);
    router.push(link);
  };

  // 桌面：点列表项 → 关下拉、开独立弹窗（弹窗状态在 bell 这层，不随下拉卸载而消失）
  const openDetail = (item: DetailItem) => {
    setOpen(false);
    setDetail(item);
  };

  const trigger = (
    <button
      type="button"
      className="lv-notif-bell"
      aria-label={t("ariaLabel")}
      aria-haspopup="dialog"
      aria-expanded={open}
      data-open={open ? "true" : "false"}
      data-unread={unread > 0 ? "true" : "false"}
      onClick={() => setOpen((v) => !v)}
    >
      <Bell size={18} strokeWidth={1.75} />
      {unread > 0 && <span className="lv-notif-badge">{badgeText(unread)}</span>}
    </button>
  );

  return (
    <div ref={wrapRef} className="lv-notif-bell-wrap">
      {trigger}

      {!isMobile && open && (
        <div className="lv-notif-pop" role="dialog" aria-label={t("ariaLabel")}>
          <NotificationPanel summary={summary} onNavigate={navigate} onOpenDetail={openDetail} />
        </div>
      )}

      {isMobile && (
        <Drawer open={open} onClose={() => setOpen(false)} title={t("ariaLabel")}>
          <NotificationPanel summary={summary} onNavigate={navigate} isMobile />
        </Drawer>
      )}

      {/* 桌面详情：独立弹窗，脱离会自动关闭的下拉层 */}
      {!isMobile && (
        <Modal open={detail !== null} onClose={() => setDetail(null)} maxWidth={560}>
          {detail && (
            <div className="lv-notif-detail-shell">
              <NotificationDetailView item={detail} onNavigate={navigate} goLabel={t("goToLink")} />
            </div>
          )}
        </Modal>
      )}

      <style jsx global>{`
        .lv-notif-bell-wrap { position: relative; display: inline-flex; }
        .lv-notif-bell {
          position: relative; display: inline-flex; align-items: center; justify-content: center;
          width: 38px; height: 38px; border-radius: var(--lv-r-pill);
          background: rgba(255, 255, 255, 0.055);
          border: 1px solid rgba(255, 255, 255, 0.11);
          color: var(--lv-ink);
          cursor: pointer;
          transition:
            color 180ms var(--lv-ease),
            background 180ms var(--lv-ease),
            border-color 180ms var(--lv-ease),
            box-shadow 180ms var(--lv-ease),
            transform 180ms var(--lv-ease);
        }
        .lv-notif-bell:hover,
        .lv-notif-bell[data-open="true"] {
          color: var(--lv-ink);
          background: rgba(255, 255, 255, 0.1);
          border-color: rgba(255, 255, 255, 0.2);
        }
        .lv-notif-bell:hover { transform: translateY(-1px); }
        .lv-notif-badge {
          position: absolute; top: -3px; right: -3px;
          min-width: 16px; height: 16px; padding: 0 4.5px;
          display: inline-flex; align-items: center; justify-content: center;
          border-radius: 999px;
          background: var(--lv-badge); color: #fff;
          font-family: var(--lv-font-sans);
          font-size: 10.5px; font-weight: 600; line-height: 1; letter-spacing: 0;
          font-variant-numeric: tabular-nums;
        }
        .lv-notif-pop {
          position: absolute; top: calc(100% + 10px); right: 0; width: 410px; max-width: calc(100vw - 24px);
          background: rgba(24, 24, 28, 0.97);
          border: 1px solid rgba(255, 255, 255, 0.15);
          border-radius: var(--lv-r-card);
          box-shadow: 0 24px 72px -18px rgba(0, 0, 0, 0.74), inset 0 1px 0 rgba(255,255,255,0.07);
          backdrop-filter: blur(22px) saturate(135%);
          -webkit-backdrop-filter: blur(22px) saturate(135%);
          overflow: hidden;
          z-index: var(--lv-z-modal);
        }
        .lv-notif-detail-shell {
          max-height: min(62dvh, 540px);
          overflow-y: auto;
          overscroll-behavior: contain;
          margin: -2px;
          padding: 2px;
        }
        .lv-notif-pop::before {
          content: "";
          position: absolute;
          inset: 0 0 auto;
          height: 120px;
          background: radial-gradient(ellipse 78% 120% at 52% -26%, rgba(245, 242, 235, 0.08), transparent 68%);
          pointer-events: none;
        }
      `}</style>
    </div>
  );
}
