"use client";
import { useEffect, useState, useCallback } from "react";
import { DollarSign, TrendingUp, Percent, ShoppingCart } from "lucide-react";
import { SummaryCard } from "@/components/SummaryCard";
import { RevenueChart, ChartPoint } from "@/components/RevenueChart";
import { RecentSales } from "@/components/RecentSales";
import { DateRangePicker } from "@/components/DateRangePicker";
import { RefreshButton } from "@/components/RefreshButton";
import { SettingsPanel } from "@/components/SettingsPanel";
import { SaleRecord, RangeSummary } from "@/lib/types";

interface StatsView {
  range: { start: string; end: string };
  chart: ChartPoint[];
  totalRevenueUsd: number;
  todayRevenueUsd: number;
  recentSales: SaleRecord[];
  lastRangeSummary: RangeSummary | null;
  lastRefreshAt: string | null;
}

function fmt(d: Date) {
  return d.toISOString().slice(0, 10);
}

function defaultRange() {
  const end = new Date();
  const start = new Date();
  start.setDate(start.getDate() - 6);
  return { start: fmt(start), end: fmt(end) };
}

export default function DashboardPage() {
  const [range, setRange] = useState(defaultRange());
  const [view, setView] = useState<StatsView | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [config, setConfig] = useState<{ organizationId: string | null; tokenSavedAt: string | null }>({
    organizationId: null,
    tokenSavedAt: null,
  });

  const loadStats = useCallback(async (start: string, end: string) => {
    const res = await fetch(`/api/stats?start=${start}&end=${end}`);
    const data = await res.json();
    setView(data);
  }, []);

  const loadConfig = useCallback(async () => {
    const res = await fetch("/api/config");
    const data = await res.json();
    setConfig({ organizationId: data.organizationId, tokenSavedAt: data.tokenSavedAt });
  }, []);

  useEffect(() => {
    loadStats(range.start, range.end);
  }, [range, loadStats]);

  useEffect(() => {
    loadConfig();
  }, [loadConfig]);

  // rafraîchit l'affichage toutes les 5 min si l'onglet reste ouvert (lecture locale seulement)
  useEffect(() => {
    const id = setInterval(() => loadStats(range.start, range.end), 5 * 60 * 1000);
    return () => clearInterval(id);
  }, [range, loadStats]);

  async function handleRefresh() {
    setLoading(true);
    setError(null);
    try {
      const today = fmt(new Date());
      const res = await fetch("/api/refresh", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ startDate: range.start, endDate: today }),
      });
      if (res.status === 401) {
        const body = await res.json().catch(() => ({}));
        setError(body.error === "token_expired" ? "token_expired" : "missing_config");
        return;
      }
      if (res.status === 400) {
        setError("missing_config");
        return;
      }
      if (!res.ok) throw new Error("Échec de l'actualisation");
      await loadStats(range.start, range.end);
    } catch (e) {
      setError(e instanceof Error ? e.message : "unknown");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="p-8 flex-1" style={{ color: "#fff" }}>
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-black">Revenus Telegram</h1>
          <p className="text-sm mt-1" style={{ color: "#6b7280" }}>Dashboard perso — OnlyChat</p>
        </div>
        <div className="flex items-center gap-3">
          <DateRangePicker start={range.start} end={range.end} onChange={(start, end) => setRange({ start, end })} />
          <RefreshButton loading={loading} onClick={handleRefresh} />
          <SettingsPanel tokenSavedAt={config.tokenSavedAt} organizationId={config.organizationId} onSaved={loadConfig} />
        </div>
      </div>

      {error === "token_expired" && (
        <div className="mb-6 p-4 rounded-xl text-sm" style={{ background: "#7c2d1220", border: "1px solid #7c2d12", color: "#fca5a5" }}>
          Le token OnlyChat a expiré — ouvre les Réglages (icône engrenage) pour en remettre un frais.
        </div>
      )}
      {error === "missing_config" && (
        <div className="mb-6 p-4 rounded-xl text-sm" style={{ background: "#7c2d1220", border: "1px solid #7c2d12", color: "#fca5a5" }}>
          Aucun token configuré — ouvre les Réglages pour en ajouter un.
        </div>
      )}

      <div className="grid grid-cols-4 gap-4 mb-8">
        <SummaryCard label="Revenu (période)" value={`$${(view?.totalRevenueUsd ?? 0).toFixed(2)}`} icon={DollarSign} color="#10b981" />
        <SummaryCard label="Revenu aujourd'hui" value={`$${(view?.todayRevenueUsd ?? 0).toFixed(2)}`} icon={TrendingUp} color="#a855f7" />
        <SummaryCard
          label="Ventes IA (dernier refresh)"
          value={`${view?.lastRangeSummary?.aiSalesCount ?? 0}`}
          icon={ShoppingCart}
          color="#3b82f6"
        />
        <SummaryCard
          label="Ratio unlock (dernier refresh)"
          value={`${((view?.lastRangeSummary?.unlockRatio ?? 0) * 100).toFixed(1)}%`}
          icon={Percent}
          color="#f59e0b"
        />
      </div>

      <div className="grid grid-cols-3 gap-6">
        <div className="col-span-2">
          <RevenueChart data={view?.chart ?? []} />
        </div>
        <RecentSales sales={view?.recentSales ?? []} />
      </div>

      <p className="text-xs mt-6" style={{ color: "#4b5563" }}>
        Dernière actualisation : {view?.lastRefreshAt ? new Date(view.lastRefreshAt).toLocaleString("fr-FR") : "jamais"}
      </p>
    </div>
  );
}
