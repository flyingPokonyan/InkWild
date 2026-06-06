"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";

import { gameHistoryQueryKeys } from "@/lib/api/history";
import { getQueryClient } from "@/lib/query-client";
import { useConfirm } from "@/components/ui/ConfirmDialog";
import { useGameStore } from "@/stores/game";

interface PauseOverlayProps {
  sessionId: string;
  onResume: () => void;
  /** 退出落点：来自 ?return=（工坊试玩等），缺省回首页。 */
  exitHref?: string;
}

export function PauseOverlay({ sessionId, onResume, exitHref = "/" }: PauseOverlayProps) {
  const router = useRouter();
  const reset = useGameStore((s) => s.reset);
  const endGame = useGameStore((s) => s.endGame);
  const t = useTranslations("play");
  const confirm = useConfirm();

  const handlePause = async () => {
    try {
      await fetch(`/api/game/${sessionId}/pause`, { method: "POST", credentials: "include" });
    } catch {
      // pause API 失败也别把用户卡在弹窗里 —— 进度后端早写好了，
      // 强制清本地态 + 回首页，下次能从历史里恢复。
    }
    getQueryClient().invalidateQueries({ queryKey: gameHistoryQueryKeys.all });
    reset();
    router.push(exitHref);
  };

  const handleEnd = async () => {
    const ok = await confirm({
      title: "结束这一局？",
      message: "会为你生成一段落幕收场，结束后可在历史里回顾。",
      confirmText: "结束并落幕",
      cancelText: "继续游戏",
    });
    if (!ok) return;
    // 关闭暂停浮层，露出落幕动画；endGame 负责生成落幕白 → ending 事件 → 结局页。
    onResume();
    void endGame();
  };

  return (
    <div
      className="lv-theme fixed inset-0 flex items-center justify-center"
      style={{
        zIndex: "var(--lv-z-overlay)" as unknown as number,
        background: "rgba(6, 6, 10, 0.65)",
        backdropFilter: "blur(16px) saturate(120%)",
        WebkitBackdropFilter: "blur(16px) saturate(120%)",
      }}
    >
      <div
        className="text-center"
        style={{
          maxWidth: 360,
          padding: "var(--lv-s-6) var(--lv-s-4)",
          display: "flex",
          flexDirection: "column",
          gap: "var(--lv-s-6)",
        }}
      >
        <div className="lv-t-caps" style={{ color: "var(--lv-ink-3)" }}>
          {t("pauseTitle")}
        </div>
        <p className="lv-t-body-long" style={{ color: "var(--lv-ink-2)" }}>
          {t("pauseDesc")}
        </p>
        <div className="flex flex-col gap-3 sm:flex-row sm:justify-center sm:flex-wrap">
          <button
            type="button"
            onClick={onResume}
            className="lv-btn lv-btn-primary"
          >
            {t("resume")}
          </button>
          <button
            type="button"
            onClick={handlePause}
            className="lv-btn"
          >
            {t("leaveSave")}
          </button>
          <button
            type="button"
            onClick={handleEnd}
            className="lv-btn"
            style={{ color: "var(--lv-ink-3)" }}
          >
            结束这局
          </button>
        </div>
      </div>
    </div>
  );
}
