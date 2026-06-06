import { useQuery } from "@tanstack/react-query";

import { ApiError, apiFetch } from "./api";
import type { CurrentUser } from "./types";

export async function fetchMe(): Promise<CurrentUser | null> {
  try {
    return await apiFetch<CurrentUser | null>("/api/auth/me");
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) return null;
    throw err;
  }
}

/**
 * 统一 me 缓存读取。AuthGate / Sidebar / UserDrawer 都用它。
 * 共用 queryKey + queryFn → TanStack 自动去重，全 admin 站只发一次 /api/auth/me。
 */
export function useMe() {
  return useQuery<CurrentUser | null>({
    queryKey: ["auth", "me"],
    queryFn: fetchMe,
    staleTime: 5 * 60_000,
    retry: false,
  });
}
