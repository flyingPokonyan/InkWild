import { apiURL } from "./api";
import { extractSSEBlocks } from "./sse-parser";
import type { ProcessingEventPayload } from "./types";

const SSE_HEADERS = {
  Accept: "text/event-stream",
  "Content-Type": "application/json",
};

const EXPECTED_GAME_SSE_SCHEMA_VERSION = 1;

// Connection-loss watchdog. The backend emits a `:` comment every 30s as a
// heartbeat; if we don't see *any* bytes (heartbeat or real event) for 90s
// we consider the connection dead and surface a `connection_lost` typed error.
const CONNECTION_LOST_THRESHOLD_MS = 90_000;
const CONNECTION_LOST_CHECK_INTERVAL_MS = 10_000;

/** Categories surfaced to upper layers. Mirrors the backend enum in `api/game.py`. */
export type SSEErrorCode =
  | "rate_limit"
  | "cost_cap"
  | "llm_timeout"
  | "provider_down"
  | "moderation"
  // Phase 2.A.3 — Director/NPC structured output unparseable; retrying the
  // round is the right user affordance (provider is alive, just gave noise).
  | "llm_parse"
  | "connection_lost"
  // Phase 1 credits — balance can't cover the action's estimate (L2 gate).
  | "credits_insufficient"
  | "unknown";

const KNOWN_SSE_ERROR_CODES: ReadonlySet<SSEErrorCode> = new Set([
  "rate_limit",
  "cost_cap",
  "llm_timeout",
  "provider_down",
  "moderation",
  "llm_parse",
  "connection_lost",
  "credits_insufficient",
  "unknown",
]);

export interface SSEError {
  code: SSEErrorCode;
  message: string;
  /** Optional retry hint, primarily set for `rate_limit`. */
  retryAfterMs?: number;
}

export interface SSECallbacks {
  onProcessing?: (data: Partial<ProcessingEventPayload>) => void;
  onNarrative?: (text: string) => void;
  onStateUpdate?: (data: Record<string, unknown>) => void;
  /** Phase-4 follow-up: case board refreshes a beat after `done` (carries game_state). */
  onCaseBoardUpdate?: (data: Record<string, unknown>) => void;
  onSessionCreated?: (data: { session_id: string }) => void;
  onEnding?: (data: { ending_type: string; title: string }) => void;
  onError?: (error: SSEError) => void;
  onCostWarning?: (data: { message: string; suggest?: string; total_cost_cents?: number; cap_cost_cents?: number }) => void;
  onCapReached?: (data: { message: string; suggest?: string; total_cost_cents?: number; cap_cost_cents?: number }) => void;
  onDone?: () => void;
}

function costGuardrailPayload(payload: Record<string, unknown>) {
  return {
    message: String(payload.message || ""),
    suggest: typeof payload.suggest === "string" ? payload.suggest : undefined,
    total_cost_cents: typeof payload.total_cost_cents === "number" ? payload.total_cost_cents : undefined,
    cap_cost_cents: typeof payload.cap_cost_cents === "number" ? payload.cap_cost_cents : undefined,
  };
}

function validateGameSSEPayload(payload: unknown): Record<string, unknown> {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new Error("SSE 数据解析失败：事件数据不是有效对象");
  }

  const record = payload as Record<string, unknown>;
  const version = record.version ?? record.schema_version;
  if (version !== undefined && version !== EXPECTED_GAME_SSE_SCHEMA_VERSION) {
    throw new Error(`SSE 事件版本不匹配：期望 ${EXPECTED_GAME_SSE_SCHEMA_VERSION}`);
  }

  return record;
}

function normalizeSSEErrorCode(value: unknown): SSEErrorCode {
  if (typeof value === "string" && (KNOWN_SSE_ERROR_CODES as ReadonlySet<string>).has(value)) {
    return value as SSEErrorCode;
  }
  return "unknown";
}

function buildSSEError(payload: Record<string, unknown>): SSEError {
  const code = normalizeSSEErrorCode(payload.code);
  const message = typeof payload.message === "string" && payload.message
    ? payload.message
    : "连接失败";
  const retryAfterMs = typeof payload.retry_after_ms === "number"
    ? payload.retry_after_ms
    : undefined;
  return { code, message, retryAfterMs };
}

function dispatchEvent(
  eventName: string,
  payload: Record<string, unknown>,
  callbacks: SSECallbacks,
): boolean {
  switch (eventName) {
    case "processing": {
      const rawKind = payload.kind;
      const kind: ProcessingEventPayload["kind"] | undefined =
        rawKind === "phase" || rawKind === "per_npc" || rawKind === "progress"
          ? rawKind
          : undefined;
      const rawStage = payload.stage;
      const stage: ProcessingEventPayload["stage"] | undefined =
        rawStage === "received" ||
        rawStage === "reasoning" ||
        rawStage === "npcs_entering" ||
        rawStage === "writing"
          ? rawStage
          : undefined;
      callbacks.onProcessing?.({
        phase: typeof payload.phase === "string" ? payload.phase : undefined,
        focus_npcs: Array.isArray(payload.focus_npcs)
          ? payload.focus_npcs.filter((item): item is string => typeof item === "string")
          : undefined,
        flavor: typeof payload.flavor === "string" ? payload.flavor : undefined,
        stage,
        input_summary: typeof payload.input_summary === "string" ? payload.input_summary : undefined,
        npcs: Array.isArray(payload.npcs)
          ? payload.npcs.filter((item): item is string => typeof item === "string")
          : undefined,
        kind,
      });
      return false;
    }
    case "narrative":
      callbacks.onNarrative?.(String(payload.text || ""));
      return false;
    case "state_update":
      callbacks.onStateUpdate?.(payload);
      return false;
    case "case_board_update":
      callbacks.onCaseBoardUpdate?.(payload);
      return false;
    case "session_created":
      callbacks.onSessionCreated?.(payload as { session_id: string });
      return false;
    case "ending":
      callbacks.onEnding?.(payload as { ending_type: string; title: string });
      return false;
    case "error":
      callbacks.onError?.(buildSSEError(payload));
      return false;
    case "cost_warning":
      callbacks.onCostWarning?.(costGuardrailPayload(payload));
      return false;
    case "cap_reached":
      callbacks.onCapReached?.(costGuardrailPayload(payload));
      callbacks.onError?.({
        code: "cost_cap",
        message: String(payload.message || "本次故事已达到费用上限"),
      });
      return false;
    case "done":
      callbacks.onDone?.();
      return true;
    default:
      return false;
  }
}

function processChunk(block: string, callbacks: SSECallbacks): boolean {
  const trimmed = block.trim();
  if (!trimmed) {
    return false;
  }

  let eventName = "message";
  const dataLines: string[] = [];
  let sawDataOrEvent = false;

  for (const line of trimmed.split("\n")) {
    // SSE comment lines (`:foo`, `: heartbeat`, `:hb`) are keepalives — ignored
    // for dispatch but they DO refresh the connection-loss watchdog (handled
    // upstream via `lastDataTimestamp` on every read).
    if (line.startsWith(":")) {
      continue;
    }
    if (line.startsWith("event: ")) {
      eventName = line.slice(7).trim();
      sawDataOrEvent = true;
    } else if (line.startsWith("data: ")) {
      dataLines.push(line.slice(6));
      sawDataOrEvent = true;
    }
  }

  if (!sawDataOrEvent) {
    // Block was pure-comment (heartbeat). Nothing to dispatch.
    return false;
  }

  if (dataLines.length === 0) {
    return false;
  }

  let parsedPayload: unknown;
  try {
    parsedPayload = JSON.parse(dataLines.join("\n"));
  } catch {
    throw new Error("SSE 数据解析失败：事件 JSON 格式无效");
  }

  const payload = validateGameSSEPayload(parsedPayload);
  return dispatchEvent(eventName, payload, callbacks);
}

function readRetryAfterMs(response: Response): number | undefined {
  const header = response.headers.get("Retry-After");
  if (!header) return undefined;
  const seconds = Number(header);
  if (Number.isFinite(seconds) && seconds >= 0) {
    return Math.round(seconds * 1000);
  }
  // RFC 7231 also allows HTTP-date; fall back to undefined.
  const dateMs = Date.parse(header);
  if (Number.isFinite(dateMs)) {
    return Math.max(0, dateMs - Date.now());
  }
  return undefined;
}

function buildHttpError(response: Response, payload: unknown): SSEError {
  // Map known HTTP statuses to typed SSE error codes. The SSE rate-limit
  // middleware rejects at the HTTP layer (429) before the stream starts —
  // see backend/api/game.py game_action handler.
  if (response.status === 429) {
    let message = "操作过于频繁，请稍后再试";
    if (
      payload &&
      typeof payload === "object" &&
      "detail" in payload &&
      payload.detail &&
      typeof payload.detail === "object" &&
      "message" in payload.detail &&
      typeof (payload.detail as { message?: unknown }).message === "string"
    ) {
      message = (payload.detail as { message: string }).message;
    }
    return {
      code: "rate_limit",
      message,
      retryAfterMs: readRetryAfterMs(response),
    };
  }

  // Surface backend-classified message when present, otherwise generic fallback.
  let message = "连接失败";
  if (payload && typeof payload === "object") {
    const detail = (payload as { detail?: unknown }).detail;
    if (
      detail &&
      typeof detail === "object" &&
      "message" in detail &&
      typeof (detail as { message?: unknown }).message === "string"
    ) {
      message = (detail as { message: string }).message;
    } else if (
      "message" in payload &&
      typeof (payload as { message?: unknown }).message === "string"
    ) {
      message = (payload as { message: string }).message;
    }
  }

  if (response.status >= 500) {
    return { code: "provider_down", message };
  }
  return { code: "unknown", message };
}

export async function streamAction(
  path: string,
  body: Record<string, unknown>,
  callbacks: SSECallbacks,
): Promise<void> {
  const response = await fetch(apiURL(path), {
    method: "POST",
    credentials: "include",
    headers: {
      ...SSE_HEADERS,
    },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    callbacks.onError?.(buildHttpError(response, payload));
    callbacks.onDone?.();
    return;
  }

  const reader = response.body?.getReader();
  if (!reader) {
    callbacks.onError?.({ code: "unknown", message: "未收到流式响应" });
    callbacks.onDone?.();
    return;
  }

  const decoder = new TextDecoder();
  let buffer = "";
  let sawDone = false;

  // Connection-loss watchdog: track the last time *any* bytes arrived
  // (including heartbeat comments) and emit `connection_lost` after 90s
  // of total silence. We do NOT auto-reconnect here (deferred).
  let lastDataTimestamp = Date.now();
  let connectionLostFired = false;
  const watchdog = setInterval(() => {
    if (connectionLostFired) return;
    if (Date.now() - lastDataTimestamp > CONNECTION_LOST_THRESHOLD_MS) {
      connectionLostFired = true;
      callbacks.onError?.({
        code: "connection_lost",
        message: "网络连接已断开，请刷新或重试",
      });
      // Best-effort cancel of the underlying read so the loop unblocks.
      try {
        void reader.cancel();
      } catch {
        // ignore
      }
    }
  }, CONNECTION_LOST_CHECK_INTERVAL_MS);

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (value && value.byteLength > 0) {
        // Any bytes — heartbeat or real event — count as a liveness signal.
        lastDataTimestamp = Date.now();
      }
      buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
      const { blocks, rest } = extractSSEBlocks(buffer);
      buffer = rest;

      for (const chunk of blocks) {
        sawDone = processChunk(chunk, callbacks) || sawDone;
      }

      if (done) {
        break;
      }
    }

    if (buffer.trim()) {
      sawDone = processChunk(buffer, callbacks) || sawDone;
    }
  } catch (error) {
    if (!connectionLostFired) {
      callbacks.onError?.({
        code: "unknown",
        message: error instanceof Error ? error.message : "流式连接中断",
      });
    }
  } finally {
    clearInterval(watchdog);
    if (!sawDone) {
      callbacks.onDone?.();
    }
  }
}
