import { RevenueHistory } from "./types";

export interface StatsView {
  range: { start: string; end: string };
  chart: Array<{ date: string; totalUsd: number; isFinal: boolean }>;
  totalRevenueUsd: number;
  todayRevenueUsd: number;
  recentSales: RevenueHistory["recentSales"];
  lastRangeSummary: RevenueHistory["lastRangeSummary"];
  lastRefreshAt: string | null;
}

function eachDate(start: string, end: string): string[] {
  const out: string[] = [];
  const cur = new Date(`${start}T00:00:00`);
  const last = new Date(`${end}T00:00:00`);
  while (cur <= last) {
    const y = cur.getFullYear();
    const m = String(cur.getMonth() + 1).padStart(2, "0");
    const d = String(cur.getDate()).padStart(2, "0");
    out.push(`${y}-${m}-${d}`);
    cur.setDate(cur.getDate() + 1);
  }
  return out;
}

function todayLocal(): string {
  return eachDate(new Date().toISOString().slice(0, 10), new Date().toISOString().slice(0, 10))[0];
}

export function buildStatsView(history: RevenueHistory, start: string, end: string): StatsView {
  const dates = eachDate(start, end);
  const chart = dates.map((date) => {
    const rec = history.days[`telegram:${date}`];
    return { date, totalUsd: rec?.totalUsd ?? 0, isFinal: rec?.isFinal ?? false };
  });

  const totalRevenueUsd = chart.reduce((sum, d) => sum + d.totalUsd, 0);
  const today = todayLocal();
  const todayRevenueUsd = history.days[`telegram:${today}`]?.totalUsd ?? 0;

  return {
    range: { start, end },
    chart,
    totalRevenueUsd,
    todayRevenueUsd,
    recentSales: history.recentSales,
    lastRangeSummary: history.lastRangeSummary,
    lastRefreshAt: history.lastRefreshAt,
  };
}
