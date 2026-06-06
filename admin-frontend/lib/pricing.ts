/**
 * 单价格式化：后端用「分 / 百万 token」(input/output) 或「分 / 张」(image) 存。
 * 1 cent CNY ≈ 0.014 USD（粗略，仅用于显示参考）。
 */

const USD_PER_CNY = 0.14;

export function fmtPricePerM(
  cents: number | null,
  currency: "cny" | "usd" = "cny",
): string {
  if (cents == null) return "—";
  const cny = cents / 100;
  if (currency === "cny") {
    return `¥${cny.toFixed(cny < 1 ? 3 : 2)}/M`;
  }
  const usd = cny * USD_PER_CNY;
  return `$${usd.toFixed(usd < 1 ? 3 : 2)}/M`;
}

export function fmtPricePerImage(
  cents: number | null,
  currency: "cny" | "usd" = "cny",
): string {
  if (cents == null) return "—";
  const cny = cents / 100;
  if (currency === "cny") {
    return `¥${cny.toFixed(cny < 0.1 ? 4 : 3)}/张`;
  }
  const usd = cny * USD_PER_CNY;
  return `$${usd.toFixed(usd < 0.01 ? 4 : 3)}/img`;
}

export function fmtCentsTotal(
  cents: number,
  currency: "cny" | "usd" = "cny",
  dp = 2,
): string {
  const cny = cents / 100;
  if (currency === "cny") return `¥${cny.toFixed(dp)}`;
  const usd = cny * USD_PER_CNY;
  return `$${usd.toFixed(dp)}`;
}
