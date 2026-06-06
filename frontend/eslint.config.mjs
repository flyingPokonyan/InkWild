import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

/**
 * v2.2 ESLint — 简化版（2026-05-09）
 *
 * 设计哲学：spec 是参考、不是律法。视觉决定还给设计师（jie）的眼睛，
 * 不靠机器拦字号/间距/圆角。**只剩一条硬规则**：禁止引用旧 token
 * （--ta-*、--color-accent、--font-size-*），防止 stage 5e 之后漂回旧系统。
 *
 * 之前钉死的 `text-[Xrem]` / `gap-5/7/9/10/11` / `z-[\d` / `rounded-[`
 * / inline `fontSize` 数字 等规则全部解锁——你想用 `text-[0.85rem]`
 * 因为视觉合适，那就用。lv-t-* 工具类仍然存在但不强制。
 */
const v22Restrictions = {
  rules: {
    "no-restricted-syntax": [
      "error",
      {
        selector: "Literal[value=/var\\(--(?:font-size-|ta-|color-accent)/]",
        message:
          "禁引用旧 token（--font-size-* / --ta-* / --color-accent）。统一用 var(--lv-*)。",
      },
    ],
  },
};

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  globalIgnores([
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
    "eslint.config.mjs",
  ]),
  v22Restrictions,
]);

export default eslintConfig;
