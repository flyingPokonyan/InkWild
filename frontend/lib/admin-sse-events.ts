export type ProgressMeta = {
  /** 主阶段位置（0-based） */
  stage_index?: number;
  total_stages?: number;
  /** 阶段人类可读标签（后端可选填） */
  stage_label?: string;
  /** 子任务并发位置（仅在主阶段含并发时填） */
  subtask_key?: string;
  subtask_index?: number;
  subtask_total?: number;
  /** 耗时（ms） */
  duration_ms?: number;
  /** 摘要 */
  payload_summary?: Record<string, number | string>;
  /** 重试信息 */
  attempt?: number;
  max_attempts?: number;
  error_class?: string;
  // 阶段反馈字段（completed 事件 meta 携带，前端 formatter 用）。
  // 所有可选，后端就近 emit；缺失时 formatter 自动降级。
  sample?: string[];
  world_name?: string;
  location_count?: number;
  dimension_count?: number;
  role_count?: number;
  character_count?: number;
  event_count?: number;
  npc_count?: number;
  edge_count?: number;
  clue_count?: number;
  playable_count?: number;
  repair_count?: number;
  cover_count?: number;
  avatar_count?: number;
  image_count?: number;
  // === T4: Stage 0 IP recognition (phase_a) ===
  // 仅在 phase === "ip_recognition" && code === "completed" 时出现
  kind?: "known_ip" | "hybrid" | "original";
  confidence?: number;
  ip_name?: string | null;
  ip_type?: "tv" | "movie" | "novel" | "anime" | "game" | "other" | null;
  one_liner?: string | null;
  source_hints?: string[];
};

/** Stage 0（phase_a）IP 识别完成事件 —— progress 事件的特化形态。
 *
 * 后端在 phase_a 任务流尾部 emit 一个 progress 事件：
 * `{ phase: "ip_recognition", code: "completed", meta: { kind, confidence, ... } }`
 *
 * 前端用 `isIPRecognitionEvent(event)` type guard 把通用 progress 事件窄化到这个
 * 形状，再传给 IPRecognitionCard（T9 实装）。
 */
export type IPRecognitionEvent = {
  phase: "ip_recognition";
  code: "completed";
  message?: string;
  meta: {
    kind: "known_ip" | "hybrid" | "original";
    confidence: number;
    ip_name?: string | null;
    ip_type?: "tv" | "movie" | "novel" | "anime" | "game" | "other" | null;
    one_liner?: string | null;
    source_hints?: string[];
  };
};

export function isIPRecognitionEvent(
  event: { phase?: string; code?: string; meta?: ProgressMeta | undefined },
): event is IPRecognitionEvent {
  return (
    event.phase === "ip_recognition" &&
    event.code === "completed" &&
    !!event.meta &&
    typeof (event.meta as ProgressMeta).kind === "string"
  );
}

/** 结构化 progress 事件 payload（由 dispatchAdminSseEvent 解析后传给 onProgress） */
export type ProgressEventData = {
  phase: string;
  /** started / completed / subtask_started / subtask_completed / heartbeat / repair_completed / review_adjusted */
  code: string;
  message?: string;
  meta?: ProgressMeta;
};

export interface AdminProgressEvent {
  phase: string;
  code: string;
  message: string;
  meta?: ProgressMeta;
}

export interface AdminSSECallbacks<T> {
  onEvent?: (event: { name: string; seq?: number; payload: unknown }) => void;
  onProgress?: (event: AdminProgressEvent) => void;
  onWarning?: (event: AdminProgressEvent) => void;
  onResult?: (payload: T) => void;
  onError?: (message: string) => void;
  onDone?: () => void;
}

export function dispatchAdminSseEvent<T>(
  eventName: string,
  payload: unknown,
  callbacks: AdminSSECallbacks<T>,
): boolean {
  if (eventName === "progress") {
    const event = payload as Partial<ProgressEventData>;
    callbacks.onProgress?.({
      phase: event.phase || "",
      code: event.code || "",
      message: event.message || "",
      meta: event.meta,
    });
    return false;
  }

  if (eventName === "warning") {
    const event = payload as Partial<ProgressEventData>;
    callbacks.onWarning?.({
      phase: event.phase || "",
      code: event.code || "",
      message: event.message || "",
      meta: event.meta,
    });
    return false;
  }

  if (eventName === "result") {
    callbacks.onResult?.(payload as T);
    return false;
  }

  if (eventName === "error") {
    callbacks.onError?.(String((payload as { message?: string }).message || "生成失败"));
    return false;
  }

  if (eventName === "done") {
    callbacks.onDone?.();
    return true;
  }

  return false;
}
