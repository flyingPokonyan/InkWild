"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import {
  ArrowLeft,
  BadgeCheck,
  Bell,
  Coins,
  Gift,
  Megaphone,
  MessageSquare,
  ShieldAlert,
  ShieldCheck,
  XCircle,
} from "lucide-react";

import { parseBackendIso } from "@/lib/datetime";
import {
  useAnnouncements,
  useMarkRead,
  useNotifications,
  type AnnouncementItem,
  type AnnouncementLevel,
  type NotificationItem,
  type NotificationSummary,
  type NotificationType,
} from "@/lib/notifications";

import { NotificationDetailView, type DetailItem } from "./NotificationDetailView";

type Tab = "notifications" | "announcements";

const TYPE_ICON: Record<string, typeof Bell> = {
  signup_grant: Gift,
  review_approved: BadgeCheck,
  review_rejected: XCircle,
  content_takedown: ShieldAlert,
  content_restored: ShieldCheck,
  low_credit: Coins,
  feedback_new: MessageSquare,
  feedback_update: MessageSquare,
};

const LEVEL_COLOR: Record<string, string> = {
  info: "var(--lv-accent-2)",
  warning: "#d8a24a",
  critical: "#d66a5a",
};

function relativeTime(iso: string | null): string {
  if (!iso) return "";
  const then = parseBackendIso(iso).getTime();
  const diff = Date.now() - then;
  const min = Math.floor(diff / 60000);
  if (min < 1) return "刚刚";
  if (min < 60) return `${min} 分钟前`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr} 小时前`;
  const day = Math.floor(hr / 24);
  if (day < 30) return `${day} 天前`;
  return parseBackendIso(iso).toLocaleDateString();
}

function iconFor(type: NotificationType) {
  return TYPE_ICON[type] ?? Bell;
}

export function NotificationPanel({
  summary,
  onNavigate,
  isMobile = false,
  onOpenDetail,
}: {
  summary: NotificationSummary | undefined;
  onNavigate: (link: string) => void;
  /** 移动端：详情就地在面板内展开；桌面：详情用独立弹窗 */
  isMobile?: boolean;
  /** 桌面：把详情上抛给 NotificationBell 渲染独立弹窗（脱离会自动关闭的下拉层） */
  onOpenDetail?: (item: DetailItem) => void;
}) {
  const t = useTranslations("notifications");
  const [tab, setTab] = useState<Tab>("notifications");
  const [detail, setDetail] = useState<DetailItem | null>(null);
  const mark = useMarkRead();

  const notifQuery = useNotifications(true);
  const annQuery = useAnnouncements(tab === "announcements");

  const notifItems = notifQuery.data?.pages.flatMap((p) => p.items) ?? [];
  const annItems = annQuery.data?.pages.flatMap((p) => p.items) ?? [];

  const unreadN = summary?.notifications ?? 0;
  const unreadA = summary?.announcements ?? 0;
  const unreadTotal = unreadN + unreadA;

  function handleNotificationClick(item: NotificationItem) {
    if (!item.read_at) mark.notification.mutate(item.id);
    const d: DetailItem = { kind: "notification", data: item };
    if (onOpenDetail) onOpenDetail(d);
    else setDetail(d);
  }

  function handleAnnouncementClick(item: AnnouncementItem) {
    if (!item.read) mark.announcement.mutate(item.id);
    const d: DetailItem = { kind: "announcement", data: item };
    if (onOpenDetail) onOpenDetail(d);
    else setDetail(d);
  }

  function handleGo(link: string) {
    setDetail(null);
    onNavigate(link);
  }

  const active = tab === "notifications";
  const items = active ? notifItems : annItems;
  const query = active ? notifQuery : annQuery;
  const isEmpty = !query.isLoading && items.length === 0;

  // 移动端：详情就地替换面板内容
  if (isMobile && detail) {
    return (
      <div className="lv-notif-panel">
        <div className="lv-notif-detail-bar-head">
          <button type="button" className="lv-notif-back" onClick={() => setDetail(null)}>
            <ArrowLeft size={16} strokeWidth={1.9} />
            {t("back")}
          </button>
        </div>
        <div className="lv-notif-detail-scroll">
          <NotificationDetailView item={detail} onNavigate={handleGo} goLabel={t("goToLink")} />
        </div>
        <style jsx global>{`
          .lv-notif-detail-bar-head { padding: 14px 14px 6px; }
          .lv-notif-back { display: inline-flex; align-items: center; gap: 6px; background: none; border: none; color: var(--lv-ink-3); font-size: 13px; cursor: pointer; padding: 4px 2px; }
          .lv-notif-back:hover { color: var(--lv-ink); }
          .lv-notif-detail-scroll { overflow-y: auto; padding: 6px 16px 20px; -webkit-overflow-scrolling: touch; }
        `}</style>
      </div>
    );
  }

  return (
    <div className="lv-notif-panel">
      <div className="lv-notif-head">
        <div>
          <h2>{t("panelTitle")}</h2>
          <p>{unreadTotal > 0 ? t("unreadSummary", { count: unreadTotal }) : t("allRead")}</p>
        </div>
        <span className="lv-notif-head-mark" aria-hidden>
          <Bell size={16} strokeWidth={1.7} />
        </span>
      </div>

      {/* tabs */}
      <div className="lv-notif-tabs">
        <TabButton label={t("tabNotifications")} count={unreadN} active={tab === "notifications"} onClick={() => setTab("notifications")} />
        <TabButton label={t("tabAnnouncements")} count={unreadA} active={tab === "announcements"} onClick={() => setTab("announcements")} />
        <button
          type="button"
          className="lv-notif-readall"
          disabled={(active ? unreadN : unreadA) === 0}
          onClick={() => (active ? mark.notificationsAll.mutate() : mark.announcementsAll.mutate())}
        >
          {t("markAllRead")}
        </button>
      </div>

      {/* list */}
      <div className="lv-notif-list">
        {isEmpty ? (
          <div className="lv-notif-empty">
            <Megaphone size={20} strokeWidth={1.5} />
            <span>{active ? t("empty") : t("emptyAnnouncements")}</span>
          </div>
        ) : active ? (
          notifItems.map((item) => {
            const Icon = iconFor(item.type);
            return (
              <button key={item.id} type="button" className="lv-notif-row" onClick={() => handleNotificationClick(item)}>
                {!item.read_at && <span className="lv-notif-dot" />}
                <span className="lv-notif-icon"><Icon size={15} strokeWidth={1.75} /></span>
                <span className="lv-notif-body">
                  <span className="lv-notif-title" data-unread={!item.read_at}>{item.title}</span>
                  {item.body && <span className="lv-notif-sub">{item.body}</span>}
                  <span className="lv-notif-time">{relativeTime(item.created_at)}</span>
                </span>
              </button>
            );
          })
        ) : (
          annItems.map((item) => (
            <button key={item.id} type="button" className="lv-notif-row" onClick={() => handleAnnouncementClick(item)}>
              {!item.read && <span className="lv-notif-dot" />}
              <span className="lv-notif-bar" style={{ background: LEVEL_COLOR[item.level as AnnouncementLevel] ?? LEVEL_COLOR.info }} />
              <span className="lv-notif-body">
                <span className="lv-notif-title" data-unread={!item.read}>{item.title}</span>
                <span className="lv-notif-sub lv-notif-sub-3">{item.body}</span>
                <span className="lv-notif-time">{relativeTime(item.published_at)}</span>
              </span>
            </button>
          ))
        )}

        {query.hasNextPage && (
          <button type="button" className="lv-notif-more" disabled={query.isFetchingNextPage} onClick={() => query.fetchNextPage()}>
            {query.isFetchingNextPage ? "…" : t("loadMore")}
          </button>
        )}
      </div>

      <style jsx global>{`
        .lv-notif-panel { position: relative; display: flex; flex-direction: column; max-height: min(72dvh, 520px); }
        .lv-notif-head {
          position: relative;
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 18px;
          padding: 18px 18px 14px;
        }
        .lv-notif-head h2 {
          margin: 0;
          color: var(--lv-ink);
          font-family: var(--lv-font-serif);
          font-size: 20px;
          font-weight: 500;
          line-height: 1.2;
          letter-spacing: 0.01em;
        }
        .lv-notif-head p {
          margin: 5px 0 0;
          color: var(--lv-ink-3);
          font-size: 12px;
          line-height: 1.5;
        }
        .lv-notif-head-mark {
          display: inline-grid;
          place-items: center;
          width: 34px;
          height: 34px;
          border-radius: var(--lv-r-pill);
          color: var(--lv-accent);
          background: rgba(223, 194, 144, 0.08);
          border: 1px solid rgba(223, 194, 144, 0.14);
        }
        .lv-notif-tabs { display: flex; align-items: center; gap: 4px; padding: 0 12px 10px; border-bottom: 1px solid rgba(255,255,255,0.11); }
        .lv-notif-tab { display: inline-flex; align-items: center; gap: 6px; height: 30px; padding: 0 10px; border-radius: var(--lv-r-pill); background: transparent; border: none; color: var(--lv-ink-2); font-size: 13px; font-weight: 600; cursor: pointer; transition: color 160ms ease, background 160ms ease; }
        .lv-notif-tab[data-active="true"] { color: var(--lv-ink); background: rgba(255,255,255,0.1); }
        .lv-notif-tab:hover { color: var(--lv-ink); }
        .lv-notif-tab-count { min-width: 16px; height: 16px; padding: 0 5px; border-radius: 999px; background: var(--lv-badge); color: #fff; font-size: 10.5px; font-weight: 600; display: inline-flex; align-items: center; justify-content: center; font-variant-numeric: tabular-nums; }
        .lv-notif-readall { margin-left: auto; background: none; border: none; color: var(--lv-ink-4); font-size: 12px; cursor: pointer; padding: 4px 6px; }
        .lv-notif-readall:hover { color: var(--lv-accent); }
        .lv-notif-readall:disabled { opacity: 0.36; cursor: default; }
        .lv-notif-readall:disabled:hover { color: var(--lv-ink-4); }
        .lv-notif-list { overflow-y: auto; padding: 6px; -webkit-overflow-scrolling: touch; }
        .lv-notif-row { position: relative; display: flex; gap: 11px; width: 100%; text-align: left; padding: 12px 12px 12px 15px; background: rgba(255,255,255,0.025); border: 1px solid transparent; border-radius: var(--lv-r-input); cursor: pointer; transition: background 140ms ease, border-color 140ms ease; }
        .lv-notif-row + .lv-notif-row { margin-top: 4px; }
        .lv-notif-row:hover { background: rgba(255,255,255,0.08); border-color: rgba(255,255,255,0.1); }
        .lv-notif-dot { position: absolute; left: 5px; top: 16px; width: 6px; height: 6px; border-radius: 50%; background: var(--lv-accent); }
        .lv-notif-icon {
          flex: 0 0 auto;
          display: inline-grid;
          place-items: center;
          width: 26px;
          height: 26px;
          border-radius: 8px;
          color: var(--lv-ink-2);
          background: rgba(255,255,255,0.07);
          margin-top: 1px;
        }
        .lv-notif-bar { flex: 0 0 auto; width: 3px; border-radius: 2px; align-self: stretch; }
        .lv-notif-body { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
        .lv-notif-title { color: var(--lv-ink); font-size: 13.5px; font-weight: 500; line-height: 1.4; }
        .lv-notif-title[data-unread="true"] { color: var(--lv-ink); font-weight: 600; }
        .lv-notif-sub { color: var(--lv-ink-3); font-size: 12px; line-height: 1.5; overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
        .lv-notif-sub-3 { -webkit-line-clamp: 3; }
        .lv-notif-time { color: var(--lv-ink-4); font-size: 11px; margin-top: 1px; }
        .lv-notif-empty { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 10px; padding: 44px 16px; color: var(--lv-ink-4); font-size: 13px; }
        .lv-notif-more { width: 100%; padding: 10px; background: none; border: none; color: var(--lv-ink-4); font-size: 12px; cursor: pointer; }
        .lv-notif-more:hover { color: var(--lv-accent); }
      `}</style>
    </div>
  );
}

function TabButton({ label, count, active, onClick }: { label: string; count: number; active: boolean; onClick: () => void }) {
  return (
    <button type="button" className="lv-notif-tab" data-active={active} onClick={onClick}>
      {label}
      {count > 0 && <span className="lv-notif-tab-count">{count > 99 ? "99+" : count}</span>}
    </button>
  );
}
