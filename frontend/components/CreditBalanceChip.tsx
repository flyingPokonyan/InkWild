"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Coins } from "lucide-react";
import { useTranslations } from "next-intl";

import { CreditWalletDrawer } from "@/components/CreditWalletDrawer";
import {
  CREDIT_BALANCE_QUERY_KEY,
  balanceTone,
  creditLevel,
  fetchCreditBalance,
  fmtCredits,
  type CreditScope,
} from "@/lib/credits";

interface CreditBalanceChipProps {
  // "chip" = 顶部栏中性药丸；"plain" = 无填充小号（Play 沉浸态）
  variant?: "chip" | "plain";
  // "all" = 我的积分（全部流水）；"session" = 本局积分（需 sessionId，play 用）
  scope?: CreditScope;
  sessionId?: string;
}

export function CreditBalanceChip({ variant = "chip", scope = "all", sessionId }: CreditBalanceChipProps = {}) {
  const t = useTranslations("credits");
  const [open, setOpen] = useState(false);

  const { data: balance } = useQuery({
    queryKey: CREDIT_BALANCE_QUERY_KEY,
    queryFn: fetchCreditBalance,
    staleTime: 30_000,
  });

  const level = creditLevel(balance?.balance);
  const palette = balanceTone(level);
  const isPlain = variant === "plain";
  const triggerTone =
    !isPlain && level === "normal"
      ? { color: "var(--lv-ink-2)", soft: "rgba(255, 255, 255, 0.055)", border: "rgba(255, 255, 255, 0.11)" }
      : palette;

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className={isPlain ? "credit-chip-plain" : "credit-chip"}
        title={scope === "session" ? t("sessionTitle") : t("title")}
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: isPlain ? "5px" : "6px",
          height: isPlain ? "28px" : "32px",
          padding: isPlain ? "0 4px" : "0 12px",
          borderRadius: "var(--lv-r-pill)",
          background: isPlain ? "transparent" : triggerTone.soft,
          border: isPlain ? "1px solid transparent" : `1px solid ${triggerTone.border}`,
          color: triggerTone.color,
          fontSize: isPlain ? "12.5px" : "13px",
          fontWeight: 600,
          cursor: "pointer",
          fontVariantNumeric: "tabular-nums",
          transition: "border-color 200ms ease, background 200ms ease, color 200ms ease",
        }}
      >
        <Coins size={isPlain ? 12 : 13} />
        <span>{balance ? fmtCredits(balance.balance) : "—"}</span>
      </button>

      <CreditWalletDrawer open={open} onClose={() => setOpen(false)} scope={scope} sessionId={sessionId} />

      <style jsx global>{`
        .credit-chip:hover {
          border-color: rgba(255, 255, 255, 0.2) !important;
          background: rgba(255, 255, 255, 0.1) !important;
        }
        .credit-chip-plain:hover {
          opacity: 0.72;
        }
      `}</style>
    </>
  );
}
