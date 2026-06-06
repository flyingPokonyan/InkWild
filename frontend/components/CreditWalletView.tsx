"use client";

import { useState } from "react";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";

import {
  CREDIT_BALANCE_QUERY_KEY,
  balanceTone,
  creditLevel,
  creditTxnsKey,
  creditTxnsSummaryKey,
  fetchCreditBalance,
  fetchCreditTransactions,
  fmtCredits,
  type CreditScope,
  type CreditTransaction,
} from "@/lib/credits";

// 流水翻页：每页 8 条，游标按需取下一批（翻全部，不限条数）。
// 翻到真正最后一页（本地无下一页且后端无更多）→「下一页」置灰，不会"一直点下一张"。
const PAGE_SIZE = 8;

type LedgerFilterKey = "all" | "play" | "creation" | "grantAdjust";

const LEDGER_FILTERS: {
  key: LedgerFilterKey;
  labelKey: "filterAll" | "filterPlay" | "filterCreation" | "filterGrantAdjust";
  category?: string;
}[] = [
  { key: "all", labelKey: "filterAll" },
  { key: "play", labelKey: "filterPlay", category: "play" },
  { key: "creation", labelKey: "filterCreation", category: "creation,image" },
  { key: "grantAdjust", labelKey: "filterGrantAdjust", category: "grant,adjust" },
];

function TxnRow({
  txn,
  t,
  isSession,
  locale,
}: {
  txn: CreditTransaction;
  t: ReturnType<typeof useTranslations>;
  isSession: boolean;
  locale: string;
}) {
  const zero = txn.delta === 0;
  const positive = txn.delta >= 0;
  const kindLabel = t(`kind.${txn.kind}`);
  const catLabel = txn.category ? t(`cat.${txn.category}`) : "";
  const time = formatTxnTime(txn.ts, locale);
  const turnLabel = txn.ref_turn ? t("turnN", { n: txn.ref_turn }) : "";

  // 主行 = 这条流水「是什么」；次行 = 限定词 · 时间（始终两段，避免次行只剩孤零零时间）。
  let title = kindLabel;
  let metaLead = catLabel;
  if (isSession) {
    // play 本局抽屉：世界/剧本对所有行都一样（冗余）。回合当主行；kind（游玩消耗 / 失败未扣费）
    // 作次行 lead，让每行看得出「这笔花在什么上」，信息量对齐「我的积分」明细。
    title = turnLabel || kindLabel;
    metaLead = turnLabel ? kindLabel : "";
  } else if (txn.ref_title) {
    const sub = txn.ref_subtitle ?? (txn.ref_mode === "free" ? t("freeMode") : null);
    title = sub ? `${txn.ref_title} · ${sub}` : txn.ref_title;
    // 游玩 → 回合数与时间结伴（第1回合 · 10:45）；生成 → 种类与时间结伴（生成世界 · 10:45）。
    metaLead = turnLabel || kindLabel;
  }
  const metaText = [metaLead, time].filter(Boolean).join(" · ");

  return (
    <div className="cw-txn">
      <div className="cw-txn-main">
        <div className="cw-txn-title">{title}</div>
        <div className="cw-txn-meta">{metaText}</div>
        {txn.note ? <div className="cw-txn-note">{txn.note}</div> : null}
      </div>
      <div className="cw-txn-side">
        {zero ? (
          <div className="cw-txn-zero">{t("notCharged")}</div>
        ) : (
          <div className={`cw-txn-delta${positive ? " is-positive" : ""}`}>
            {positive ? "+" : ""}
            {fmtCredits(txn.delta)}
          </div>
        )}
        <div className="cw-txn-balance">{fmtCredits(txn.balance_after)}</div>
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div style={{ color: "var(--lv-ink-3)", fontSize: "var(--lv-t-meta)" }}>{label}</div>
      <div
        style={{
          color: "var(--lv-ink)",
          fontSize: "15px",
          fontWeight: 600,
          marginTop: "3px",
          fontVariantNumeric: "tabular-nums",
        }}
      >
        {value}
      </div>
    </div>
  );
}

// 行内只显示「时:分」——日期交给上面的日期分组标题，避免重复。
function formatTxnTime(iso: string, locale: string): string {
  return new Date(iso).toLocaleTimeString(locale, { hour: "2-digit", minute: "2-digit" });
}

// 分组标题用清晰日期（zh「6月5日」/ en「June 5」），今年省略年份。
function formatTxnGroupDate(iso: string, locale: string): string {
  const date = new Date(iso);
  const now = new Date();
  const includeYear = date.getFullYear() !== now.getFullYear();
  return date.toLocaleDateString(locale, {
    year: includeYear ? "numeric" : undefined,
    month: "long",
    day: "numeric",
  });
}

function groupTransactions(items: CreditTransaction[], locale: string) {
  const groups: { key: string; label: string; items: CreditTransaction[] }[] = [];
  for (const item of items) {
    const date = new Date(item.ts);
    const key = `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}`;
    const last = groups[groups.length - 1];
    if (last?.key === key) {
      last.items.push(item);
    } else {
      groups.push({ key, label: formatTxnGroupDate(item.ts, locale), items: [item] });
    }
  }
  return groups;
}

interface CreditLedgerProps {
  scope: CreditScope;
  sessionId?: string;
}

/**
 * 积分流水列表（标题 + 行）。独立导出，供账户中心 / 积分页 / play 抽屉复用，
 * 不带余额 Hero —— 余额由各页自己渲染，避免重复。
 */
export function CreditLedger({ scope, sessionId }: CreditLedgerProps) {
  const t = useTranslations("credits");
  const locale = useLocale();
  const isSession = scope === "session";
  const [activeFilter, setActiveFilter] = useState<LedgerFilterKey>("all");
  const [page, setPage] = useState(0);
  const activeCategory = isSession
    ? undefined
    : LEDGER_FILTERS.find((filter) => filter.key === activeFilter)?.category;

  const {
    data,
    isLoading: txnsLoading,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useInfiniteQuery({
    queryKey: creditTxnsKey(scope, sessionId, activeCategory),
    queryFn: ({ pageParam }) =>
      fetchCreditTransactions({
        before: pageParam as string | undefined,
        ...(isSession ? { session: sessionId } : {}),
        ...(activeCategory ? { category: activeCategory } : {}),
      }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    enabled: !isSession || !!sessionId,
  });

  const items = data?.pages.flatMap((p) => p.items) ?? [];
  const pageItems = items.slice(page * PAGE_SIZE, page * PAGE_SIZE + PAGE_SIZE);
  const groups = groupTransactions(pageItems, locale);
  const hasLocalNext = (page + 1) * PAGE_SIZE < items.length;
  const canPrev = page > 0;
  const canNext = hasLocalNext || hasNextPage;

  const selectFilter = (key: LedgerFilterKey) => {
    setActiveFilter(key);
    setPage(0);
  };
  const goPrev = () => setPage((p) => Math.max(0, p - 1));
  const goNext = async () => {
    // 本地没攒够下一页且后端还有 → 先按需取下一批，再翻页。
    if (!hasLocalNext && hasNextPage) {
      await fetchNextPage();
    }
    setPage((p) => p + 1);
  };

  return (
    <div className="cw-ledger">
      <div className="cw-ledger-head">
        <div className="cw-ledger-title">
          <strong>{t("transactions")}</strong>
        </div>
        {!isSession && (
          <div className="cw-filter-row" aria-label={t("filterLabel")}>
            {LEDGER_FILTERS.map((filter) => {
              const selected = filter.key === activeFilter;
              return (
                <button
                  key={filter.key}
                  type="button"
                  className={`cw-filter-chip${selected ? " is-active" : ""}`}
                  aria-pressed={selected}
                  onClick={() => selectFilter(filter.key)}
                >
                  {t(filter.labelKey)}
                </button>
              );
            })}
          </div>
        )}
      </div>
      {txnsLoading ? (
        <div className="cw-ledger-state">{t("loading")}</div>
      ) : items.length > 0 ? (
        <>
          {groups.map((group) => (
            <div key={group.key}>
              <div className="cw-ledger-date">{group.label}</div>
              {group.items.map((txn) => (
                <TxnRow key={txn.id} txn={txn} t={t} isSession={isSession} locale={locale} />
              ))}
            </div>
          ))}
          {(canPrev || canNext) && (
            <div className="cw-pager">
              <button
                type="button"
                className="cw-pager-btn"
                onClick={goPrev}
                disabled={!canPrev || isFetchingNextPage}
                aria-label={t("prevPage")}
              >
                <ChevronLeft size={16} />
              </button>
              <span className="cw-pager-label">
                {isFetchingNextPage ? t("loading") : t("pageN", { n: page + 1 })}
              </span>
              <button
                type="button"
                className="cw-pager-btn"
                onClick={() => void goNext()}
                disabled={!canNext || isFetchingNextPage}
                aria-label={t("nextPage")}
              >
                <ChevronRight size={16} />
              </button>
            </div>
          )}
        </>
      ) : (
        <div className="cw-ledger-state">
          {isSession ? t("sessionEmpty") : t("empty")}
        </div>
      )}
      <style jsx global>{`
        .cw-ledger {
          overflow: hidden;
          margin-top: 20px;
          border-radius: var(--lv-r-card);
          border: 1px solid var(--lv-line);
          background: rgba(255, 255, 255, 0.015);
        }
        .cw-ledger-head {
          display: flex;
          flex-direction: column;
          gap: 11px;
          padding: 14px 16px;
          border-bottom: 1px solid var(--lv-line);
          background: rgba(255, 255, 255, 0.014);
        }
        .cw-ledger-title {
          display: flex;
          align-items: baseline;
          justify-content: space-between;
          gap: 12px;
        }
        .cw-ledger-title strong {
          color: var(--lv-ink);
          font-size: 15px;
          font-weight: 600;
        }
        .cw-ledger-title span {
          color: var(--lv-ink-3);
          font-size: 12px;
          font-variant-numeric: tabular-nums;
        }
        .cw-filter-row {
          display: flex;
          gap: 8px;
          overflow-x: auto;
          padding-bottom: 1px;
          scrollbar-width: none;
        }
        .cw-filter-row::-webkit-scrollbar {
          display: none;
        }
        .cw-filter-chip {
          flex: 0 0 auto;
          min-height: 36px;
          border-radius: var(--lv-r-pill);
          border: 1px solid var(--lv-line-2);
          background: rgba(255, 255, 255, 0.024);
          color: var(--lv-ink-3);
          padding: 0 13px;
          font-size: 12px;
          font-weight: 500;
          line-height: 1;
          cursor: pointer;
          transition: background var(--lv-dur-fast) var(--lv-ease), border-color var(--lv-dur-fast) var(--lv-ease), color var(--lv-dur-fast) var(--lv-ease);
        }
        .cw-filter-chip:hover {
          border-color: rgba(255, 255, 255, 0.16);
          background: rgba(255, 255, 255, 0.05);
          color: var(--lv-ink-2);
        }
        .cw-filter-chip.is-active {
          border-color: rgba(255, 255, 255, 0.26);
          background: rgba(245, 242, 235, 0.94);
          color: #171410;
          box-shadow: 0 6px 14px rgba(0, 0, 0, 0.12);
        }
        .cw-ledger-date {
          padding: 12px 16px 3px;
          color: var(--lv-ink-3);
          font-family: var(--lv-font-mono);
          font-size: 10px;
          font-weight: 500;
          letter-spacing: 0.14em;
          line-height: 1.4;
        }
        .cw-txn {
          display: grid;
          grid-template-columns: minmax(0, 1fr) auto;
          gap: 16px;
          padding: 12px 16px;
          border-top: 1px solid rgba(255, 255, 255, 0.045);
        }
        .cw-txn-main {
          min-width: 0;
        }
        .cw-txn-title {
          color: var(--lv-ink);
          font-size: var(--lv-t-compact);
          font-weight: 500;
          line-height: 1.4;
        }
        .cw-txn-meta,
        .cw-txn-note {
          margin-top: 3px;
          overflow: hidden;
          color: var(--lv-ink-3);
          font-size: var(--lv-t-meta);
          line-height: 1.45;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .cw-txn-meta {
          font-variant-numeric: tabular-nums;
        }
        .cw-txn-side {
          flex-shrink: 0;
          text-align: right;
        }
        .cw-txn-zero {
          color: var(--lv-ink-3);
          font-size: 12px;
          font-weight: 500;
        }
        .cw-txn-delta {
          color: var(--lv-ink-2);
          font-size: 14px;
          font-weight: 600;
          font-variant-numeric: tabular-nums;
          line-height: 1.4;
        }
        .cw-txn-delta.is-positive {
          color: var(--lv-ink);
        }
        .cw-txn-balance {
          margin-top: 3px;
          color: var(--lv-ink-3);
          font-size: 10px;
          font-variant-numeric: tabular-nums;
          line-height: 1.4;
        }
        .cw-ledger-state {
          padding: 16px;
          color: var(--lv-ink-3);
          font-size: var(--lv-t-compact);
        }
        /* 翻页器：到末页「下一页」置灰，不会"一直点下一张" */
        .cw-pager {
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 16px;
          padding: 12px 16px 14px;
        }
        .cw-pager-btn {
          width: 38px;
          height: 38px;
          display: grid;
          place-items: center;
          border-radius: 50%;
          border: 1px solid var(--lv-line-2);
          background: transparent;
          color: var(--lv-ink-2);
          cursor: pointer;
          transition: background var(--lv-dur-fast) var(--lv-ease), border-color var(--lv-dur-fast) var(--lv-ease), color var(--lv-dur-fast) var(--lv-ease);
        }
        .cw-pager-btn:hover:not(:disabled) {
          border-color: rgba(255, 255, 255, 0.18);
          background: rgba(255, 255, 255, 0.05);
          color: var(--lv-ink);
        }
        .cw-pager-btn:disabled {
          cursor: not-allowed;
          opacity: 0.3;
        }
        .cw-pager-label {
          min-width: 84px;
          text-align: center;
          color: var(--lv-ink-3);
          font-size: var(--lv-t-meta);
          font-variant-numeric: tabular-nums;
        }
        .cw-window-note {
          padding: 0 16px 14px;
          text-align: center;
          color: var(--lv-ink-4);
          font-size: var(--lv-t-meta);
        }
        @media (max-width: 768px) {
          .cw-ledger {
            margin-top: 14px;
          }
          .cw-txn {
            gap: 12px;
            padding: 13px 14px;
          }
          .cw-ledger-head {
            padding: 14px;
          }
          .cw-filter-row {
            gap: 7px;
          }
          .cw-filter-chip {
            min-height: 44px;
            padding: 0 14px;
            font-size: 12px;
          }
          .cw-ledger-date {
            padding-left: 14px;
            padding-right: 14px;
          }
          .cw-pager-btn {
            width: 44px;
            height: 44px;
          }
        }
      `}</style>
    </div>
  );
}

interface CreditWalletViewProps {
  scope: CreditScope;
  sessionId?: string;
}

/**
 * 积分内容块：当前余额 + 统计 + 流水列表。play 本局抽屉 / 移动 chip 抽屉继续用它，
 * 保证这些入口展示一致。
 * - scope="all"：全部流水 + 累计获得/消耗
 * - scope="session"：仅本局流水 + 本局消耗（需 sessionId）
 */
export function CreditWalletView({ scope, sessionId }: CreditWalletViewProps) {
  const t = useTranslations("credits");
  const isSession = scope === "session";

  const { data: balance } = useQuery({
    queryKey: CREDIT_BALANCE_QUERY_KEY,
    queryFn: fetchCreditBalance,
    staleTime: 30_000,
  });

  const { data: txns } = useQuery({
    queryKey: creditTxnsSummaryKey(scope, sessionId),
    queryFn: () => fetchCreditTransactions(isSession ? { session: sessionId } : {}),
    enabled: isSession && !!sessionId,
  });

  const level = creditLevel(balance?.balance);
  const palette = balanceTone(level);
  const balanceColor = level === "normal" ? "var(--lv-ink)" : palette.color;
  const sessionSpent = (txns?.items ?? []).reduce((sum, x) => (x.delta < 0 ? sum - x.delta : sum), 0);

  return (
    <div style={{ padding: "4px 0 20px" }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: "8px", padding: "8px 0 16px" }}>
        <span style={{ color: balanceColor, fontSize: "28px", fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>
          {balance ? fmtCredits(balance.balance) : "—"}
        </span>
        <span style={{ color: "var(--lv-ink-3)", fontSize: "var(--lv-t-meta)" }}>{t("unit")}</span>
      </div>

      <div style={{ display: "flex", gap: "24px", paddingBottom: "18px", borderBottom: "1px solid var(--lv-line)" }}>
        {isSession ? (
          <Stat label={t("sessionSpent")} value={fmtCredits(sessionSpent)} />
        ) : (
          <>
            <Stat label={t("lifetimeGranted")} value={balance ? fmtCredits(balance.lifetime_granted) : "—"} />
            <Stat label={t("lifetimeSpent")} value={balance ? fmtCredits(balance.lifetime_spent) : "—"} />
          </>
        )}
      </div>

      <CreditLedger scope={scope} sessionId={sessionId} />
    </div>
  );
}
