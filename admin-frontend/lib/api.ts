const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  code?: number;

  constructor(message: string, status: number, code?: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

interface ApiEnvelope<T> {
  code: number;
  data: T;
  message?: string;
}

interface ApiErrorDetail {
  code?: number;
  message?: string;
}

function extractMessage(payload: unknown, fallback: string): string {
  if (!payload || typeof payload !== "object") return fallback;
  const r = payload as { message?: string; detail?: ApiErrorDetail };
  return r.detail?.message || r.message || fallback;
}

function extractCode(payload: unknown): number | undefined {
  if (!payload || typeof payload !== "object") return undefined;
  const r = payload as { code?: number; detail?: ApiErrorDetail };
  return r.code ?? r.detail?.code;
}

export async function apiFetch<T>(
  path: string,
  options?: RequestInit,
): Promise<T> {
  const headers = new Headers(options?.headers);
  if (options?.body !== undefined && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const res = await fetch(`${API_BASE}${path}`, {
    cache: "no-store",
    credentials: "include",
    ...options,
    headers,
  });

  const payload = (await res.json().catch(() => null)) as
    | ApiEnvelope<T>
    | null;

  if (!res.ok) {
    throw new ApiError(
      extractMessage(payload, "请求失败"),
      res.status,
      extractCode(payload),
    );
  }

  if (payload && typeof payload.code === "number") {
    if (payload.code !== 0) {
      throw new ApiError(
        payload.message || "请求失败",
        res.status,
        payload.code,
      );
    }
    return payload.data;
  }

  return payload as T;
}

export function apiUrl(path: string): string {
  return `${API_BASE}${path}`;
}
