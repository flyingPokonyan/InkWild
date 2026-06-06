/**
 * Worlds 数据获取 — TanStack Query 封装。
 * v2.2 §14.4 基础设施层：替掉 useEffect + apiFetch + active flag 模板。
 */

import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "@/lib/api";
import type { WorldDetail, WorldListItem } from "@/lib/types";

export const worldsQueryKeys = {
  all: ["worlds"] as const,
  list: () => [...worldsQueryKeys.all, "list"] as const,
  detail: (id: string) => [...worldsQueryKeys.all, "detail", id] as const,
};

export function fetchWorldList(): Promise<WorldListItem[]> {
  return apiFetch<WorldListItem[]>("/api/worlds");
}

export function fetchWorldDetail(id: string): Promise<WorldDetail> {
  return apiFetch<WorldDetail>(`/api/worlds/${id}`);
}

export function useWorldList() {
  return useQuery({
    queryKey: worldsQueryKeys.list(),
    queryFn: fetchWorldList,
  });
}

export function useWorldDetail(id: string | undefined) {
  return useQuery({
    queryKey: worldsQueryKeys.detail(id || ""),
    queryFn: () => fetchWorldDetail(id as string),
    enabled: Boolean(id),
  });
}
