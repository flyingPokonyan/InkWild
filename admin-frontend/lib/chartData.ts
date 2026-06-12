/** 把后端返回的稀疏日序列补齐成连续 N 天（缺失日补 0）。 */
function beijingTodayParts(): { year: number; month: number; day: number } {
  const parts = new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "numeric",
    day: "numeric",
  }).formatToParts(new Date());
  const get = (type: string) => Number(parts.find((p) => p.type === type)?.value);
  return { year: get("year"), month: get("month"), day: get("day") };
}

export function fillDailySeries(
  series: { date: string; cost_cents: number }[],
  days: number,
): { date: string; label: string; value: number }[] {
  const valueByDate = new Map(series.map((p) => [p.date, p.cost_cents]));
  const out: { date: string; label: string; value: number }[] = [];
  const todayParts = beijingTodayParts();
  const today = new Date(Date.UTC(todayParts.year, todayParts.month - 1, todayParts.day));

  for (let i = days - 1; i >= 0; i--) {
    const d = new Date(today);
    d.setUTCDate(today.getUTCDate() - i);
    const iso = `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}-${String(d.getUTCDate()).padStart(2, "0")}`;
    out.push({
      date: iso,
      label: `${d.getUTCMonth() + 1}/${d.getUTCDate()}`,
      value: valueByDate.get(iso) ?? 0,
    });
  }
  return out;
}
