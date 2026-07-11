import { loadConfig } from "./config-store";

export class TokenExpiredError extends Error {
  constructor() {
    super("OnlyChat access token expired or invalid");
    this.name = "TokenExpiredError";
  }
}

export class MissingConfigError extends Error {
  constructor() {
    super("OnlyChat access token or organizationId not configured");
    this.name = "MissingConfigError";
  }
}

export interface TelegramStatsResponse {
  totalRevenueUsd: number;
  totalRevenueStars: number;
  aiRevenueUsd: number;
  aiRevenueStars: number;
  aiSalesCount: number;
  averageBasketUsd: number;
  averageBasketStars: number;
  unlockRatio: number;
  recentSales: Array<{
    id: string;
    date: string;
    amountUsd: number;
    amountStars: number;
    fanUsername?: string;
    creator?: string;
  }>;
  chartTotal: Array<{ date: string; totalUsd: number; totalStars: number }>;
}

// startDate/endDate: "YYYY-MM-DD", interprétées en heure locale de la machine (comme le fait le dashboard OnlyChat lui-même)
export async function fetchTelegramStats(startDate: string, endDate: string): Promise<TelegramStatsResponse> {
  const { accessToken, organizationId } = loadConfig();
  if (!accessToken || !organizationId) throw new MissingConfigError();

  const start = new Date(`${startDate}T00:00:00`).toISOString();
  const end = new Date(`${endDate}T23:59:59.999`).toISOString();

  const url = `https://api.app.only-chat.ai/telegram-bridge/stats?organizationId=${encodeURIComponent(organizationId)}&startDate=${start}&endDate=${end}`;
  const res = await fetch(url, { headers: { Authorization: `Bearer ${accessToken}` } });

  if (res.status === 401 || res.status === 403) throw new TokenExpiredError();
  if (!res.ok) throw new Error(`OnlyChat API a répondu ${res.status}`);

  return res.json();
}
