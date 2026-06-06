import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { apiFetch } from "./api";

// ---------- 类型 ----------

export type NotificationType =
  | "signup_grant"
  | "review_approved"
  | "review_rejected"
  | "content_takedown"
  | "content_restored"
  | "low_credit"
  | string;

export interface NotificationItem {
  id: string;
  type: NotificationType;
  title: string;
  body: string | null;
  link: string | null;
  payload: Record<string, unknown> | null;
  read_at: string | null;
  created_at: string;
}

export type AnnouncementLevel = "info" | "warning" | "critical" | string;

export interface AnnouncementItem {
  id: string;
  title: string;
  body: string;
  level: AnnouncementLevel;
  published_at: string | null;
  read: boolean;
}

export interface NotificationSummary {
  notifications: number;
  announcements: number;
}

interface NotificationPage {
  items: NotificationItem[];
  next_before: string | null;
}
interface AnnouncementPage {
  items: AnnouncementItem[];
  next_before: string | null;
}

// ---------- query keys ----------

export const NOTIF_SUMMARY_KEY = ["notif", "summary"] as const;
export const NOTIF_LIST_KEY = ["notif", "list"] as const;
export const ANN_LIST_KEY = ["notif", "announcements"] as const;

// ---------- API ----------

export const fetchSummary = () => apiFetch<NotificationSummary>("/api/notifications/summary");

const fetchNotifications = (before?: string | null) =>
  apiFetch<NotificationPage>(`/api/notifications${before ? `?before=${encodeURIComponent(before)}` : ""}`);

const fetchAnnouncements = (before?: string | null) =>
  apiFetch<AnnouncementPage>(`/api/announcements${before ? `?before=${encodeURIComponent(before)}` : ""}`);

const postNotificationRead = (id: string) =>
  apiFetch<unknown>(`/api/notifications/${id}/read`, { method: "POST" });
const postNotificationsReadAll = () =>
  apiFetch<unknown>("/api/notifications/read-all", { method: "POST" });
const postAnnouncementRead = (id: string) =>
  apiFetch<unknown>(`/api/announcements/${id}/read`, { method: "POST" });
const postAnnouncementsReadAll = () =>
  apiFetch<unknown>("/api/announcements/read-all", { method: "POST" });

// ---------- helpers ----------

export const totalUnread = (s: NotificationSummary | undefined): number =>
  s ? s.notifications + s.announcements : 0;

export const badgeText = (n: number): string => (n > 99 ? "99+" : String(n));

// ---------- hooks ----------

/** 铃铛角标：轮询未读汇总。仅登录态启用。 */
export function useNotificationSummary(enabled: boolean) {
  return useQuery({
    queryKey: NOTIF_SUMMARY_KEY,
    queryFn: fetchSummary,
    enabled,
    refetchInterval: 45_000,
    refetchOnWindowFocus: true,
    staleTime: 20_000,
  });
}

/** 个人通知列表，打开弹窗时才拉。 */
export function useNotifications(enabled: boolean) {
  return useInfiniteQuery({
    queryKey: NOTIF_LIST_KEY,
    queryFn: ({ pageParam }) => fetchNotifications(pageParam),
    enabled,
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_before,
  });
}

/** 系统公告列表。 */
export function useAnnouncements(enabled: boolean) {
  return useInfiniteQuery({
    queryKey: ANN_LIST_KEY,
    queryFn: ({ pageParam }) => fetchAnnouncements(pageParam),
    enabled,
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_before,
  });
}

/** 标记已读（单条 / 全部，通知 / 公告）。成功后刷新汇总与列表。 */
export function useMarkRead() {
  const qc = useQueryClient();
  const invalidate = () => {
    qc.invalidateQueries({ queryKey: NOTIF_SUMMARY_KEY });
    qc.invalidateQueries({ queryKey: NOTIF_LIST_KEY });
    qc.invalidateQueries({ queryKey: ANN_LIST_KEY });
  };
  return {
    notification: useMutation({ mutationFn: postNotificationRead, onSuccess: invalidate }),
    notificationsAll: useMutation({ mutationFn: postNotificationsReadAll, onSuccess: invalidate }),
    announcement: useMutation({ mutationFn: postAnnouncementRead, onSuccess: invalidate }),
    announcementsAll: useMutation({ mutationFn: postAnnouncementsReadAll, onSuccess: invalidate }),
  };
}
