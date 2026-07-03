"use client";
import { useState } from "react";
import { TrendingUp, MessageCircle, DollarSign, Users, Zap, Clock, ToggleLeft, ToggleRight, ArrowUpRight } from "lucide-react";

const stats = [
  { label: "Revenus générés (IA)", value: "€3,847", change: "+28%", icon: DollarSign, color: "#10b981" },
  { label: "Messages envoyés", value: "1,204", change: "+14%", icon: MessageCircle, color: "#a855f7" },
  { label: "Taux de conversion PPV", value: "18.4%", change: "+3.2%", icon: TrendingUp, color: "#3b82f6" },
  { label: "Fans actifs", value: "847", change: "+52", icon: Users, color: "#f59e0b" },
];

const activity = [
  { fan: "fan_2847", action: "Achat PPV", amount: "€18", time: "il y a 2 min", type: "sale" },
  { fan: "fan_1093", action: "Nouveau message", amount: null, time: "il y a 5 min", type: "message" },
  { fan: "fan_5521", action: "Achat PPV", amount: "€25", time: "il y a 12 min", type: "sale" },
  { fan: "fan_0834", action: "Relance envoyée", amount: null, time: "il y a 18 min", type: "nudge" },
  { fan: "fan_3311", action: "Achat PPV", amount: "€12", time: "il y a 24 min", type: "sale" },
  { fan: "fan_7762", action: "Welcome message", amount: null, time: "il y a 31 min", type: "welcome" },
];

export default function DashboardPage() {
  const [aiActive, setAiActive] = useState(true);

  return (
    <div className="p-8" style={{ color: "#fff" }}>
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-black">Vue d&apos;ensemble</h1>
          <p className="text-sm mt-1" style={{ color: "#6b7280" }}>Aujourd&apos;hui — Mardi 1 juillet 2025</p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-3 px-4 py-2.5 rounded-xl border"
            style={{ background: "#111118", borderColor: "#1e1e2e" }}>
            <span className="text-sm font-medium" style={{ color: aiActive ? "#10b981" : "#6b7280" }}>
              IA {aiActive ? "Active" : "Inactive"}
            </span>
            <button onClick={() => setAiActive(!aiActive)} className="transition-all">
              {aiActive
                ? <ToggleRight size={24} style={{ color: "#10b981" }} />
                : <ToggleLeft size={24} style={{ color: "#4b5563" }} />}
            </button>
          </div>
          <div className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm"
            style={{ background: "rgba(168,85,247,0.1)", color: "#a855f7", border: "1px solid rgba(168,85,247,0.2)" }}>
            <Zap size={14} />
            <Clock size={14} />
            <span>00:00 – 23:59</span>
          </div>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-4 gap-4 mb-8">
        {stats.map((s) => (
          <div key={s.label} className="p-5 rounded-2xl border" style={{ background: "#111118", borderColor: "#1e1e2e" }}>
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs" style={{ color: "#6b7280" }}>{s.label}</span>
              <s.icon size={16} style={{ color: s.color }} />
            </div>
            <div className="text-2xl font-black mb-1">{s.value}</div>
            <div className="flex items-center gap-1 text-xs" style={{ color: "#10b981" }}>
              <ArrowUpRight size={12} />
              {s.change} ce mois
            </div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-3 gap-6">
        {/* Activity feed */}
        <div className="col-span-2 rounded-2xl border p-6" style={{ background: "#111118", borderColor: "#1e1e2e" }}>
          <h2 className="font-bold mb-4">Activité en temps réel</h2>
          <div className="space-y-3">
            {activity.map((a, i) => (
              <div key={i} className="flex items-center justify-between py-3 border-b last:border-0"
                style={{ borderColor: "#1e1e2e" }}>
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold"
                    style={{
                      background: a.type === "sale" ? "rgba(16,185,129,0.15)" : a.type === "message" ? "rgba(168,85,247,0.15)" : "rgba(59,130,246,0.15)",
                      color: a.type === "sale" ? "#10b981" : a.type === "message" ? "#a855f7" : "#3b82f6",
                    }}>
                    {a.type === "sale" ? "€" : a.type === "message" ? "✉" : "↩"}
                  </div>
                  <div>
                    <div className="text-sm font-medium">{a.action}</div>
                    <div className="text-xs" style={{ color: "#6b7280" }}>{a.fan}</div>
                  </div>
                </div>
                <div className="text-right">
                  {a.amount && <div className="text-sm font-bold" style={{ color: "#10b981" }}>{a.amount}</div>}
                  <div className="text-xs" style={{ color: "#4b5563" }}>{a.time}</div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Quick stats side */}
        <div className="space-y-4">
          <div className="rounded-2xl border p-5" style={{ background: "#111118", borderColor: "#1e1e2e" }}>
            <h3 className="font-bold text-sm mb-4">Performance IA</h3>
            <div className="space-y-3">
              {[
                { label: "Taux de réponse", value: "99.2%", bar: 99 },
                { label: "Satisfaction fans", value: "94%", bar: 94 },
                { label: "PPV converties", value: "18.4%", bar: 18 },
              ].map((m) => (
                <div key={m.label}>
                  <div className="flex justify-between text-xs mb-1">
                    <span style={{ color: "#9ca3af" }}>{m.label}</span>
                    <span className="font-medium">{m.value}</span>
                  </div>
                  <div className="h-1.5 rounded-full" style={{ background: "#1e1e2e" }}>
                    <div className="h-full rounded-full" style={{ width: `${m.bar}%`, background: "linear-gradient(90deg,#a855f7,#7c3aed)" }} />
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-2xl border p-5" style={{ background: "#111118", borderColor: "#1e1e2e" }}>
            <h3 className="font-bold text-sm mb-4">Revenus du jour</h3>
            <div className="text-3xl font-black mb-1" style={{ color: "#10b981" }}>€284</div>
            <div className="text-xs" style={{ color: "#6b7280" }}>+12% vs hier</div>
            <div className="mt-4 space-y-2">
              {[
                { label: "PPV vendus", value: "€198" },
                { label: "Relances", value: "€56" },
                { label: "Welcome", value: "€30" },
              ].map((r) => (
                <div key={r.label} className="flex justify-between text-sm">
                  <span style={{ color: "#6b7280" }}>{r.label}</span>
                  <span className="font-medium">{r.value}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
