import { useMutation, useQuery } from "@tanstack/react-query";

import { apiFetch } from "./api";

export type FeedbackCategory = "bug" | "suggestion";

export interface FeedbackEvent {
  kind: "status" | "reply";
  status: string | null;
  body: string | null;
  created_at: string;
}

export interface FeedbackThread {
  id: string;
  category: FeedbackCategory | string;
  content: string;
  image_url: string | null;
  status: string;
  created_at: string;
  events: FeedbackEvent[];
}

export interface FeedbackPayload {
  category: FeedbackCategory;
  content: string;
  image?: string | null; // base64 data URL
  page_url?: string | null;
  contact?: string | null;
}

const submitFeedback = (payload: FeedbackPayload) =>
  apiFetch<{ id: string }>("/api/feedback", {
    method: "POST",
    body: JSON.stringify(payload),
  });

/** 提交反馈。成功后调用方自行关闭弹窗 / 提示。 */
export function useSubmitFeedback() {
  return useMutation({ mutationFn: submitFeedback });
}

/** 反馈线程（本体 + 时间线）。用于通知详情里展示「解决记录」全貌。 */
export function useFeedbackThread(feedbackId: string | null) {
  return useQuery({
    queryKey: ["feedback-thread", feedbackId],
    queryFn: () => apiFetch<FeedbackThread>(`/api/feedback/${feedbackId}`),
    enabled: !!feedbackId,
    staleTime: 10_000,
  });
}
