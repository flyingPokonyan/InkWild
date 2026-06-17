"use client";

import { Bug, Lightbulb } from "lucide-react";

import { parseBackendIso } from "@/lib/datetime";
import { useFeedbackThread, type FeedbackEvent } from "@/lib/feedback";

const STATUS_LABEL: Record<string, string> = { new: "待处理", triaged: "处理中", resolved: "已解决" };
const STATUS_COLOR: Record<string, string> = {
  new: "var(--lv-warn)",
  triaged: "var(--lv-accent-2)",
  resolved: "var(--lv-success)",
};
const CATEGORY_LABEL: Record<string, string> = { bug: "问题反馈", suggestion: "优化建议" };

function fmt(iso: string): string {
  return parseBackendIso(iso).toLocaleString();
}

type Row =
  | { kind: "submission"; content: string; image: string | null; time: string }
  | { kind: "status"; status: string; time: string }
  | { kind: "reply"; body: string; time: string };

/** 反馈线程：你的提交 + 管理员回复用卡片，状态变更用细分隔线。倒序（最新在上）。 */
export function FeedbackThread({ feedbackId }: { feedbackId: string }) {
  const { data, isLoading, isError } = useFeedbackThread(feedbackId);

  if (isLoading) return <div className="fbt-state">加载中…</div>;
  if (isError || !data) return <div className="fbt-state">无法加载反馈详情</div>;

  const CatIcon = data.category === "suggestion" ? Lightbulb : Bug;

  // 时间正序拼装，再整体倒序展示（最新在上、提交在底）
  const rows: Row[] = [
    { kind: "submission", content: data.content, image: data.image_url, time: data.created_at },
    ...data.events.map((e: FeedbackEvent): Row =>
      e.kind === "status"
        ? { kind: "status", status: e.status ?? "", time: e.created_at }
        : { kind: "reply", body: e.body ?? "", time: e.created_at },
    ),
  ];
  rows.reverse();

  return (
    <div className="fbt">
      <div className="fbt-head">
        <span className="fbt-cat"><CatIcon size={13} strokeWidth={1.9} />{CATEGORY_LABEL[data.category] ?? data.category}</span>
        <span className="fbt-status" style={{ color: STATUS_COLOR[data.status], borderColor: STATUS_COLOR[data.status] }}>
          {STATUS_LABEL[data.status] ?? data.status}
        </span>
      </div>

      <div className="fbt-rows">
        {rows.map((r, i) => {
          if (r.kind === "status") {
            return (
              <div key={i} className="fbt-div">
                <span className="fbt-div-dot" style={{ background: STATUS_COLOR[r.status] }} />
                状态更新为「{STATUS_LABEL[r.status] ?? r.status}」
                <time>{fmt(r.time)}</time>
              </div>
            );
          }
          const mine = r.kind === "submission";
          return (
            <div key={i} className={`fbt-card${mine ? " fbt-card--mine" : ""}`}>
              <div className="fbt-card-head">
                <b>{mine ? "你的反馈" : "管理员回复"}</b>
                <time>{fmt(r.time)}</time>
              </div>
              <p className="fbt-card-body">{mine ? r.content : r.body}</p>
              {mine && r.image && (
                // eslint-disable-next-line @next/next/no-img-element
                <img className="fbt-card-img" src={r.image} alt="" />
              )}
            </div>
          );
        })}
      </div>

      <style jsx global>{`
        .fbt-state { padding: 28px 8px; text-align: center; color: var(--lv-ink-4); font-size: 13px; }
        .fbt { display: flex; flex-direction: column; }
        .fbt-head { display: flex; align-items: center; gap: 10px; margin-bottom: 16px; }
        .fbt-cat { display: inline-flex; align-items: center; gap: 6px; color: var(--lv-ink-2); font-size: 13px; }
        .fbt-status { display: inline-flex; align-items: center; height: 20px; padding: 0 9px; border: 1px solid currentColor; border-radius: var(--lv-r-pill); font-size: 11px; font-weight: 600; }
        .fbt-rows { display: flex; flex-direction: column; gap: 10px; }
        .fbt-div { display: flex; align-items: center; gap: 8px; padding: 2px 2px; color: var(--lv-ink-3); font-size: 12px; }
        .fbt-div-dot { width: 6px; height: 6px; border-radius: 50%; flex: 0 0 auto; }
        .fbt-div time { margin-left: auto; color: var(--lv-ink-4); font-size: 11px; }
        .fbt-card { border: 1px solid var(--lv-line); border-radius: var(--lv-r-card); padding: 11px 13px; background: rgba(174,180,184,0.05); }
        .fbt-card--mine { background: rgba(255,255,255,0.02); }
        .fbt-card-head { display: flex; align-items: baseline; justify-content: space-between; gap: 10px; margin-bottom: 5px; }
        .fbt-card-head b { color: var(--lv-ink); font-size: 12.5px; font-weight: 600; }
        .fbt-card-head time { color: var(--lv-ink-4); font-size: 11px; white-space: nowrap; }
        .fbt-card-body { margin: 0; color: var(--lv-ink-2); font-size: 13.5px; line-height: 1.7; white-space: pre-wrap; }
        .fbt-card-img { width: 100%; max-height: 160px; object-fit: cover; border-radius: var(--lv-r-input); margin-top: 8px; }
      `}</style>
    </div>
  );
}
