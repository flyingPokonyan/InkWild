import { AmbientAura } from "@/components/choice/AmbientAura";
import { LoadingPulse } from "@/components/ui/LoadingPulse";

/**
 * /play/[id] 路由段 loading fallback。
 *
 * 方案 A：入场等待全程在 setup 页用 GameLoadingScreen 展示，内容就绪才跳到这里，落地即进舞台。
 * 但 router.push 瞬间该路由段 RSC 仍可能闪一帧 —— 用与 GameLoadingScreen 同款的黑底 +
 * AmbientAura + LoadingPulse 兜底，保证与前一屏视觉连续，不再露出 app/loading.tsx 那个没有
 * 氛围光的裸 pulse。从历史恢复（resume）进入 play 的导航同样受益。
 */
export default function PlayLoading() {
  return (
    <div
      className="lv-theme relative flex min-h-dvh w-full flex-col items-center justify-center overflow-hidden"
      style={{ background: "var(--lv-bg)" }}
    >
      <AmbientAura />
      <div className="relative z-10">
        <LoadingPulse variant="block" label="" />
      </div>
    </div>
  );
}
