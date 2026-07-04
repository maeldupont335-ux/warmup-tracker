"use client";
import { useState, useEffect } from "react";
import { TrendingUp, DollarSign, MessageCircle, Users, Star, RefreshCw, ShoppingBag } from "lucide-react";

const PERIODS = [
  { label: "Aujourd'hui", days: 1 },
  { label: "7 jours", days: 7 },
  { label: "30 jours", days: 30 },
  { label: "90 jours", days: 90 },
  { label: "Tout", days: 3650 },
];

interface DailyRevenue { date: string; amount: number; }
interface TopFan { rank: number; name: string; stars: number; creatorName: string; }
interface LastSale { stars: number; amountEur: number; fanId: string; createdAt: string; }

interface Analytics {
  totalRevenueEur: number;
  totalStars: number;
  totalFans: number;
  activeFans: number;
  messagesIA: number;
  totalStarsSales: number;
  conversionRate: string;
  dailyRevenue: DailyRevenue[];
  topFans: TopFan[];
  lastSales: LastSale[];
}

export default function AnalyticsPage() {
  const [periodDays, setPeriodDays] = useState(30);
  const [data, setData] = useState<Analytics | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchData = async (days: number) => {
    setLoading(true);
    try {
      const res = await fetch(`/api/analytics?days=${days}`);
      if (res.ok) setData(await res.json());
    } catch { /* ignore */ }
    setLoading(false);
  };

  useEffect(() => { fetchData(periodDays); }, [periodDays]);

  const maxRev = data ? Math.max(...data.dailyRevenue.map(d => d.amount), 0.01) : 1;

  const formatDate = (iso: string) =>
    new Date(iso).toLocaleDateString("fr-FR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });

  const formatDay = (iso: string) =>
    new Date(iso).toLocaleDateString("fr-FR", { day: "2-digit", month: "2-digit" });

  return (
    <div className="p-8" style={{ color: "#fff" }}>

      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-black">Vue d&apos;ensemble</h1>
          <p className="text-sm mt-1" style={{ color: "#6b7280" }}>Performance réelle de ton IA</p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => fetchData(periodDays)}
            className="p-2 rounded-lg border transition-all hover:bg-white/5"
            style={{ borderColor: "#1e1e2e", color: "#6b7280" }}>
            <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
          </button>
          <div className="flex items-center gap-1 p-1 rounded-xl" style={{ background: "#111118", border: "1px solid #1e1e2e" }}>
            {PERIODS.map(p => (
              <button key={p.days} onClick={() => setPeriodDays(p.days)}
                className="px-4 py-1.5 rounded-lg text-sm font-medium transition-all"
                style={periodDays === p.days
                  ? { background: "linear-gradient(135deg,#a855f7,#7c3aed)", color: "#fff" }
                  : { color: "#6b7280" }}>
                {p.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {loading && !data ? (
        <div className="flex items-center justify-center h-64">
          <RefreshCw size={24} className="animate-spin" style={{ color: "#6b7280" }} />
        </div>
      ) : (
        <>
          {/* KPI cards */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
            {[
              {
                label: "Revenus générés",
                value: `€${(data?.totalRevenueEur ?? 0).toFixed(2)}`,
                sub: `${data?.totalStars ?? 0} ⭐ vendues`,
                icon: DollarSign, color: "#10b981",
              },
              {
                label: "Fans actifs",
                value: String(data?.activeFans ?? 0),
                sub: `sur ${data?.totalFans ?? 0} fans total`,
                icon: Users, color: "#a855f7",
              },
              {
                label: "Médias payants vendus",
                value: String(data?.totalStarsSales ?? 0),
                sub: `taux conversion ${data?.conversionRate ?? "0"}%`,
                icon: TrendingUp, color: "#3b82f6",
              },
              {
                label: "Messages IA envoyés",
                value: String(data?.messagesIA ?? 0),
                sub: "estimé sur la période",
                icon: MessageCircle, color: "#f59e0b",
              },
            ].map((k) => (
              <div key={k.label} className="p-5 rounded-2xl border" style={{ background: "#111118", borderColor: "#1e1e2e" }}>
                <div className="flex items-center justify-between mb-3">
                  <span className="text-xs" style={{ color: "#6b7280" }}>{k.label}</span>
                  <k.icon size={15} style={{ color: k.color }} />
                </div>
                <div className="text-2xl font-black mb-1">{k.value}</div>
                <div className="text-xs" style={{ color: "#4b5563" }}>{k.sub}</div>
              </div>
            ))}
          </div>

          <div className="grid grid-cols-3 gap-6 mb-6">
            {/* Graphe revenus */}
            <div className="col-span-2 rounded-2xl border p-6" style={{ background: "#111118", borderColor: "#1e1e2e" }}>
              <h2 className="font-bold mb-6">Revenus quotidiens (€)</h2>
              {data?.dailyRevenue.every(d => d.amount === 0) ? (
                <div className="flex flex-col items-center justify-center h-40" style={{ color: "#4b5563" }}>
                  <DollarSign size={32} style={{ marginBottom: 8 }} />
                  <p className="text-sm">Aucun revenu sur cette période</p>
                  <p className="text-xs mt-1">Les ventes Stars apparaîtront ici</p>
                </div>
              ) : (
                <>
                  <div className="flex items-end gap-1 h-40">
                    {data?.dailyRevenue.map((d, i) => (
                      <div key={i} className="flex-1 flex flex-col items-center gap-1 group relative">
                        <div className="absolute -top-7 left-1/2 -translate-x-1/2 text-xs px-2 py-1 rounded hidden group-hover:block z-10"
                          style={{ background: "#1e1e2e", color: "#d1d5db", whiteSpace: "nowrap" }}>
                          {formatDay(d.date)} — €{d.amount.toFixed(2)}
                        </div>
                        <div className="w-full rounded-t-sm transition-all"
                          style={{
                            height: `${Math.max((d.amount / maxRev) * 100, d.amount > 0 ? 4 : 1)}%`,
                            background: d.amount > 0
                              ? "linear-gradient(180deg,#a855f7,#7c3aed)"
                              : "rgba(168,85,247,0.08)",
                          }} />
                      </div>
                    ))}
                  </div>
                  <div className="flex justify-between text-xs mt-2" style={{ color: "#4b5563" }}>
                    {data && data.dailyRevenue.length > 0 && (
                      <>
                        <span>{formatDay(data.dailyRevenue[0].date)}</span>
                        <span>{formatDay(data.dailyRevenue[Math.floor(data.dailyRevenue.length / 2)]?.date ?? "")}</span>
                        <span>Aujourd&apos;hui</span>
                      </>
                    )}
                  </div>
                </>
              )}
            </div>

            {/* Top fans */}
            <div className="rounded-2xl border p-6" style={{ background: "#111118", borderColor: "#1e1e2e" }}>
              <h2 className="font-bold mb-4 flex items-center gap-2">
                <Star size={14} style={{ color: "#f59e0b" }} />
                Top fans
              </h2>
              {!data?.topFans?.length ? (
                <div className="text-center py-8" style={{ color: "#4b5563" }}>
                  <Users size={28} style={{ margin: "0 auto 8px" }} />
                  <p className="text-xs">Aucune vente encore</p>
                </div>
              ) : (
                <div className="space-y-3">
                  {data.topFans.map((f) => (
                    <div key={f.telegramId ?? f.rank} className="flex items-center gap-3">
                      <span className="text-xs font-bold w-5 text-center"
                        style={{ color: f.rank <= 3 ? "#f59e0b" : "#4b5563" }}>
                        #{f.rank}
                      </span>
                      <div className="flex-1 text-sm min-w-0">
                        <div className="font-medium truncate">{f.name}</div>
                        <div className="text-xs" style={{ color: "#6b7280" }}>{f.creatorName}</div>
                      </div>
                      <span className="text-sm font-bold flex items-center gap-1" style={{ color: "#f59e0b" }}>
                        <Star size={11} fill="#f59e0b" />{f.stars}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Dernières ventes */}
          <div className="rounded-2xl border p-6" style={{ background: "#111118", borderColor: "#1e1e2e" }}>
            <h2 className="font-bold mb-4 flex items-center gap-2">
              <ShoppingBag size={14} style={{ color: "#a855f7" }} />
              Dernières ventes
            </h2>
            {!data?.lastSales?.length ? (
              <div className="text-center py-8" style={{ color: "#4b5563" }}>
                <ShoppingBag size={28} style={{ margin: "0 auto 8px" }} />
                <p className="text-sm">Aucune vente sur cette période</p>
                <p className="text-xs mt-1">Les ventes de médias payants apparaîtront ici</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr style={{ borderBottom: "1px solid #1e1e2e" }}>
                      {["Date", "Fan", "Stars", "Revenu net"].map(h => (
                        <th key={h} className="text-left pb-3 text-xs font-medium" style={{ color: "#6b7280" }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {data.lastSales.map((s, i) => (
                      <tr key={i} style={{ borderBottom: i < data.lastSales.length - 1 ? "1px solid #1a1a28" : "none" }}>
                        <td className="py-3 text-xs" style={{ color: "#6b7280" }}>{formatDate(s.createdAt)}</td>
                        <td className="py-3 text-xs" style={{ color: "#d1d5db" }}>{s.fanId}</td>
                        <td className="py-3">
                          <span className="flex items-center gap-1 text-xs font-bold" style={{ color: "#f59e0b" }}>
                            <Star size={10} fill="#f59e0b" />{s.stars}
                          </span>
                        </td>
                        <td className="py-3 text-xs font-bold" style={{ color: "#10b981" }}>
                          €{s.amountEur.toFixed(2)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
