import { RevenueHistory, RangeSummary, SaleRecord } from "./types";
import { TelegramStatsResponse } from "./onlychat-client";

const SOURCE = "telegram" as const;

function todayLocal(): string {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function dedupeSales(sales: SaleRecord[]): SaleRecord[] {
  const seen = new Set<string>();
  const out: SaleRecord[] = [];
  for (const s of sales) {
    const key = `${s.date}|${s.amount}|${s.label}`;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(s);
  }
  return out.sort((a, b) => (a.date < b.date ? 1 : -1)).slice(0, 200);
}

export function mergeTelegramStats(
  history: RevenueHistory,
  response: TelegramStatsResponse,
  startDate: string,
  endDate: string
): RevenueHistory {
  const today = todayLocal();
  const days = { ...history.days };

  for (const entry of response.chartTotal) {
    const key = `${SOURCE}:${entry.date}`;
    const existing = days[key];
    if (existing?.isFinal) continue; // jour passé déjà verrouillé : on ne touche plus

    days[key] = {
      date: entry.date,
      source: SOURCE,
      totalUsd: entry.totalUsd,
      totalStars: entry.totalStars,
      isFinal: entry.date < today,
      fetchedAt: new Date().toISOString(),
    };
  }

  const newSales: SaleRecord[] = (response.recentSales || []).map((s) => ({
    date: String(s.date ?? new Date().toISOString()),
    amount: Number(s.amountUsd ?? 0),
    source: SOURCE,
    label: `${s.fanUsername ?? "Fan"} → ${s.creator ?? ""}`.trim(),
  }));

  const summary: RangeSummary = {
    source: SOURCE,
    startDate,
    endDate,
    totalRevenueUsd: response.totalRevenueUsd,
    aiRevenueUsd: response.aiRevenueUsd,
    aiSalesCount: response.aiSalesCount,
    unlockRatio: response.unlockRatio,
    averageBasketUsd: response.averageBasketUsd,
    fetchedAt: new Date().toISOString(),
  };

  return {
    days,
    recentSales: dedupeSales([...newSales, ...history.recentSales]),
    lastRangeSummary: summary,
    lastRefreshAt: new Date().toISOString(),
  };
}
