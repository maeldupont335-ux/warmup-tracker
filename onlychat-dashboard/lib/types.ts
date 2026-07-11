export type Source = "telegram";

export interface DayRecord {
  date: string; // YYYY-MM-DD
  source: Source;
  totalUsd: number;
  totalStars: number;
  isFinal: boolean; // true = jour passé, verrouillé, ne sera plus jamais réécrasé
  fetchedAt: string; // ISO
}

export interface SaleRecord {
  date: string; // ISO
  amount: number;
  source: Source;
  label: string;
}

export interface RangeSummary {
  source: Source;
  startDate: string;
  endDate: string;
  totalRevenueUsd: number;
  aiRevenueUsd: number;
  aiSalesCount: number;
  unlockRatio: number;
  averageBasketUsd: number;
  fetchedAt: string;
}

export interface RevenueHistory {
  days: Record<string, DayRecord>; // clé: `${source}:${date}`
  recentSales: SaleRecord[];
  lastRangeSummary: RangeSummary | null;
  lastRefreshAt: string | null;
}

export interface OnlyChatConfig {
  accessToken: string | null;
  refreshToken: string | null;
  organizationId: string | null;
  tokenSavedAt: string | null;
}
