import { dispatchAdminSseEvent, type AdminSSECallbacks } from "./admin-sse-events";
import { extractSSEBlocks } from "./sse-parser";
import type {
  AdminGenerationTaskSummary,
  AdminScriptDraftDetail,
  AdminWorldDraftDetail,
  ApiEnvelope,
  ApiErrorDetail,
} from "./types";

const ADMIN_STREAM_TIMEOUT_MS = 30 * 60 * 1000;
const IMAGE_REGEN_RECOVERY_TIMEOUT_MS = 12 * 60 * 1000;
const IMAGE_REGEN_POLL_INTERVAL_MS = 3 * 1000;

export type AdminStreamResult = {
  completed: boolean;
  aborted: boolean;
  timedOut: boolean;
  errorMessage: string | null;
};

export class AdminPermissionError extends Error {
  status: number;

  constructor(message: string) {
    super(message);
    this.name = "AdminPermissionError";
    this.status = 403;
  }
}

function buildErrorMessage(payload: unknown, fallback: string): string {
  if (!payload || typeof payload !== "object") {
    return fallback;
  }

  const response = payload as {
    message?: string;
    detail?: ApiErrorDetail;
  };

  return response.detail?.message || response.message || fallback;
}

function redirectToLogin(): void {
  if (typeof window === "undefined") {
    return;
  }

  const location = window.location;
  const from = `${location.pathname}${location.search}${location.hash}`;
  location.href = `/login?from=${encodeURIComponent(from)}`;
}

function createTimeoutSignal(
  externalSignal: AbortSignal | undefined,
): {
  signal: AbortSignal;
  didTimeout: () => boolean;
  cleanup: () => void;
} {
  const controller = new AbortController();
  let timedOut = false;

  const timeoutId = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, ADMIN_STREAM_TIMEOUT_MS);

  const abortFromExternal = () => {
    controller.abort(externalSignal?.reason);
  };

  if (externalSignal) {
    if (externalSignal.aborted) {
      abortFromExternal();
    } else {
      externalSignal.addEventListener("abort", abortFromExternal, { once: true });
    }
  }

  return {
    signal: controller.signal,
    didTimeout: () => timedOut,
    cleanup: () => {
      clearTimeout(timeoutId);
      externalSignal?.removeEventListener("abort", abortFromExternal);
    },
  };
}

export async function workshopFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const headers = new Headers(options?.headers);
  const hasBody = options?.body !== undefined;

  if (hasBody && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(path, {
    cache: "no-store",
    ...options,
    credentials: "include",
    headers,
  });

  const payload = (await response.json().catch(() => null)) as ApiEnvelope<T> | null;

  if (response.status === 401) {
    redirectToLogin();
    throw new Error(buildErrorMessage(payload, "请先登录"));
  }

  if (response.status === 403) {
    // For workshop routes a 403 means the user lacks creator permission or
    // is not the resource owner — surface inline rather than redirect.
    throw new AdminPermissionError(buildErrorMessage(payload, "没有权限"));
  }

  if (!response.ok) {
    throw new Error(buildErrorMessage(payload, "请求失败"));
  }

  if (payload && typeof payload.code === "number") {
    if (payload.code !== 0) {
      throw new Error(payload.message || "请求失败");
    }
    return payload.data;
  }

  return payload as T;
}

export type { AdminProgressEvent } from "./admin-sse-events";

/**
 * Continue a world draft's generation after Stage 0 IP recognition.
 * Backend kicks off phase_b with the chosen fidelity mode and returns
 * the new task id; caller updates `generation_task` state so the existing
 * SSE-subscribe effect re-subscribes to the new task stream.
 */
export async function continueWorldDraftGeneration(
  draftId: string,
  fidelityMode: "strict" | "loose" | "none",
): Promise<{ task_id: string; draft_id: string }> {
  return workshopFetch<{ task_id: string; draft_id: string }>(
    `/api/workshop/world-drafts/${draftId}/continue-generation`,
    {
      method: "POST",
      body: JSON.stringify({ fidelity_mode: fidelityMode }),
    },
  );
}

/** Upload a base64 data-URL image, returns the stored URL. */
export async function uploadWorkshopImage(
  image: string,
  kind: "avatar" | "cover",
): Promise<string> {
  const { url } = await workshopFetch<{ url: string }>("/api/workshop/uploads", {
    method: "POST",
    body: JSON.stringify({ image, kind }),
  });
  return url;
}

/** Fetch the exact base prompt for one world-draft image. */
export async function getWorldDraftImagePrompt(
  draftId: string,
  target: string,
): Promise<string> {
  const { prompt } = await workshopFetch<{ prompt: string }>(
    `/api/workshop/world-drafts/${draftId}/image-prompt`,
    { method: "POST", body: JSON.stringify({ target }) },
  );
  return prompt;
}

/** Fetch the exact base prompt for one script-draft cover. */
export async function getScriptDraftImagePrompt(draftId: string): Promise<string> {
  const { prompt } = await workshopFetch<{ prompt: string }>(
    `/api/workshop/script-drafts/${draftId}/image-prompt`,
    { method: "POST", body: JSON.stringify({ target: "cover" }) },
  );
  return prompt;
}

function isFetchConnectionError(error: unknown): boolean {
  return error instanceof TypeError;
}

function waitForDelay(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(signal.reason ?? new DOMException("Aborted", "AbortError"));
      return;
    }

    const finish = () => {
      signal?.removeEventListener("abort", abort);
      resolve();
    };
    const timeoutId = setTimeout(finish, ms);
    const abort = () => {
      clearTimeout(timeoutId);
      reject(signal?.reason ?? new DOMException("Aborted", "AbortError"));
    };
    signal?.addEventListener("abort", abort, { once: true });
  });
}

function worldDraftImageURL(detail: AdminWorldDraftDetail, target: string): string {
  if (target === "hero") return detail.payload.hero_image || "";
  if (target === "cover") return detail.payload.cover_image || "";
  if (!target.startsWith("avatar:")) return "";

  const characterName = target.slice("avatar:".length).trim();
  const characterImages = (
    detail.payload as typeof detail.payload & { character_images?: Record<string, string> }
  ).character_images;
  return (
    characterImages?.[characterName] ||
    detail.payload.world_characters.find((character) => character.name.trim() === characterName)?.avatar ||
    ""
  );
}

async function pollForRegeneratedImage(
  readCurrentURL: () => Promise<string>,
  previousURL: string,
  signal?: AbortSignal,
): Promise<string> {
  const deadline = Date.now() + IMAGE_REGEN_RECOVERY_TIMEOUT_MS;
  while (Date.now() < deadline) {
    await waitForDelay(IMAGE_REGEN_POLL_INTERVAL_MS, signal);
    try {
      const currentURL = await readCurrentURL();
      if (currentURL && currentURL !== previousURL) return currentURL;
    } catch (error) {
      if (!isFetchConnectionError(error)) throw error;
    }
  }
  throw new Error("图片仍在后台处理，请稍后刷新草稿");
}

/** Regenerate one world-draft image. ``target`` ∈ "hero" | "cover" | "avatar:<名>". */
export async function regenerateWorldDraftImage(
  draftId: string,
  target: string,
  prompt: string,
  previousURL = "",
  signal?: AbortSignal,
): Promise<string> {
  try {
    const { url } = await workshopFetch<{ url: string }>(
      `/api/workshop/world-drafts/${draftId}/regenerate-image`,
      { method: "POST", body: JSON.stringify({ target, prompt }), signal },
    );
    return url;
  } catch (error) {
    if (!isFetchConnectionError(error) || signal?.aborted) throw error;
    return pollForRegeneratedImage(async () => {
      const detail = await workshopFetch<AdminWorldDraftDetail>(
        `/api/workshop/world-drafts/${draftId}`,
        { signal },
      );
      return worldDraftImageURL(detail, target);
    }, previousURL, signal);
  }
}

/** Regenerate a script-draft cover. */
export async function regenerateScriptDraftImage(
  draftId: string,
  prompt: string,
  previousURL = "",
  signal?: AbortSignal,
): Promise<string> {
  try {
    const { url } = await workshopFetch<{ url: string }>(
      `/api/workshop/script-drafts/${draftId}/regenerate-image`,
      { method: "POST", body: JSON.stringify({ target: "cover", prompt }), signal },
    );
    return url;
  } catch (error) {
    if (!isFetchConnectionError(error) || signal?.aborted) throw error;
    return pollForRegeneratedImage(async () => {
      const detail = await workshopFetch<AdminScriptDraftDetail>(
        `/api/workshop/script-drafts/${draftId}`,
        { signal },
      );
      return detail.payload.cover_image || "";
    }, previousURL, signal);
  }
}

export async function streamAdminEvents<T>(
  path: string,
  callbacks: AdminSSECallbacks<T>,
  options?: {
    method?: "GET" | "POST";
    body?: Record<string, unknown>;
    signal?: AbortSignal;
  },
): Promise<AdminStreamResult> {
  const timeout = createTimeoutSignal(options?.signal);
  const headers = new Headers({ Accept: "text/event-stream" });
  if (options?.body) {
    headers.set("Content-Type", "application/json");
  }
  let response: Response;

  try {
    response = await fetch(path, {
      method: options?.method || "GET",
      credentials: "include",
      headers,
      body: options?.body ? JSON.stringify(options.body) : undefined,
      signal: timeout.signal,
    });
  } catch (error) {
    timeout.cleanup();
    if (timeout.didTimeout()) {
      callbacks.onError?.("任务超时");
      callbacks.onDone?.();
      return { completed: false, aborted: false, timedOut: true, errorMessage: "任务超时" };
    }
    if (error instanceof DOMException && error.name === "AbortError") {
      return { completed: false, aborted: true, timedOut: false, errorMessage: null };
    }
    const message = error instanceof Error ? error.message : "连接失败";
    callbacks.onError?.(message);
    callbacks.onDone?.();
    return { completed: false, aborted: false, timedOut: false, errorMessage: message };
  }

  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    timeout.cleanup();
    const message = buildErrorMessage(payload, "连接失败");
    callbacks.onError?.(message);
    callbacks.onDone?.();
    return { completed: false, aborted: false, timedOut: false, errorMessage: message };
  }

  const reader = response.body?.getReader();
  if (!reader) {
    timeout.cleanup();
    callbacks.onError?.("未收到流式响应");
    callbacks.onDone?.();
    return { completed: false, aborted: false, timedOut: false, errorMessage: "未收到流式响应" };
  }

  const decoder = new TextDecoder();
  let buffer = "";
  let sawDone = false;
  let aborted = false;
  let errorMessage: string | null = null;

  try {
    while (true) {
      const { done, value } = await reader.read();
      buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
      const { blocks, rest } = extractSSEBlocks(buffer);
      buffer = rest;

      for (const chunk of blocks) {
        const lines = chunk.trim().split("\n");
        let eventName = "message";
        let eventSeq: number | undefined;
        const dataLines: string[] = [];

        for (const line of lines) {
          if (line.startsWith("event: ")) {
            eventName = line.slice(7).trim();
          } else if (line.startsWith("id: ")) {
            const parsedSeq = Number.parseInt(line.slice(4).trim(), 10);
            if (Number.isFinite(parsedSeq)) {
              eventSeq = parsedSeq;
            }
          } else if (line.startsWith("data: ")) {
            dataLines.push(line.slice(6));
          }
        }

        const payload = dataLines.length > 0 ? JSON.parse(dataLines.join("\n")) : {};
        callbacks.onEvent?.({ name: eventName, seq: eventSeq, payload });
        if (dispatchAdminSseEvent<T>(eventName, payload, callbacks)) {
          sawDone = true;
        }
      }

      if (done) break;
    }
  } catch (error) {
    if (timeout.didTimeout()) {
      errorMessage = "任务超时";
      callbacks.onError?.("任务超时");
      return { completed: sawDone, aborted: false, timedOut: true, errorMessage };
    }
    if (error instanceof DOMException && error.name === "AbortError") {
      aborted = true;
      return { completed: sawDone, aborted: true, timedOut: false, errorMessage: null };
    }
    errorMessage = error instanceof Error ? error.message : "流式连接中断";
    callbacks.onError?.(errorMessage);
  } finally {
    timeout.cleanup();
    if (timeout.didTimeout()) {
      await reader.cancel().catch(() => undefined);
    }
    if (!sawDone && !aborted) {
      callbacks.onDone?.();
    }
  }

  return { completed: sawDone, aborted, timedOut: timeout.didTimeout(), errorMessage };
}

export async function streamAdminRequest<T>(
  path: string,
  body: Record<string, unknown>,
  callbacks: AdminSSECallbacks<T>,
  options?: {
    signal?: AbortSignal;
  },
): Promise<AdminStreamResult> {
  return streamAdminEvents(path, callbacks, {
    method: "POST",
    body,
    signal: options?.signal,
  });
}

export async function getGenerationTask(taskId: string): Promise<AdminGenerationTaskSummary> {
  return workshopFetch<AdminGenerationTaskSummary>(`/api/workshop/generation-tasks/${taskId}`);
}
