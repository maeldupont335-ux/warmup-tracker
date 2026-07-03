"use client";
import { useState } from "react";
import { TrendingUp, DollarSign, MessageCircle, Users, ArrowUpRight } from "lucide-react";

const periods = ["7j", "30j", "90j", "All"];

const topFans = [
  { id: "fan_2847", spent: "€284", messages: 48, rank: 1 },
  { id: "fan_5521", spent: "€198", messages: 31, rank: 2 },
  { id: "fan_1093", spent: "€156", messages: 67, rank: 3 },
  { id: "fan_7762", spent: "€124", messages: 22, rank: 4 },
  { id: "fan_0834", spent: "€98", messages: 19, rank: 5 },
];

const dailyRevenue = [42, 68, 55, 91, 73, 88, 120, 95, 110, 84, 102, 138, 115, 142];

export default function AnalyticsPage() {
  const [period, setPeriod] = useState("30j");

  const maxRev = Math.max(...dailyRevenue);

  return (
    <div className="p-8" style={{ color: "#fff" }}>
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-black">Analytics</h1>
          <p className="text-sm mt-1" style={{ color: "#6b7280" }}>Performance de ton IA</p>
        </div>
        <div className="flex items-center gap-1 p-1 rounded-xl" style={{ background: "#111118", border: "1px solid #1e1e2e" }}>
          {periods.map(p => (
            <button key={p} onClick={() => setPeriod(p)}
              className="px-4 py-1.5 rounded-lg text-sm font-medium transition-all"
              style={period === p
                ? { background: "linear-gradient(135deg,#a855f7,#7c3aed)", color: "#fff" }
                : { color: "#6b7280" }}>
              {p}
            </button>
          ))}
        </div>
      </div>

      {/* KPI cards */}
      <div className="grid grid-cols-4 gap-4 mb-8">
        {[
          { label: "Revenus IA totaux", value: "€3,847", change: "+28%", icon: DollarSign, color: "#10b981" },
          { label: "Messages IA", value: "1,204", change: "+14%", icon: MessageCircle, color: "#a855f7" },
          { label: "PPV vendus", value: "94", change: "+32%", icon: TrendingUp, color: "#3b82f6" },
          { label: "Fans réactivés", value: "127", change: "+8%", icon: Users, color: "#f59e0b" },
        ].map((k) => (
          <div key={k.label} className="p-5 rounded-2xl border" style={{ background: "#111118", borderColor: "#1e1e2e" }}>
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs" style={{ color: "#6b7280" }}>{k.label}</span>
              <k.icon size={15} style={{ color: k.color }} />
            </div>
            <div className="text-2xl font-black mb-1">{k.value}</div>
            <div className="flex items-center gap-1 text-xs" style={{ color: "#10b981" }}>
              <ArrowUpRight size={11} />{k.change}
            </div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-3 gap-6">
        {/* Revenue chart */}
        <div className="col-span-2 rounded-2xl border p-6" style={{ background: "#111118", borderColor: "#1e1e2e" }}>
          <h2 className="font-bold mb-6">Revenus quotidiens (IA)</h2>
          <div className="flex items-end gap-2 h-40">
            {dailyRevenue.map((v, i) => (
              <div key={i} className="flex-1 flex flex-col items-center gap-1">
                <div className="w-full rounded-t-sm transition-all hover:opacity-80"
                  style={{
                    height: `${(v / maxRev) * 100}%`,
                    background: i === dailyRevenue.length - 1
                      ? "linear-gradient(180deg,#a855f7,#7c3aed)"
                      : "linear-gradient(180deg,rgba(168,85,247,0.4),rgba(124,58,237,0.2))",
                  }} />
              </div>
            ))}
          </div>
          <div className="flex justify-between text-xs mt-2" style={{ color: "#4b5563" }}>
            <span>J-14</span><span>J-7</span><span>Aujourd&apos;hui</span>
          </div>
        </div>

        {/* Top fans */}
        <div className="rounded-2xl border p-6" style={{ background: "#111118", borderColor: "#1e1e2e" }}>
          <h2 className="font-bold mb-4">Top fans</h2>
          <div className="space-y-3">
            {topFans.map((f) => (
              <div key={f.id} className="flex items-center gap-3">
                <span className="text-xs font-bold w-5 text-center" style={{ color: f.rank <= 3 ? "#f59e0b" : "#4b5563" }}>
                  #{f.rank}
                </span>
                <div className="flex-1 text-sm">
                  <div className="font-medium">{f.id}</div>
                  <div className="text-xs" style={{ color: "#6b7280" }}>{f.messages} messages</div>
                </div>
                <span className="text-sm font-bold" style={{ color: "#10b981" }}>{f.spent}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Breakdown */}
      <div className="grid grid-cols-3 gap-6 mt-6">
        {[
          { label: "Revenus PPV", value: "€2,184", pct: 56, color: "#a855f7" },
          { label: "Revenus relances", value: "€1,044", pct: 27, color: "#ec4899" },
          { label: "Revenus welcome", value: "€619", pct: 17, color: "#3b82f6" },
        ].map((r) => (
          <div key={r.label} className="p-5 rounded-2xl border" style={{ background: "#111118", borderColor: "#1e1e2e" }}>
            <div className="flex justify-between items-start mb-3">
              <span className="text-sm" style={{ color: "#9ca3af" }}>{r.label}</span>
              <span className="text-xs font-bold px-2 py-0.5 rounded-full"
                style={{ background: `${r.color}15`, color: r.color }}>{r.pct}%</span>
            </div>
            <div className="text-xl font-black mb-2">{r.value}</div>
            <div className="h-1.5 rounded-full" style={{ background: "#1e1e2e" }}>
              <div className="h-full rounded-full transition-all" style={{ width: `${r.pct}%`, background: r.color }} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
