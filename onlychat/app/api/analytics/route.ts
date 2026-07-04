import { NextRequest, NextResponse } from "next/server";
import { createServerClient } from "@supabase/ssr";
import { getDataDir } from "@/lib/data-dir";
import fs from "fs";
import path from "path";

async function getUserId(req: NextRequest): Promise<string | null> {
  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    { cookies: { getAll: () => req.cookies.getAll(), setAll: () => {} } }
  );
  const { data: { user } } = await supabase.auth.getUser();
  return user?.id ?? null;
}

function loadCreators(userId: string) {
  try {
    const f = path.join(getDataDir(), "users", `${userId}-creators.json`);
    if (!fs.existsSync(f)) return [];
    return JSON.parse(fs.readFileSync(f, "utf-8"));
  } catch { return []; }
}

function loadFans(creatorId: string) {
  try {
    const f = path.join(getDataDir(), "creators", `${creatorId}-fans.json`);
    if (!fs.existsSync(f)) return [];
    return JSON.parse(fs.readFileSync(f, "utf-8"));
  } catch { return []; }
}

function loadBilling(userId: string) {
  try {
    const f = path.join(getDataDir(), "billing", `${userId}.json`);
    if (!fs.existsSync(f)) return null;
    return JSON.parse(fs.readFileSync(f, "utf-8"));
  } catch { return null; }
}

export async function GET(req: NextRequest) {
  const userId = await getUserId(req);
  if (!userId) return NextResponse.json({ error: "Non authentifié" }, { status: 401 });

  const url = new URL(req.url);
  const periodDays = parseInt(url.searchParams.get("days") ?? "30");
  const since = new Date(Date.now() - periodDays * 24 * 60 * 60 * 1000);

  const creators = loadCreators(userId);
  const billing = loadBilling(userId);
  const transactions: {
    type: string; amount: number; stars?: number;
    creatorId?: string; fanId?: string; createdAt: string;
  }[] = billing?.transactions ?? [];

  // Filtrer par période
  const periodTxs = transactions.filter(t => new Date(t.createdAt) >= since);
  const starsTxs = periodTxs.filter(t => t.type === "stars_sale");

  // Revenue total sur la période
  const totalRevenueEur = starsTxs.reduce((s, t) => s + (t.amount ?? 0), 0);
  const totalStars = starsTxs.reduce((s, t) => s + (t.stars ?? 0), 0);

  // Messages envoyés : on compte depuis les fans (lastInteraction dans la période)
  let totalFans = 0;
  let activeFans = 0; // fans qui ont interagi dans la période
  let totalStarsSales = starsTxs.length;
  const topFansMap: Record<string, { name: string; stars: number; creatorName: string }> = {};

  for (const creator of creators) {
    const fans = loadFans(creator.id);
    totalFans += fans.length;
    for (const fan of fans) {
      if (fan.lastInteraction && new Date(fan.lastInteraction) >= since) {
        activeFans++;
      }
      // Stars par fan
      if (fan.totalStars && fan.totalStars > 0) {
        topFansMap[fan.telegramId] = {
          name: fan.name || fan.telegramId,
          stars: fan.totalStars ?? 0,
          creatorName: creator.name,
        };
      }
    }
  }

  // Messages IA envoyés : approximé = activeFans * moyenne (on n'a pas de compteur exact)
  // On prend les transactions pour estimer
  const messagesIA = activeFans * 3; // placeholder basé sur fans actifs

  // Taux de conversion paid media = ventes stars / fans actifs
  const conversionRate = activeFans > 0 ? ((totalStarsSales / activeFans) * 100).toFixed(1) : "0";

  // Graphe journalier : revenus par jour sur la période
  const dailyMap: Record<string, number> = {};
  for (let i = 0; i < periodDays; i++) {
    const d = new Date(Date.now() - i * 24 * 60 * 60 * 1000);
    const key = d.toISOString().slice(0, 10);
    dailyMap[key] = 0;
  }
  for (const tx of starsTxs) {
    const key = new Date(tx.createdAt).toISOString().slice(0, 10);
    if (key in dailyMap) dailyMap[key] += tx.amount ?? 0;
  }
  const dailyRevenue = Object.entries(dailyMap)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([date, amount]) => ({ date, amount: Math.round(amount * 100) / 100 }));

  // Top fans par stars
  const topFans = Object.entries(topFansMap)
    .sort(([, a], [, b]) => b.stars - a.stars)
    .slice(0, 5)
    .map(([telegramId, data], i) => ({
      rank: i + 1,
      telegramId,
      name: data.name,
      stars: data.stars,
      creatorName: data.creatorName,
    }));

  // Dernières ventes
  const lastSales = starsTxs
    .sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime())
    .slice(0, 10)
    .map(t => ({
      stars: t.stars ?? 0,
      amountEur: Math.round((t.amount ?? 0) * 100) / 100,
      creatorId: t.creatorId ?? "",
      fanId: t.fanId ?? "",
      createdAt: t.createdAt,
    }));

  return NextResponse.json({
    period: periodDays,
    totalRevenueEur: Math.round(totalRevenueEur * 100) / 100,
    totalStars,
    totalFans,
    activeFans,
    messagesIA,
    totalStarsSales,
    conversionRate,
    dailyRevenue,
    topFans,
    lastSales,
  });
}
