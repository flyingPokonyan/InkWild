import type {
  ModelCapability,
  ModelKind,
  ModelProviderStatus,
  ModelProviderType,
  ProviderModelStatus,
} from "@/lib/types";
import { parseBackendIso } from "@/lib/datetime";

export const PROVIDER_TYPE_LABELS: Record<ModelProviderType, string> = {
  openai_compatible: "OpenAI 兼容",
  xai: "xAI / Grok",
  gemini: "Gemini",
  seedream_image: "Seedream 生图",
};

export const PROVIDER_TYPE_HINTS: Record<ModelProviderType, string> = {
  openai_compatible: "适合 DeepSeek、OpenRouter、自建 OpenAI 兼容网关。",
  xai: "同一平台下可挂文本与生图模型，也可验证 web search。",
  gemini: "按 Gemini OpenAI 兼容入口接入，文本与生图模型分开配置。",
  seedream_image: "只用于图片模型，不会出现在文本槽位候选里。",
};

export const PROVIDER_TYPE_MARKS: Record<ModelProviderType, string> = {
  openai_compatible: "AI",
  xai: "X",
  gemini: "G",
  seedream_image: "S",
};

export const PROVIDER_TYPE_DEFAULT_BASE_URL: Record<ModelProviderType, string> = {
  openai_compatible: "",
  xai: "https://api.x.ai/v1",
  gemini: "https://generativelanguage.googleapis.com/v1beta/openai",
  seedream_image: "",
};

export const PROVIDER_TYPE_KEY_HINT: Record<ModelProviderType, string> = {
  openai_compatible: "e.g. DEEPSEEK_API_KEY",
  xai: "e.g. XAI_API_KEY",
  gemini: "e.g. GEMINI_API_KEY",
  seedream_image: "e.g. SEEDREAM_API_KEY",
};

export const MODEL_KIND_LABELS: Record<ModelKind, string> = {
  text: "文本",
  image: "生图",
};

export const CAPABILITY_LABELS: Record<ModelCapability, string> = {
  chat_basic: "基础对话",
  streaming: "流式输出",
  tool_use: "Tool Use",
  json_output: "JSON 输出",
  image_generation: "图片生成",
  web_search: "联网搜索",
};

export const CAPABILITY_ICON_PATHS: Record<ModelCapability, string> = {
  chat_basic: "M3 5h14v8H8l-3 3v-3H3z",
  streaming: "M3 6h10M3 10h14M3 14h8",
  tool_use: "M8 3 5 6l3 3M12 3l3 3-3 3M5 14h10",
  json_output: "M7 3a4 4 0 0 0-4 4v6a4 4 0 0 0 4 4M13 3a4 4 0 0 1 4 4v6a4 4 0 0 1-4 4",
  image_generation: "M3 4h14v12H3zM3 13l4-4 3 3 3-3 4 4",
  web_search: "M2 10s3-5 8-5 8 5 8 5-3 5-8 5-8-5-8-5z M10 7.5a2.5 2.5 0 1 0 0 5 2.5 2.5 0 0 0 0-5z",
};

export const CAPABILITY_GROUPS: Record<ModelKind, ModelCapability[]> = {
  text: ["chat_basic", "streaming", "json_output", "tool_use", "web_search"],
  image: ["image_generation"],
};

export function statusPillClass(status: ProviderModelStatus | ModelProviderStatus | string): string {
  if (status === "ready" || status === "active") {
    return "text-emerald-300 bg-emerald-400/10 border-emerald-400/20";
  }
  if (status === "partial") return "text-amber-200 bg-amber-400/10 border-amber-400/20";
  if (status === "failed" || status === "invalid") {
    return "text-red-300 bg-red-400/10 border-red-400/20";
  }
  if (status === "disabled") return "text-white/40 bg-white/[0.04] border-white/10";
  return "text-white/60 bg-white/5 border-white/10";
}

export function statusLabel(status: ProviderModelStatus | ModelProviderStatus): string {
  const map: Record<string, string> = {
    active: "启用",
    disabled: "停用",
    invalid: "失效",
    ready: "就绪",
    partial: "部分",
    failed: "失败",
    unverified: "待验证",
  };
  return map[status] ?? status;
}

export function formatDateTime(value?: string | null): string {
  if (!value) return "—";
  const d = parseBackendIso(value);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString("zh-CN", { hour12: false });
}

export function parseJsonObject(value: string): Record<string, unknown> {
  const trimmed = value.trim();
  if (!trimmed) return {};
  const parsed = JSON.parse(trimmed) as unknown;
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("额外配置必须是 JSON 对象");
  }
  return parsed as Record<string, unknown>;
}
