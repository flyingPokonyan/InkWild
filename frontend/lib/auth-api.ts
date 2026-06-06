import { apiFetch, apiURL } from "@/lib/api";
import type { CurrentUserDTO } from "@/lib/types";

export type AuthProvider = "google" | "linuxdo";

export interface RegisterResult {
  pending_verification: boolean;
  email: string;
}

export function oauthStartUrl(provider: AuthProvider, nextPath: string): string {
  return apiURL(`/api/auth/oauth/${provider}/start?next=${encodeURIComponent(nextPath)}`);
}

export async function registerWithPassword(input: {
  email: string;
  password: string;
  nickname?: string;
}): Promise<RegisterResult> {
  return apiFetch<RegisterResult>("/api/auth/register", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function requestPasswordReset(email: string): Promise<void> {
  await apiFetch<void>("/api/auth/password/forgot", {
    method: "POST",
    body: JSON.stringify({ email }),
  });
}

export async function resendVerification(email: string): Promise<void> {
  await apiFetch<void>("/api/auth/resend-verification", {
    method: "POST",
    body: JSON.stringify({ email }),
  });
}

export async function updateProfile(input: { nickname?: string }): Promise<CurrentUserDTO> {
  return apiFetch<CurrentUserDTO>("/api/auth/me", {
    method: "PATCH",
    body: JSON.stringify(input),
  });
}

// dataUrl: FileReader.readAsDataURL 的结果（data:image/png;base64,...）。
export async function uploadAvatar(dataUrl: string): Promise<CurrentUserDTO> {
  return apiFetch<CurrentUserDTO>("/api/auth/me/avatar", {
    method: "POST",
    body: JSON.stringify({ image: dataUrl }),
  });
}

export async function changePassword(input: { oldPassword: string; newPassword: string }): Promise<void> {
  await apiFetch<void>("/api/auth/password/change", {
    method: "POST",
    body: JSON.stringify({ old_password: input.oldPassword, new_password: input.newPassword }),
  });
}

export async function resetPassword(input: { token: string; newPassword: string }): Promise<void> {
  await apiFetch<void>("/api/auth/password/reset", {
    method: "POST",
    body: JSON.stringify({ token: input.token, new_password: input.newPassword }),
  });
}

export async function verifyEmail(token: string): Promise<CurrentUserDTO> {
  return apiFetch<CurrentUserDTO>("/api/auth/verify-email", {
    method: "POST",
    body: JSON.stringify({ token }),
  });
}
