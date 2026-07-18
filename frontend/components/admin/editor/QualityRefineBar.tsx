"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  getWorldDraftDetail,
  refineWorldDraft,
  streamAdminEvents,
  undoWorldDraftRefine,
} from "@/lib/workshop-api";
import type { WorldDraftPayload } from "@/lib/types";

/** 可精修的语义质检 code（去掉 judge_ 前缀）→ 中文标签。只有这几类走 AI 精修；
 * 确定性检查（gender/地点引用等）和内容审核标记只展示、不精修。 */
const REFINABLE_LABELS: Record<string, string> = {
  timeline_coverage_gap: "时间线覆盖缺口",
  event_beat_duplication: "事件节拍重复",
  canon_fidelity: "与原著设定冲突",
  ai_smell: "角色/设定套路化",
};

/** 生成流程内部标记，不作为"问题"展示给用户 */
const HIDDEN_CODES = new Set(["events_revised"]);

type WarnItem = {
  code: string; // 去前缀
  label: string;
  detail: string;
  refinable: boolean;
};

type RefineChange = {
  kind: string;
  entity: string;
  field: string;
  before: string;
  after: string;
};

type RefineMeta = {
  changed: boolean;
  changes: RefineChange[];
  rechecked: { code: string; severity: string; detail: string }[];
};

type View = "warnings" | "refining" | "result";

interface Props {
  draftId: string;
  payload: WorldDraftPayload;
  /** 精修/撤销落库后，用服务端最新 payload 同步编辑器状态 */
  onRefined: (payload: WorldDraftPayload) => void;
  /** 精修进行中（含后台复检）置 true，让 shell 暂停 autosave、禁用保存/发布 */
  onBusyChange?: (busy: boolean) => void;
  /** 挂载时若已有在跑的精修任务 id（重进草稿页），自动重连其 SSE 流恢复进度 */
  initialRefineTaskId?: string | null;
}

function normCode(code: string): string {
  return code.replace(/^judge_/, "");
}

function parseWarnings(payload: WorldDraftPayload): WarnItem[] {
  const raw = (payload as { quality_warnings?: unknown[] }).quality_warnings;
  if (!Array.isArray(raw)) return [];
  const items: WarnItem[] = [];
  for (const w of raw) {
    // 内容审核标记（moderation_flag:* 纯字符串）不展示：用户无法处理（多为剧情暴力误伤），剔除。
    if (typeof w === "string") continue;
    if (!w || typeof w !== "object") continue;
    const obj = w as { code?: string; message?: string; detail?: string };
    const code = normCode(String(obj.code || ""));
    if (!code || HIDDEN_CODES.has(code)) continue;
    const refinable = code in REFINABLE_LABELS;
    items.push({
      code,
      label: refinable ? REFINABLE_LABELS[code] : "需人工修正",
      detail: String(obj.message || obj.detail || ""),
      refinable,
    });
  }
  return items;
}

export function QualityRefineBar({
  draftId,
  payload,
  onRefined,
  onBusyChange,
  initialRefineTaskId,
}: Props) {
  const [view, setView] = useState<View>("warnings");
  const [expanded, setExpanded] = useState(false);
  const [stage, setStage] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<RefineMeta | null>(null);
  // 复检退后台：completed 后 result 先出，复检仍在跑时为 true，recheck_done 落定为 false。
  const [rechecking, setRechecking] = useState(false);

  const warnings = useMemo(() => parseWarnings(payload), [payload]);
  const refinable = warnings.filter((w) => w.refinable);
  const manual = warnings.length - refinable.length;

  const syncDetail = useCallback(() => {
    getWorldDraftDetail(draftId)
      .then((d) => onRefined(d.payload))
      .catch(() => {});
  }, [draftId, onRefined]);

  // 连一条精修任务的 SSE 流并驱动 UI —— 既供新发起（runRefine）也供重进恢复（挂载 effect）复用。
  // afterSeq=0 会重放全部历史事件，重进时据此重建 completed/recheck_done 状态。
  const streamRefineTask = useCallback(
    async (taskId: string, afterSeq: number) => {
      setView("refining");
      onBusyChange?.(true);
      let errored = false;
      try {
        await streamAdminEvents(
          `/api/workshop/generation-tasks/${taskId}/stream?after_seq=${afterSeq}`,
          {
            onProgress: (e) => {
              if (e.message) setStage(e.message);
              // completed：主体改动已落库，先把结果给用户（复检还在后台跑）。
              if (e.code === "completed" && e.meta) {
                const meta = e.meta as unknown as RefineMeta;
                setResult(meta);
                setExpanded(true);
                setRechecking(Boolean(meta.changed));
                setView("result");
                syncDetail(); // 同步改动后的内容（此时 warnings 尚未刷新）
              }
              // recheck_done：复检落定，刷新复检结论 + quality_warnings。
              if (e.code === "recheck_done") {
                const rechecked =
                  (e.meta as { rechecked?: RefineMeta["rechecked"] } | undefined)?.rechecked ?? [];
                setResult((r) => (r ? { ...r, rechecked } : r));
                setRechecking(false);
                syncDetail();
              }
            },
            onError: (m) => {
              errored = true;
              setError(m);
            },
          },
        );
        if (errored) {
          setRechecking(false);
          // 已出结果就停在 result（错误只发生在复检段）；否则退回质检条。
          setView((v) => (v === "result" ? "result" : "warnings"));
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "精修失败");
        setRechecking(false);
        setView((v) => (v === "result" ? "result" : "warnings"));
      } finally {
        onBusyChange?.(false); // 锁到 done（含复检）才释放
      }
    },
    [onBusyChange, syncDetail],
  );

  const runRefine = useCallback(
    async (targets: string[]) => {
      setError(null);
      setStage("正在准备精修…");
      setView("refining");
      onBusyChange?.(true);
      let taskId: string;
      try {
        taskId = (await refineWorldDraft(draftId, targets)).task_id;
      } catch (err) {
        setError(err instanceof Error ? err.message : "精修失败");
        setView("warnings");
        onBusyChange?.(false);
        return;
      }
      await streamRefineTask(taskId, 0);
    },
    [draftId, onBusyChange, streamRefineTask],
  );

  // 重进草稿页时若已有在跑的精修任务，自动重连恢复（只连一次）。
  const reconnectedRef = useRef<string | null>(null);
  useEffect(() => {
    if (!initialRefineTaskId || reconnectedRef.current === initialRefineTaskId) return;
    reconnectedRef.current = initialRefineTaskId;
    setStage("正在恢复精修进度…");
    void streamRefineTask(initialRefineTaskId, 0);
  }, [initialRefineTaskId, streamRefineTask]);

  const runUndo = useCallback(async () => {
    setError(null);
    try {
      await undoWorldDraftRefine(draftId);
      const detail = await getWorldDraftDetail(draftId);
      onRefined(detail.payload);
      setResult(null);
      setRechecking(false);
      setView("warnings");
    } catch (err) {
      setError(err instanceof Error ? err.message : "撤销失败");
    }
  }, [draftId, onRefined]);

  if (view === "warnings" && warnings.length === 0) return null;

  const summary =
    view === "result"
      ? result?.changed
        ? `精修完成 · ${result.changes.length} 处改动`
        : "精修未产生改动"
      : refinable.length > 0
        ? `${refinable.length} 项可精修${manual > 0 ? ` · ${manual} 项待人工` : ""}`
        : `${manual} 项待人工修正`;

  const canExpand =
    view === "result" ? Boolean(result?.changed) || (result?.rechecked.length ?? 0) > 0 : true;

  return (
    <div className="qr">
      <div className="qr-row">
        <span className={`qr-eyebrow lv-t-caps ${view === "result" ? "qr-ok" : ""}`}>
          {view === "refining" || view === "result" ? "AI 精修" : "AI 质检"}
        </span>

        {view === "refining" ? (
          <span className="qr-stage lv-t-compact">
            <span className="qr-pulse" aria-hidden />
            {stage || "精修中…"}
          </span>
        ) : (
          <button
            type="button"
            className="qr-sum lv-t-compact"
            onClick={() => canExpand && setExpanded((v) => !v)}
            aria-expanded={expanded}
          >
            {summary}
            {canExpand && (
              <span className="qr-chev lv-t-caps">{expanded ? "收起 ▴" : "展开详情 ▾"}</span>
            )}
          </button>
        )}

        <div className="qr-actions">
          {view === "warnings" && refinable.length > 0 && (
            <button type="button" className="qr-btn qr-solid" onClick={() => runRefine([])}>
              一键精修
            </button>
          )}
          {view === "result" && (
            <button
              type="button"
              className="qr-btn qr-ghost"
              onClick={runUndo}
              disabled={rechecking}
              title={rechecking ? "复检完成后可撤销" : undefined}
            >
              撤销
            </button>
          )}
        </div>
      </div>

      {expanded && view === "warnings" && (
        <ul className="qr-list">
          {warnings.map((w, i) => (
            <li key={`${w.code}-${i}`} className="qr-item">
              <span className={w.refinable ? "qr-dot-r" : "qr-dot-m"} aria-hidden>
                {w.refinable ? "✦" : "●"}
              </span>
              <div className="qr-item-body">
                <span className="lv-t-compact qr-item-label">{w.label}</span>
                {w.detail && <span className="lv-t-meta qr-item-detail">{w.detail}</span>}
              </div>
              {w.refinable && (
                <button
                  type="button"
                  className="qr-btn qr-ghost qr-item-btn"
                  onClick={() => runRefine([w.code])}
                >
                  精修
                </button>
              )}
            </li>
          ))}
        </ul>
      )}

      {expanded && view === "result" && (
        <div className="qr-result">
          {result?.changed &&
            result.changes.slice(0, 6).map((c, i) => (
              <div key={i} className="qr-change">
                <span className="lv-t-caps qr-change-tag">
                  {c.kind === "events" ? "事件" : "角色"}·{c.entity}
                </span>
                <span className="lv-t-meta qr-before">{c.before}</span>
                <span className="lv-t-compact qr-after">{c.after}</span>
              </div>
            ))}
          {result && result.changes.length > 6 && (
            <div className="lv-t-meta qr-more">…另有 {result.changes.length - 6} 处</div>
          )}
          <div className="qr-recheck lv-t-meta">
            {rechecking ? (
              <span className="qr-recheck-live">
                <span className="qr-pulse" aria-hidden />
                复检中…（改动已应用，可继续等待或稍后查看）
              </span>
            ) : result && result.rechecked.length === 0 ? (
              "✓ 复检未再发现硬伤"
            ) : (
              `复检后仍存在 ${result?.rechecked.length} 项（可再修一轮或人工处理）`
            )}
          </div>
        </div>
      )}

      {error && <div className="lv-t-meta qr-error">⚠ {error}</div>}

      <style jsx>{`
        .qr {
          display: flex;
          flex-direction: column;
          gap: var(--lv-s-2);
          padding-bottom: var(--lv-s-3);
          border-bottom: 1px solid var(--lv-line);
        }
        .qr-row {
          display: flex;
          align-items: center;
          gap: var(--lv-s-3);
          flex-wrap: wrap;
          min-height: 28px;
        }
        .qr-eyebrow { color: var(--lv-ink-3); flex-shrink: 0; }
        .qr-ok { color: var(--lv-success); }
        .qr-sum {
          display: inline-flex;
          align-items: center;
          gap: 6px;
          background: none;
          border: none;
          padding: 0;
          color: var(--lv-ink-2);
          cursor: pointer;
        }
        .qr-sum:hover { color: var(--lv-ink); }
        .qr-sum:hover .qr-chev { color: var(--lv-ink-2); }
        .qr-chev { color: var(--lv-ink-3); flex-shrink: 0; }
        .qr-stage {
          display: inline-flex;
          align-items: center;
          gap: var(--lv-s-2);
          color: var(--lv-ink-2);
        }
        .qr-pulse {
          width: 7px; height: 7px; border-radius: 9999px;
          background: var(--lv-ink-3);
          animation: qr-pulse 1.1s ease-in-out infinite;
        }
        @keyframes qr-pulse { 0%,100% { opacity: .25; } 50% { opacity: 1; } }
        .qr-actions { margin-left: auto; display: flex; gap: var(--lv-s-2); flex-shrink: 0; }
        .qr-btn {
          display: inline-flex; align-items: center; justify-content: center;
          height: 28px; padding: 0 var(--lv-s-3);
          border-radius: var(--lv-r-pill);
          font-size: 12px; font-weight: 500; cursor: pointer;
          transition: background var(--lv-dur-fast) var(--lv-ease), color var(--lv-dur-fast) var(--lv-ease);
        }
        .qr-solid { background: var(--lv-ink); color: var(--lv-bg); border: none; }
        .qr-solid:hover { background: var(--lv-ink-2); }
        .qr-ghost { background: transparent; color: var(--lv-ink-3); border: 1px solid var(--lv-line-2); }
        .qr-ghost:hover { background: rgba(255,255,255,.04); color: var(--lv-ink); }
        .qr-btn:disabled { opacity: .5; cursor: not-allowed; pointer-events: none; }
        .qr-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: var(--lv-s-2); }
        .qr-item { display: flex; align-items: flex-start; gap: var(--lv-s-3); }
        .qr-dot-r { color: var(--lv-ink-3); font-size: 11px; margin-top: 3px; flex-shrink: 0; }
        .qr-dot-m { color: var(--lv-warn); font-size: 9px; margin-top: 4px; flex-shrink: 0; }
        .qr-item-body { display: flex; flex-direction: column; gap: 1px; min-width: 0; }
        .qr-item-label { color: var(--lv-ink); }
        .qr-item-detail { color: var(--lv-ink-3); }
        .qr-item-btn { margin-left: auto; flex-shrink: 0; height: 24px; }
        .qr-result { display: flex; flex-direction: column; gap: var(--lv-s-3); }
        .qr-change { display: flex; flex-direction: column; gap: 1px; }
        .qr-change-tag { color: var(--lv-ink-4); }
        .qr-before { color: var(--lv-ink-3); text-decoration: line-through; }
        .qr-after { color: var(--lv-ink); }
        .qr-more { color: var(--lv-ink-3); }
        .qr-recheck { color: var(--lv-ink-3); }
        .qr-recheck-live { display: inline-flex; align-items: center; gap: 6px; color: var(--lv-ink-2); }
        .qr-error { color: var(--lv-danger); }
      `}</style>
    </div>
  );
}
