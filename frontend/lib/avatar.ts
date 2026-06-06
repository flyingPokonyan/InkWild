// 头像选择的前端校验 + 读取（与后端 /api/auth/me/avatar 的限制对齐：PNG/JPEG/WebP，≤ 2MB）。

export const AVATAR_MAX_BYTES = 2 * 1024 * 1024;
export const AVATAR_TYPES = ["image/png", "image/jpeg", "image/webp"];

export type AvatarFileError = "type" | "size";

export function validateImageFile(file: File): AvatarFileError | null {
  if (!AVATAR_TYPES.includes(file.type)) return "type";
  if (file.size > AVATAR_MAX_BYTES) return "size";
  return null;
}

export function readAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(new Error("read failed"));
    reader.readAsDataURL(file);
  });
}
