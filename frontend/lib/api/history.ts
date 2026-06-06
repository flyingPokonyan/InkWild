/**
 * Game history 数据获取 — TanStack Query 封装。
 * v2.2 §14.4 基础设施层：替掉 useEffect + apiFetch + active flag 模板。
 */

import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "@/lib/api";
import type { GameHistoryItem } from "@/lib/types";

export const gameHistoryQueryKeys = {
  all: ["game-history"] as const,
};

export function fetchGameHistory(): Promise<GameHistoryItem[]> {
  return apiFetch<GameHistoryItem[]>("/api/game/history");
}

// 在历史页主动「结束」一局进行中的对局：status→ended, ending_type=abandoned。
// 复用后端 /abandon（与暂停页「放弃这局」同一端点）。调用方负责失效 history 缓存。
export function abandonGameSession(sessionId: string): Promise<void> {
  return apiFetch<void>(`/api/game/${sessionId}/abandon`, { method: "POST" });
}

export function useGameHistory() {
  return useQuery({
    queryKey: gameHistoryQueryKeys.all,
    queryFn: fetchGameHistory,
    retry: false,
  });
}
