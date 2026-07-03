"use client";
import { useEffect, useState } from "react";
import { DollarSign, Star, Users, CreditCard, ArrowUpRight, Send } from "lucide-react";

interface UserBilling {
  userId: string;
  email: string;
  balance: number;
  totalStarsSold: number;
  totalRevenueUsd: number;
  totalCommissionUsd: number;
  licenseActive: boolean;
  licenseExpiry: string | null;
  transactions: { id: string; type: string; amount: number; stars?: number; description: string; createdAt: string }[];
}

interface PlatformStats {
  totalUsers: number;
  totalRevenueUsd: number;
  totalCommissionUsd: number;
  totalStarsSold: number;
  users: UserBilling[];
}

export default function AdminPage() {
  const [stats, setStats] = useState<PlatformStats | null>(null);
  const [depositUserId, setDepositUserId] = useState("");
  const [depositAmount, setDepositAmount] = useState("");
  const [selfAmount, setSelfAmount] = useState("");
  const [msg, setMsg] = useState("");
  const [loading, setLoading] = useState(false);

  async function load() {
    const r = await fetch("/api/billing?admin=1");
    if (r.ok) setStats(await r.json());
    else setMsg("❌ Accès refusé — compte admin requis");
  }

  useEffect(() => { load(); }, []);

  async function deposit(targetUserId: string, amount: number, self = false) {
    setLoading(true); setMsg("");
    const r = await fetch("/api/billing", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: self ? "self-deposit" : "deposit", targetUserId, amount }),
    });
    const d = await r.json();
    if (d.ok) { setMsg(`✅ Dépôt de $${amount} effectué`); load(); setDepositAmount(""); setSelfAmount(""); }
    else setMsg(`❌ ${d.error}`);
    setLoading(false);
  }

  if (!stats) return (
    <div className="p-8 flex items-center justify-center" style={{ color: "#6b7280" }}>
      {msg || "Chargement..."}
    </div>
  );

  const licenseExpiry = (u: UserBilling) =>
    u.licenseActive && u.licenseExpiry && new Date(u.licenseExpiry) > new Date();

  return (
    <div className="p-8" style={{ color: "#fff" }}>
      <div className="mb-8">
        <h1 className="text-2xl font-black">Panneau Admin</h1>
        <p className="text-sm mt-1" style={{ color: "#6b7280" }}>Statistiques globales de la plateforme</p>
      </div>

      {/* Stats globales */}
      <div className="grid grid-cols-4 gap-4 mb-8">
        {[
          { label: "Utilisateurs", value: stats.totalUsers, icon: Users, color: "#a855f7", suffix: "" },
          { label: "Revenus bruts", value: `$${stats.totalRevenueUsd.toFixed(2)}`, icon: DollarSign, color: "#10b981", suffix: "" },
          { label: "Commissions (10%)", value: `$${stats.totalCommissionUsd.toFixed(2)}`, icon: ArrowUpRight, color: "#3b82f6", suffix: "" },
          { label: "Stars vendues", value: stats.totalStarsSold.toLocaleString(), icon: Star, color: "#f59e0b", suffix: "⭐" },
        ].map((s) => (
          <div key={s.label} className="p-5 rounded-2xl border" style={{ background: "#111118", borderColor: "#1e1e2e" }}>
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs" style={{ color: "#6b7280" }}>{s.label}</span>
              <s.icon size={16} style={{ color: s.color }} />
            </div>
            <div className="text-2xl font-black">{s.value}{s.suffix}</div>
          </div>
        ))}
      </div>

      {/* Dépôt sur mon propre compte */}
      <div className="rounded-2xl border p-6 mb-6" style={{ background: "#111118", borderColor: "#1e1e2e" }}>
        <h2 className="font-bold mb-4">Créditer mon compte admin</h2>
        <div className="flex gap-3">
          <input
            type="number" min="1" placeholder="Montant en $"
            value={selfAmount} onChange={e => setSelfAmount(e.target.value)}
            className="flex-1 px-4 py-2 rounded-lg text-sm outline-none"
            style={{ background: "#0d0d14", border: "1px solid #1e1e2e", color: "#fff" }}
          />
          <button
            onClick={() => selfAmount && deposit("", Number(selfAmount), true)}
            disabled={loading || !selfAmount}
            className="px-5 py-2 rounded-lg text-sm font-bold flex items-center gap-2 transition-all"
            style={{ background: "rgba(16,185,129,0.15)", color: "#10b981", border: "1px solid rgba(16,185,129,0.2)" }}>
            <Send size={14} />
            Déposer
          </button>
        </div>
      </div>

      {msg && (
        <div className="mb-6 p-4 rounded-xl text-sm"
          style={{
            background: msg.startsWith("✅") ? "rgba(16,185,129,0.1)" : "rgba(239,68,68,0.1)",
            color: msg.startsWith("✅") ? "#10b981" : "#ef4444",
            border: `1px solid ${msg.startsWith("✅") ? "rgba(16,185,129,0.2)" : "rgba(239,68,68,0.2)"}`,
          }}>
          {msg}
        </div>
      )}

      {/* Tableau utilisateurs */}
      <div className="rounded-2xl border p-6" style={{ background: "#111118", borderColor: "#1e1e2e" }}>
        <h2 className="font-bold mb-4">Utilisateurs ({stats.users.length})</h2>
        {stats.users.length === 0 ? (
          <p className="text-sm" style={{ color: "#6b7280" }}>Aucun utilisateur enregistré.</p>
        ) : (
          <div className="space-y-3">
            {stats.users.map((u) => (
              <div key={u.userId} className="p-4 rounded-xl border" style={{ borderColor: "#1e1e2e", background: "#0d0d14" }}>
                <div className="flex items-center justify-between mb-3">
                  <div>
                    <div className="font-medium text-sm">{u.email || u.userId.slice(0, 12) + "..."}</div>
                    <div className="flex items-center gap-3 mt-1">
                      <span className="text-xs px-2 py-0.5 rounded-full"
                        style={{
                          background: licenseExpiry(u) ? "rgba(16,185,129,0.15)" : "rgba(239,68,68,0.1)",
                          color: licenseExpiry(u) ? "#10b981" : "#ef4444",
                        }}>
                        {licenseExpiry(u) ? "✓ Licence active" : "✗ Sans licence"}
                      </span>
                      <span className="text-xs" style={{ color: "#6b7280" }}>
                        {u.totalStarsSold}⭐ · ${u.totalRevenueUsd.toFixed(2)} brut · ${u.totalCommissionUsd.toFixed(2)} commission
                      </span>
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="text-lg font-black" style={{ color: "#10b981" }}>${u.balance.toFixed(2)}</div>
                    <div className="text-xs" style={{ color: "#6b7280" }}>solde</div>
                  </div>
                </div>

                {/* Dépôt pour cet utilisateur */}
                <div className="flex gap-2">
                  <input
                    type="number" min="1" placeholder="Montant à déposer ($)"
                    id={`dep-${u.userId}`}
                    className="flex-1 px-3 py-1.5 rounded-lg text-xs outline-none"
                    style={{ background: "#111118", border: "1px solid #1e1e2e", color: "#fff" }}
                  />
                  <button
                    disabled={loading}
                    onClick={() => {
                      const el = document.getElementById(`dep-${u.userId}`) as HTMLInputElement;
                      if (el?.value) deposit(u.userId, Number(el.value));
                    }}
                    className="px-4 py-1.5 rounded-lg text-xs font-bold flex items-center gap-1 transition-all"
                    style={{ background: "rgba(168,85,247,0.15)", color: "#a855f7", border: "1px solid rgba(168,85,247,0.2)" }}>
                    <CreditCard size={12} />
                    Créditer
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
