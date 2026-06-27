"use client";

import { FeedbackThread } from "@/components/feedback/FeedbackThread";
import { Markdown } from "@/components/ui/Markdown";
import { parseBackendIso } from "@/lib/datetime";
import type { AnnouncementItem, NotificationItem } from "@/lib/notifications";

export type DetailItem =
  | { kind: "notification"; data: NotificationItem }
  | { kind: "announcement"; data: AnnouncementItem };

const LEVEL_TAG: Record<string, { label: string; color: string } | null> = {
  info: null,
  warning: { label: "提醒", color: "var(--lv-warn)" },
  critical: { label: "重要", color: "var(--lv-danger)" },
};

function fullTime(iso: string | null): string {
  if (!iso) return "";
  return parseBackendIso(iso).toLocaleString();
}

/** 通知 / 公告详情正文。容器（桌面 Modal · 移动面板内）各自包裹。 */
export function NotificationDetailView({
  item,
  onNavigate,
  goLabel,
}: {
  item: DetailItem;
  onNavigate: (link: string) => void;
  goLabel: string;
}) {
  const isAnn = item.kind === "announcement";
  const title = item.data.title;
  const body = item.data.body ?? "";
  const time = isAnn ? item.data.published_at : item.data.created_at;
  const image = isAnn ? item.data.image_url : null;
  const level = isAnn ? item.data.level : "info";
  const link = item.kind === "notification" ? item.data.link : null;
  const tag = LEVEL_TAG[level] ?? null;
  // 反馈进度通知：渲染线程时间线（解决记录全貌），而非单条文本快照
  const feedbackId =
    item.kind === "notification" && item.data.type === "feedback_update"
      ? (item.data.payload?.feedback_id as string | undefined) ?? null
      : null;

  return (
    <div className="lv-notif-detail">
      <header className="lv-notif-detail-head">
        <div className="lv-notif-detail-meta">
          <span className="lv-notif-detail-time">{fullTime(time)}</span>
          {tag && (
            <span className="lv-notif-detail-tag" style={{ color: tag.color, borderColor: tag.color }}>
              {tag.label}
            </span>
          )}
        </div>
        <h2 className="lv-notif-detail-title">{title}</h2>
      </header>

      {feedbackId ? (
        <div className="lv-notif-detail-body">
          <FeedbackThread feedbackId={feedbackId} />
        </div>
      ) : (
        <>
          {image && (
            // eslint-disable-next-line @next/next/no-img-element
            <img className="lv-notif-detail-img" src={image} alt="" />
          )}
          <div className="lv-notif-detail-body">
            {isAnn ? <Markdown>{body}</Markdown> : <p className="lv-notif-detail-text">{body}</p>}
          </div>
        </>
      )}

      {link && (
        <div className="lv-notif-detail-foot">
          <button type="button" className="lv-btn lv-btn-primary" onClick={() => onNavigate(link)}>
            {goLabel}
          </button>
        </div>
      )}

      <style jsx global>{`
        .lv-notif-detail { display: flex; flex-direction: column; }
        .lv-notif-detail-head { display: flex; flex-direction: column; gap: 7px; }
        .lv-notif-detail-meta { display: flex; align-items: center; gap: 10px; }
        .lv-notif-detail-time { color: var(--lv-ink-3); font-size: 12px; font-variant-numeric: tabular-nums; letter-spacing: 0.02em; }
        .lv-notif-detail-tag {
          display: inline-flex; align-items: center; height: 19px; padding: 0 8px;
          border: 1px solid currentColor; border-radius: var(--lv-r-pill);
          font-size: 11px; font-weight: 600; letter-spacing: 0.04em;
        }
        .lv-notif-detail-title {
          margin: 0; color: var(--lv-ink); font-family: var(--lv-font-serif);
          font-size: 23px; font-weight: 500; line-height: 1.28; letter-spacing: 0.01em;
        }
        .lv-notif-detail-img {
          width: 100%; max-height: 220px; object-fit: cover; display: block;
          border-radius: var(--lv-r-card); margin-top: 16px; border: 1px solid var(--lv-line);
        }
        .lv-notif-detail-body { margin-top: 16px; }
        .lv-notif-detail-text { margin: 0; color: var(--lv-ink-2); font-size: 14px; line-height: 1.8; white-space: pre-wrap; }
        .lv-notif-detail-foot { margin-top: 22px; }
      `}</style>
    </div>
  );
}
