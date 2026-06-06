/**
 * 真实 LLM provider 品牌 logo 映射。
 * SVG 文件存放在 /public/providers/，从 lobehub/lobe-icons 抓的。
 * 没匹配上的 provider 在 UI 上回退到首字母 chip。
 */

// 关键词 → icon 文件名（注意顺序：更具体的关键词先于通用的）
const ICON_RULES: Array<[RegExp, string]> = [
  [/deepseek/i, "deepseek"],
  [/claude|anthropic/i, "claude"],
  [/(^|[^a-z])(gpt|openai|chatgpt|o\d|gpt-?image)/i, "openai"],
  [/gemini/i, "gemini"],
  [/grok|x\.?ai/i, "grok"],
  [/qwen|通义|aliyun|dashscope/i, "qwen"],
  [/doubao|豆包|seedream|bytedance/i, "doubao"],
  [/moonshot|kimi|月之暗面/i, "moonshot"],
  [/zhipu|glm|智谱/i, "zhipu"],
  [/baichuan|百川/i, "baichuan"],
  [/mistral/i, "mistral"],
  [/llama|meta-?ai/i, "meta"],
  [/spark|讯飞|iflytek/i, "spark"],
  [/hunyuan|混元|tencent/i, "hunyuan"],
  [/minimax|abab/i, "minimax"],
  [/stepfun|step-/i, "stepfun"],
  [/(^|[^a-z])yi[-\d]/i, "yi"],
  [/google/i, "google"],
];

// provider_type 兜底（用户 provider 名字可能怪，但 type 是结构化的）
const TYPE_FALLBACK: Record<string, string> = {
  xai: "grok",
  gemini: "gemini",
  seedream_image: "doubao",
  // openai_compatible 不兜底 —— 它太通用，需要从 name 推断
};

export function resolveProviderIcon(
  name: string | null | undefined,
  providerType?: string | null,
): string | null {
  const haystack = `${name || ""} ${providerType || ""}`;
  for (const [pattern, file] of ICON_RULES) {
    if (pattern.test(haystack)) return `/providers/${file}.svg`;
  }
  if (providerType && TYPE_FALLBACK[providerType]) {
    return `/providers/${TYPE_FALLBACK[providerType]}.svg`;
  }
  return null;
}
