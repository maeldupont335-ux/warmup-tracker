"use client";
import { useState, useEffect } from "react";
import { TrendingUp, MessageCircle, DollarSign, Users, Star, ShoppingBag, RefreshCw } from "lucide-react";

interface Analytics {
  totalRevenueEur: number;
  totalStars: number;
  totalFans: number;
  activeFans: number;
  totalStarsSales: number;
  conversionRate: string;
  lastSales: { stars: number; amountEur: number; fanId: string; createdAt: string }[];
}

export default function DashboardPage() {
  const [data, setData] = useState<Analytics | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/analytics?days=30")
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  const timeAgo = (iso: string) => {
    const diff = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
    if (diff < 60) return `il y a ${diff}s`;
    if (diff < 3600) return `il y a ${Math.floor(diff / 60)}min`;
    if (diff < 86400) return `il y a ${Math.floor(diff / 3600)}h`;
    return `il y a ${Math.floor(diff / 86400)}j`;
  };

  const kpis = [
    {
      label: "Revenus générés (30j)",
      value: loading ? "…" : `€${(data?.totalRevenueEur ?? 0).toFixed(2)}`,
      sub: `${data?.totalStars ?? 0} ⭐ vendues`,
      icon: DollarSign, color: "#10b981",
    },
    {
      label: "Médias payants vendus",
      value: loading ? "…" : String(data?.totalStarsSales ?? 0),
      sub: `taux conversion ${data?.conversionRate ?? "0"}%`,
      icon: TrendingUp, color: "#3b82f6",
    },
    {
      label: "Fans actifs (30j)",
      value: loading ? "…" : String(data?.activeFans ?? 0),
      sub: `sur ${data?.totalFans ?? 0} fans total`,
      icon: Users, color: "#f59e0b",
    },
    {
      label: "Messages IA envoyés",
      value: loading ? "…" : String((data?.activeFans ?? 0) * 3),
      sub: "estimé sur 30 jours",
      icon: MessageCircle, color: "#a855f7",
    },
  ];

  return (
    <div className="p-8" style={{ color: "#fff" }}>

      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-black">Vue d&apos;ensemble</h1>
          <p className="text-sm mt-1" style={{ color: "#6b7280" }}>
            {new Date().toLocaleDateString("fr-FR", { weekday: "long", day: "numeric", month: "long", year: "numeric" })}
          </p>
        </div>
        <button onClick={() => { setLoading(true); fetch("/api/analytics?days=30").then(r => r.json()).then(d => { setData(d); setLoading(false); }); }}
          className="p-2 rounded-lg border transition-all hover:bg-white/5"
          style={{ borderColor: "#1e1e2e", color: "#6b7280" }}>
          <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
        </button>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        {kpis.map((k) => (
          <div key={k.label} className="p-5 rounded-2xl border" style={{ background: "#111118", borderColor: "#1e1e2e" }}>
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs" style={{ color: "#6b7280" }}>{k.label}</span>
              <k.icon size={16} style={{ color: k.color }} />
            </div>
            <div className="text-2xl font-black mb-1">{k.value}</div>
            <div className="text-xs" style={{ color: "#4b5563" }}>{k.sub}</div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-3 gap-6">

        {/* Dernières ventes */}
        <div className="col-span-2 rounded-2xl border p-6" style={{ background: "#111118", borderColor: "#1e1e2e" }}>
          <h2 className="font-bold mb-4 flex items-center gap-2">
            <ShoppingBag size={14} style={{ color: "#a855f7" }} />
            Dernières ventes
          </h2>
          {loading ? (
            <div className="flex items-center justify-center h-32">
              <RefreshCw size={20} className="animate-spin" style={{ color: "#4b5563" }} />
            </div>
          ) : !data?.lastSales?.length ? (
            <div className="flex flex-col items-center justify-center h-32 text-center">
              <ShoppingBag size={28} style={{ color: "#2a2a3e", marginBottom: 8 }} />
              <p className="text-sm" style={{ color: "#4b5563" }}>Aucune vente pour le moment</p>
              <p className="text-xs mt-1" style={{ color: "#374151" }}>Les achats de médias payants apparaîtront ici</p>
            </div>
          ) : (
            <div className="space-y-3">
              {data.lastSales.map((s, i) => (
                <div key={i} className="flex items-center justify-between py-3 border-b last:border-0"
                  style={{ borderColor: "#1e1e2e" }}>
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-full flex items-center justify-center"
                      style={{ background: "rgba(245,158,11,0.15)" }}>
                      <Star size={14} fill="#f59e0b" style={{ color: "#f59e0b" }} />
                    </div>
                    <div>
                      <div className="text-sm font-medium">Achat média payant</div>
                      <div className="text-xs" style={{ color: "#6b7280" }}>Fan {s.fanId}</div>
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="text-sm font-bold flex items-center gap-1 justify-end" style={{ color: "#f59e0b" }}>
                      <Star size={11} fill="#f59e0b" />{s.stars}
                    </div>
                    <div className="text-xs font-bold" style={{ color: "#10b981" }}>+€{s.amountEur.toFixed(2)}</div>
                    <div className="text-xs" style={{ color: "#4b5563" }}>{timeAgo(s.createdAt)}</div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Résumé rapide */}
        <div className="space-y-4">
          <div className="rounded-2xl border p-5" style={{ background: "#111118", borderColor: "#1e1e2e" }}>
            <h3 className="font-bold text-sm mb-4">Revenus (30 jours)</h3>
            <div className="text-3xl font-black mb-1" style={{ color: "#10b981" }}>
              {loading ? "…" : `€${(data?.totalRevenueEur ?? 0).toFixed(2)}`}
            </div>
            <div className="text-xs mb-4" style={{ color: "#6b7280" }}>
              {data?.totalStars ?? 0} étoiles vendues
            </div>
            <div className="space-y-2">
              <div className="flex justify-between text-sm">
                <span style={{ color: "#6b7280" }}>Fans total</span>
                <span className="font-medium">{data?.totalFans ?? 0}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span style={{ color: "#6b7280" }}>Fans actifs</span>
                <span className="font-medium">{data?.activeFans ?? 0}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span style={{ color: "#6b7280" }}>Conversion PPV</span>
                <span className="font-medium">{data?.conversionRate ?? "0"}%</span>
              </div>
            </div>
          </div>

          <div className="rounded-2xl border p-5" style={{ background: "rgba(168,85,247,0.05)", borderColor: "rgba(168,85,247,0.2)" }}>
            <h3 className="font-bold text-sm mb-2" style={{ color: "#a855f7" }}>Pour voir plus de stats</h3>
            <p className="text-xs" style={{ color: "#6b7280" }}>
              Va dans <strong style={{ color: "#d1d5db" }}>Analytics</strong> dans le menu pour les graphiques, top fans et l&apos;historique complet avec sélecteur de période.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
