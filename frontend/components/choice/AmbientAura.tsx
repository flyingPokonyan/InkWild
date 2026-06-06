"use client";

/**
 * 中央径向呼吸光 + edge vignette 的氛围层。
 *
 * 三屏共用：GameLoadingScreen / GenerationLoadingScreen / ChoiceScene。
 * 月光白色相（ink 系），不引入 accent；7s 循环；prefers-reduced-motion 命中停动画。
 *
 * 自身 absolute inset:0 pointer-events:none，需要由外层定 position: relative 容器承接。
 */

export function AmbientAura() {
  return (
    <>
      <div className="lv-ambient-aura" aria-hidden />
      <div className="lv-ambient-vignette" aria-hidden />

      <style>{`
        .lv-ambient-aura {
          position: absolute;
          inset: 0;
          pointer-events: none;
          background: radial-gradient(
            ellipse 60% 45% at 50% 38%,
            rgba(232, 227, 216, 0.06) 0%,
            rgba(232, 227, 216, 0.02) 35%,
            rgba(0, 0, 0, 0) 60%
          );
          animation: lv-ambient-aura-breathe 7000ms cubic-bezier(0.4, 0, 0.4, 1) infinite;
        }
        @keyframes lv-ambient-aura-breathe {
          0%, 100% { opacity: 0.55; transform: scale(0.96); }
          50%      { opacity: 0.95; transform: scale(1.04); }
        }
        .lv-ambient-vignette {
          position: absolute;
          inset: 0;
          pointer-events: none;
          background: radial-gradient(
            ellipse at center,
            rgba(0, 0, 0, 0) 60%,
            rgba(0, 0, 0, 0.40) 100%
          );
        }

        @media (prefers-reduced-motion: reduce) {
          .lv-ambient-aura { animation: none; opacity: 0.75; transform: scale(1); }
        }
      `}</style>
    </>
  );
}
