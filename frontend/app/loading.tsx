import { LoadingPulse } from "@/components/ui/LoadingPulse";

/**
 * 路由级 Suspense fallback · App Router 顶层
 *
 * 任何路由段的 server-side awaiting 期间显示。
 * 大多数页面用 useQuery（客户端获数）不会触发这个，
 * 但 server component / route loading 会用到。
 *
 * 视觉：暗底 + 中央 Branch + Grow（§10.1）。
 */
export default function Loading() {
  return (
    <div
      className="lv-theme"
      style={{
        minHeight: "100dvh",
        display: "grid",
        placeItems: "center",
        background: "var(--lv-bg)",
      }}
    >
      <LoadingPulse variant="block" />
    </div>
  );
}
