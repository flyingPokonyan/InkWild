/**
 * 难度等级钳制：把任意 difficulty 数值归一到 1–5，供 i18n `worlds.difficultyName`
 * 的 ICU select 使用（入门 / 轻度 / 适中 / 较难 / 高难）。
 * 用法：t("difficultyName", { level: difficultyLevel(value) })
 * 返回 "1"–"5" 字符串，对齐 ICU select 的字符串选择子。
 */
export function difficultyLevel(value: number): string {
  return String(Math.max(1, Math.min(5, Math.round(value || 0))));
}
