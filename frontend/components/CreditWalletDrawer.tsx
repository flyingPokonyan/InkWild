"use client";

import { useTranslations } from "next-intl";

import { CreditWalletView } from "@/components/CreditWalletView";
import { PlayOverlayDrawer } from "@/components/PlayOverlayDrawer";
import { Drawer } from "@/components/ui/Drawer";
import type { CreditScope } from "@/lib/credits";

/**
 * 可控的积分抽屉。容器按 scope 选：
 * - "all"（非 play）：底部 sheet（沿用通用 Drawer），标题「我的积分」
 * - "session"（play）：复用案件板 overlay 形态，标题「本局积分」
 * 内容统一是 CreditWalletView，保证移动端/桌面一致。
 */
export function CreditWalletDrawer({
  open,
  onClose,
  scope,
  sessionId,
}: {
  open: boolean;
  onClose: () => void;
  scope: CreditScope;
  sessionId?: string;
}) {
  const t = useTranslations("credits");

  if (scope === "session") {
    return (
      <PlayOverlayDrawer open={open} onClose={onClose} title={t("sessionTitle")}>
        <CreditWalletView scope="session" sessionId={sessionId} />
      </PlayOverlayDrawer>
    );
  }

  return (
    <Drawer open={open} onClose={onClose} title={t("title")}>
      <CreditWalletView scope="all" />
    </Drawer>
  );
}
