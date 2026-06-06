import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * 合并 Tailwind class，处理冲突。shadcn 风格 cn 工具。
 * 先 clsx 拼接（处理条件类），再 twMerge 解决冲突（同 group 后值赢）。
 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
