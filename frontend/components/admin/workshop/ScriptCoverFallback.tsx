"use client";

/**
 * 剧本无真实封面时的程序化占位。
 *
 * 设计取向：**安静、低权重**，不抢戏。
 * - 标题在卡片下方有，封面里不重复
 * - 仅一层 hash 调色 tint 渐变 + 一个左上角 ◆ 徽
 * - 视觉重量与世界真照片封面接近，不让剧本卡在并排时显"重"
 */

interface Props {
  name: string;
  /** 不再使用，保留 API 兼容；以后真封面来了直接走 img 不走 fallback */
  difficulty?: number;
  estimatedTime?: string;
}

const TINTS = [
  "rgba(201,180,138,0.12)",
  "rgba(127,176,145,0.10)",
  "rgba(184,92,92,0.10)",
  "rgba(120,140,175,0.10)",
  "rgba(155,130,180,0.10)",
  "rgba(201,165,106,0.10)",
];

function hashString(s: string): number {
  let h = 5381;
  for (let i = 0; i < s.length; i++) {
    h = ((h << 5) + h + s.charCodeAt(i)) | 0;
  }
  return Math.abs(h);
}

export function ScriptCoverFallback({ name }: Props) {
  const tint = TINTS[hashString(name || "?") % TINTS.length];

  return (
    <div
      aria-hidden
      style={{
        position: "absolute",
        inset: 0,
        backgroundColor: "var(--lv-bg-1)",
        backgroundImage: `radial-gradient(120% 90% at 0% 0%, ${tint} 0%, transparent 65%)`,
        display: "flex",
        padding: "var(--lv-s-3) var(--lv-s-4)",
      }}
    >
      <span
        className="lv-t-caps"
        style={{ color: "var(--lv-ink-4)", letterSpacing: "0.04em" }}
      >
        ◆
      </span>
    </div>
  );
}
