/** 把后端返回的稀疏日序列补齐成连续 N 天（缺失日补 0）。 */
export function fillDailySeries(
  series: { date: string; cost_cents: number }[],
  days: number,
): { date: string; label: string; value: number }[] {
  const valueByDate = new Map(series.map((p) => [p.date, p.cost_cents]));
  const out: { date: string; label: string; value: number }[] = [];
  const today = new Date();
  today.setHours(0, 0, 0, 0);

  for (let i = days - 1; i >= 0; i--) {
    const d = new Date(today);
    d.setDate(today.getDate() - i);
    const iso = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    out.push({
      date: iso,
      label: `${d.getMonth() + 1}/${d.getDate()}`,
      value: valueByDate.get(iso) ?? 0,
    });
  }
  return out;
}
