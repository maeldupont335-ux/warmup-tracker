import { NextRequest } from "next/server";
import { loadHistory } from "@/lib/history-store";
import { buildStatsView } from "@/lib/stats-view";

export const dynamic = "force-dynamic";

function defaultRange(): { start: string; end: string } {
  const end = new Date();
  const start = new Date();
  start.setDate(start.getDate() - 6);
  const fmt = (d: Date) => d.toISOString().slice(0, 10);
  return { start: fmt(start), end: fmt(end) };
}

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const def = defaultRange();
  const start = searchParams.get("start") ?? def.start;
  const end = searchParams.get("end") ?? def.end;

  const history = loadHistory();
  const view = buildStatsView(history, start, end);
  return Response.json(view);
}
