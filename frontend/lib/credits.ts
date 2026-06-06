import { apiFetch } from "./api";

export interface CreditBalance {
  balance: number;
  lifetime_granted: number;
  lifetime_spent: number;
}

export type CreditCategory = "play" | "creation" | "image" | "grant" | "adjust";

export interface CreditTransaction {
  id: string;
  ts: string;
  kind: string;
  category: CreditCategory | string | null;
  delta: number;
  balance_after: number;
  note: string | null;
  ref_type: string | null;
  ref_id: string | null;
  // 反查得到的上下文：游玩→世界名/剧本名/模式/回合；生成→作品名。缺失（已删/无 ref）为 null。
  ref_title: string | null;
  ref_subtitle: string | null;
  ref_mode: "script" | "free" | string | null;
  ref_turn: number | null;
}

export interface CreditTransactionsPage {
  items: CreditTransaction[];
  next_cursor: string | null;
}

export const CREDIT_BALANCE_QUERY_KEY = ["credits", "balance"] as const;
export const CREDIT_TXNS_QUERY_KEY = ["credits", "transactions"] as const;

export type CreditScope = "all" | "session";
export interface FetchCreditTransactionsOptions {
  before?: string;
  session?: string;
  category?: string;
  limit?: number;
}

// scope/sessionId 进 query key：本局抽屉与全局抽屉缓存分开。
// invalidate 用 CREDIT_TXNS_QUERY_KEY 前缀即可一并刷新所有 scope。
export function creditTxnsKey(scope: CreditScope, sessionId?: string, category?: string) {
  return [...CREDIT_TXNS_QUERY_KEY, "list", scope, sessionId ?? null, category ?? null] as const;
}

export function creditTxnsSummaryKey(scope: CreditScope, sessionId?: string) {
  return [...CREDIT_TXNS_QUERY_KEY, "summary", scope, sessionId ?? null] as const;
}

// 低余额视觉阈值（可调；未来可换成"约 N 回合"启发式）。
export const LOW_BALANCE_THRESHOLD = 50;

export type CreditLevel = "normal" | "low" | "empty";

// 余额未知（加载中）按 normal 处理，避免闪一下告警色。
export function creditLevel(balance: number | undefined): CreditLevel {
  if (balance === undefined) return "normal";
  if (balance <= 0) return "empty";
  if (balance <= LOW_BALANCE_THRESHOLD) return "low";
  return "normal";
}

export function fetchCreditBalance(): Promise<CreditBalance> {
  return apiFetch<CreditBalance>("/api/credits/balance");
}

export function buildCreditTransactionsPath(opts: FetchCreditTransactionsOptions = {}): string {
  const params = new URLSearchParams();
  if (opts.before) params.set("before", opts.before);
  if (opts.session) params.set("session", opts.session); // 本局流水
  if (opts.category) params.set("category", opts.category);
  if (opts.limit) params.set("limit", String(opts.limit));
  const qs = params.toString();
  return `/api/credits/transactions${qs ? `?${qs}` : ""}`;
}

export function fetchCreditTransactions(
  opts: FetchCreditTransactionsOptions = {},
): Promise<CreditTransactionsPage> {
  return apiFetch<CreditTransactionsPage>(buildCreditTransactionsPath(opts));
}

export function fmtCredits(n: number): string {
  return n.toLocaleString("zh-CN", { maximumFractionDigits: 1 });
}

export interface CreditTone {
  color: string;
  soft: string;
  border: string;
}

// 余额健康度 → 配色：正常金 / 低琥珀 / 空珊瑚红。chip 触发器与抽屉大数字共用。
export function balanceTone(level: CreditLevel): CreditTone {
  if (level === "empty") {
    return { color: "var(--lv-danger)", soft: "rgba(239, 130, 118, 0.10)", border: "rgba(239, 130, 118, 0.22)" };
  }
  if (level === "low") {
    return { color: "var(--lv-warn)", soft: "rgba(201, 163, 106, 0.12)", border: "rgba(201, 163, 106, 0.24)" };
  }
  return { color: "var(--lv-accent)", soft: "var(--lv-accent-soft)", border: "rgba(223, 194, 144, 0.18)" };
}
