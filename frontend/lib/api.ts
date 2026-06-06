import type { ApiEnvelope, ApiErrorDetail } from "./types";

// 浏览器、以及任何要交给浏览器消费的 URL（apiURL）用公网/localhost 地址。
// 服务端（SSR / RSC 预取）实际发请求时直连后端容器：Docker 内 localhost 不通后端，
// 须用 INTERNAL_API_URL（非 NEXT_PUBLIC_ 前缀，浏览器读不到，会回退到 PUBLIC_API_BASE）。
const PUBLIC_API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const SERVER_API_BASE = process.env.INTERNAL_API_URL || PUBLIC_API_BASE;

function fetchBase(): string {
  return typeof window === "undefined" ? SERVER_API_BASE : PUBLIC_API_BASE;
}

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

function extractErrorCode(payload: unknown): number | undefined {
  if (!payload || typeof payload !== "object") {
    return undefined;
  }

  const response = payload as {
    code?: number;
    detail?: ApiErrorDetail;
  };

  return response.code || response.detail?.code;
}

export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError;
}

export function isUnauthorizedError(error: unknown): boolean {
  return isApiError(error) && error.status === 401;
}

export async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const headers = new Headers(options?.headers);
  const hasBody = options?.body !== undefined;

  if (hasBody && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${fetchBase()}${path}`, {
    cache: "no-store",
    credentials: "include",
    ...options,
    headers,
  });

  const payload = (await response.json().catch(() => null)) as ApiEnvelope<T> | null;

  if (!response.ok) {
    throw new ApiError(
      buildErrorMessage(payload, "请求失败"),
      response.status,
      extractErrorCode(payload),
    );
  }

  if (payload && typeof payload.code === "number") {
    if (payload.code !== 0) {
      throw new ApiError(payload.message || "请求失败", response.ok ? 400 : response.status, payload.code);
    }
    return payload.data;
  }

  return payload as T;
}

export function apiURL(path: string): string {
  return `${PUBLIC_API_BASE}${path}`;
}
