import { NextRequest } from "next/server";
import { loadHistory, saveHistory } from "@/lib/history-store";
import { fetchTelegramStats, TokenExpiredError, MissingConfigError } from "@/lib/onlychat-client";
import { mergeTelegramStats } from "@/lib/merge";
import { buildStatsView } from "@/lib/stats-view";

export const dynamic = "force-dynamic";

function fmt(d: Date) {
  return d.toISOString().slice(0, 10);
}

function defaultRefreshRange(): { start: string; end: string } {
  // couvre assez large pour backfiller l'historique récent + garantir que "aujourd'hui" est inclus
  const end = new Date();
  const start = new Date();
  start.setDate(start.getDate() - 30);
  return { start: fmt(start), end: fmt(end) };
}

async function runRefresh(startDate: string, endDate: string) {
  const response = await fetchTelegramStats(startDate, endDate);
  const history = loadHistory();
  const merged = mergeTelegramStats(history, response, startDate, endDate);
  saveHistory(merged);
  return merged;
}

export async function POST(request: NextRequest) {
  let body: { startDate?: string; endDate?: string } = {};
  try {
    body = await request.json();
  } catch {
    // pas de body -> plage par défaut
  }

  const def = defaultRefreshRange();
  const startDate = body.startDate ?? def.start;
  const endDate = body.endDate ?? def.end;

  try {
    const merged = await runRefresh(startDate, endDate);
    const view = buildStatsView(merged, startDate, endDate);
    return Response.json(view);
  } catch (err) {
    if (err instanceof TokenExpiredError) {
      return Response.json({ error: "token_expired" }, { status: 401 });
    }
    if (err instanceof MissingConfigError) {
      return Response.json({ error: "missing_config" }, { status: 400 });
    }
    return Response.json({ error: "unknown", message: String(err) }, { status: 500 });
  }
}

// Auto-poll côté serveur toutes les 30 min tant que le process tourne (site "permanent").
// Guardé par un flag global pour éviter les doublons en dev (hot reload / double-invocation).
declare global {
  // eslint-disable-next-line no-var
  var __onlychatPollerStarted: boolean | undefined;
}

if (!globalThis.__onlychatPollerStarted) {
  globalThis.__onlychatPollerStarted = true;
  const POLL_MS = 30 * 60 * 1000;
  setInterval(() => {
    const { start, end } = defaultRefreshRange();
    runRefresh(start, end)
      .then(() => console.log(`[onlychat-dashboard] auto-refresh OK (${new Date().toISOString()})`))
      .catch((err) => console.error("[onlychat-dashboard] auto-refresh failed:", err instanceof Error ? err.message : err));
  }, POLL_MS);
}
