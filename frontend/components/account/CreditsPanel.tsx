"use client";

import { useQuery } from "@tanstack/react-query";
import { Coins } from "lucide-react";
import { useTranslations } from "next-intl";

import { CreditLedger } from "@/components/CreditWalletView";
import { CREDIT_BALANCE_QUERY_KEY, balanceTone, creditLevel, fetchCreditBalance, fmtCredits } from "@/lib/credits";

/**
 * 积分内容：余额 Hero（大号普通数字 + 累计获得/消耗 + 充值）+ 全部流水。
 * PC 账户中心右侧 与 移动 /me/credits 页共用，避免余额数字重复出现。
 * @param heading 传入则渲染页内大标题（PC 用）；移动端靠顶栏已有标题，不传。
 */
export function CreditsPanel({ heading }: { heading?: string }) {
  const t = useTranslations("account");
  const tc = useTranslations("credits");

  const { data: balance } = useQuery({
    queryKey: CREDIT_BALANCE_QUERY_KEY,
    queryFn: fetchCreditBalance,
    staleTime: 30_000,
  });
  const level = creditLevel(balance?.balance);
  const palette = balanceTone(level);
  const balanceColor = level === "normal" ? "var(--lv-ink)" : palette.color;

  return (
    <div className="crp">
      {heading && <h1 className="crp-title">{heading}</h1>}

      <div className="crp-asset">
        <div className="crp-hero">
          <div className="crp-hero-main">
            <div className="lv-t-caps crp-hero-label">{t("balanceLabel")}</div>
            <div className="crp-balance">
              <span className="crp-balance-num" style={{ color: balanceColor }}>
                {balance ? fmtCredits(balance.balance) : "—"}
              </span>
              <span className="crp-balance-unit">{tc("unit")}</span>
            </div>
          </div>
          <button type="button" className="crp-topup" title={t("soon")} disabled>
            <Coins size={14} />
            {t("topup")}
            <span className="crp-soon">{t("soon")}</span>
          </button>
        </div>

        <div className="crp-stats">
          <div className="crp-stat">
            <span className="crp-stat-num">{balance ? fmtCredits(balance.lifetime_granted) : "—"}</span>
            <span className="lv-t-caps crp-stat-label">{tc("lifetimeGranted")}</span>
          </div>
          <div className="crp-stat">
            <span className="crp-stat-num">{balance ? fmtCredits(balance.lifetime_spent) : "—"}</span>
            <span className="lv-t-caps crp-stat-label">{tc("lifetimeSpent")}</span>
          </div>
        </div>
      </div>

      <CreditLedger scope="all" />

      <style jsx global>{`
        .crp-title {
          margin: 0 0 22px;
          font-family: var(--lv-font-serif);
          font-size: clamp(26px, 3vw, 32px);
          font-weight: 500;
          letter-spacing: -0.01em;
          color: var(--lv-ink);
        }
        .crp-asset {
          overflow: hidden;
          border-radius: var(--lv-r-card);
          border: 1px solid var(--lv-line);
          background:
            linear-gradient(180deg, rgba(255, 255, 255, 0.024), rgba(255, 255, 255, 0.012)),
            var(--lv-bg);
        }
        .crp-hero {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 16px;
          padding: 20px 22px 18px;
        }
        .crp-hero-label {
          color: var(--lv-ink-3);
        }
        .crp-balance {
          margin-top: 7px;
          display: flex;
          align-items: baseline;
          gap: 8px;
        }
        .crp-balance-num {
          font-size: 32px;
          font-weight: 560;
          line-height: 1;
          font-variant-numeric: tabular-nums;
          letter-spacing: 0;
        }
        .crp-balance-unit {
          font-size: 12px;
          color: var(--lv-ink-3);
        }
        .crp-topup {
          flex-shrink: 0;
          display: inline-flex;
          align-items: center;
          gap: 7px;
          height: 36px;
          padding: 0 13px;
          border-radius: var(--lv-r-pill);
          background: rgba(255, 255, 255, 0.018);
          border: 1px solid rgba(255, 255, 255, 0.075);
          color: rgba(196, 188, 174, 0.46);
          font-size: var(--lv-t-meta);
          font-weight: 500;
          cursor: not-allowed;
          box-shadow: none;
        }
        .crp-soon {
          font-family: var(--lv-font-mono);
          font-size: var(--lv-t-micro);
          letter-spacing: 0.08em;
          text-transform: uppercase;
          color: rgba(140, 130, 115, 0.72);
          padding-left: 6px;
          border-left: 1px solid rgba(255, 255, 255, 0.07);
        }
        .crp-stats {
          display: grid;
          grid-template-columns: 1fr 1fr;
          border-top: 1px solid rgba(255, 255, 255, 0.052);
        }
        .crp-stat {
          display: flex;
          flex-direction: column;
          gap: 4px;
          padding: 13px 22px 15px;
        }
        .crp-stat + .crp-stat {
          border-left: 1px solid rgba(255, 255, 255, 0.052);
        }
        .crp-stat-num {
          font-size: 16px;
          font-weight: 560;
          color: var(--lv-ink-2);
          line-height: 1;
          font-variant-numeric: tabular-nums;
        }
        .crp-stat-label {
          color: var(--lv-ink-3);
        }
        @media (max-width: 768px) {
          .crp-hero {
            flex-direction: column;
            align-items: stretch;
            gap: 14px;
            padding: 18px;
          }
          .crp-balance-num {
            font-size: 28px;
          }
          .crp-topup {
            justify-content: center;
            height: 44px;
            width: 100%;
          }
        }
      `}</style>
    </div>
  );
}
