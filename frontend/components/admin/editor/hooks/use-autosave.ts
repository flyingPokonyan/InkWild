"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export type AutosaveState =
  | { status: "idle"; lastSavedAt: Date | null }
  | { status: "dirty"; lastSavedAt: Date | null }
  | { status: "saving"; lastSavedAt: Date | null }
  | { status: "saved"; lastSavedAt: Date }
  | { status: "error"; lastSavedAt: Date | null; message: string };

interface UseAutosaveOptions<P> {
  /** 序列化 payload，决定 dirty 与否（避免对象引用比较） */
  payload: P;
  /** 实际保存调用 */
  save: (payload: P) => Promise<void>;
  /** 防抖间隔 */
  debounceMs?: number;
  /** 是否启用 */
  enabled?: boolean;
  /** 初始 lastSavedAt */
  initialSavedAt?: Date | null;
}

/**
 * 受控 payload 自动保存：
 * - payload 变更（按 JSON 序列化比对）→ 进入 dirty
 * - debounce 后触发 save，期间状态 saving
 * - 成功/失败回调更新 state
 * - 同时返回 manualSave、reset（用于发布前先 flush）
 */
export function useAutosave<P>({
  payload,
  save,
  debounceMs = 1500,
  enabled = true,
  initialSavedAt = null,
}: UseAutosaveOptions<P>) {
  const [state, setState] = useState<AutosaveState>({
    status: "idle",
    lastSavedAt: initialSavedAt,
  });
  const lastSavedSnapshotRef = useRef<string>(JSON.stringify(payload));
  const lastSavedAtRef = useRef<Date | null>(initialSavedAt);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const savingRef = useRef(false);
  const queuedRef = useRef<string | null>(null);

  const cancelTimer = () => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  };

  const flush = useCallback(
    async (snapshotJson: string, snapshotPayload: P) => {
      if (savingRef.current) {
        queuedRef.current = snapshotJson;
        return;
      }
      savingRef.current = true;
      setState((prev) => ({ status: "saving", lastSavedAt: prev.lastSavedAt }));
      try {
        await save(snapshotPayload);
        const at = new Date();
        lastSavedSnapshotRef.current = snapshotJson;
        lastSavedAtRef.current = at;
        setState({ status: "saved", lastSavedAt: at });
      } catch (e) {
        setState({
          status: "error",
          lastSavedAt: lastSavedAtRef.current,
          message: e instanceof Error ? e.message : "save failed",
        });
      } finally {
        savingRef.current = false;
        if (queuedRef.current && queuedRef.current !== lastSavedSnapshotRef.current) {
          const next = queuedRef.current;
          queuedRef.current = null;
          // small async gap so React can flush
          setTimeout(() => {
            try {
              const nextPayload = JSON.parse(next) as P;
              void flush(next, nextPayload);
            } catch {
              // unreachable: snapshot was a stringified payload
            }
          }, 0);
        }
      }
    },
    [save],
  );

  // dirty detection + debounce schedule
  useEffect(() => {
    if (!enabled) return;
    const json = JSON.stringify(payload);
    if (json === lastSavedSnapshotRef.current) {
      // back to clean
      setState((prev) =>
        prev.status === "dirty" || prev.status === "error"
          ? { status: "idle", lastSavedAt: prev.lastSavedAt }
          : prev,
      );
      return;
    }
    setState((prev) => ({ status: "dirty", lastSavedAt: prev.lastSavedAt }));
    cancelTimer();
    timerRef.current = setTimeout(() => {
      void flush(json, payload);
    }, debounceMs);
    return cancelTimer;
  }, [payload, debounceMs, enabled, flush]);

  // unmount cleanup
  useEffect(() => () => cancelTimer(), []);

  const manualSave = useCallback(async () => {
    cancelTimer();
    const json = JSON.stringify(payload);
    if (json === lastSavedSnapshotRef.current && state.status !== "error") return;
    await flush(json, payload);
  }, [payload, flush, state.status]);

  const markSaved = useCallback((nextPayload: P, at: Date = new Date()) => {
    lastSavedSnapshotRef.current = JSON.stringify(nextPayload);
    lastSavedAtRef.current = at;
    setState({ status: "saved", lastSavedAt: at });
  }, []);

  const isDirty = state.status === "dirty" || state.status === "saving" || state.status === "error";

  return { state, manualSave, markSaved, isDirty };
}
