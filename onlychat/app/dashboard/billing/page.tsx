"use client";
import { useEffect, useState } from "react";
import { DollarSign, Star, CreditCard, CheckCircle, XCircle, Clock, ArrowDownLeft, RefreshCw, ToggleLeft, ToggleRight } from "lucide-react";

interface Transaction {
  id: string; type: string; amount: number; stars?: number;
  description: string; createdAt: string;
}
interface CreatorLicense {
  creatorId: string; creatorName: string;
  active: boolean; expiry: string | null; autoRenew: boolean;
}
interface BillingData {
  userId: string; email: string; balance: number;
  totalStarsSold: number; totalRevenueUsd: number; totalCommissionUsd: number;
  licenseActive: boolean; licenseExpiry: string | null;
  creatorLicenses: Record<string, CreatorLicense>;
  transactions: Transaction[];
}
interface Creator { id: string; name: string; }

export default function BillingPage() {
  const [billing, setBilling] = useState<BillingData | null>(null);
  const [creators, setCreators] = useState<Creator[]>([]);
  const [licensePrice] = useState(30);
  const [isAdmin, setIsAdmin] = useState(false);
  const [loading, setLoading] = useState<Record<string, boolean>>({});
  const [msg, setMsg] = useState("");

  async function load() {
    const r = await fetch("/api/billing");
    if (!r.ok) return;
    const d = await r.json();
    setBilling(d.billing);
    setIsAdmin(d.isAdmin);
    setCreators(d.creators ?? []);
  }

  useEffect(() => { load(); }, []);

  function setL(key: string, v: boolean) { setLoading(p => ({ ...p, [key]: v })); }

  async function buyLicense(creatorId: string, creatorName: string) {
    setL(creatorId, true); setMsg("");
    const r = await fetch("/api/billing", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "buy-creator-license", creatorId, creatorName }),
    });
    const d = await r.json();
    if (d.ok) { setMsg(`✅ Licence activée pour ${creatorName} !`); load(); }
    else setMsg(`❌ ${d.error}`);
    setL(creatorId, false);
  }

  async function toggleAutoRenew(creatorId: string, current: boolean) {
    setL(`ar_${creatorId}`, true);
    await fetch("/api/billing", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "toggle-autorenew", creatorId, autoRenew: !current }),
    });
    load();
    setL(`ar_${creatorId}`, false);
  }

  const daysLeft = (expiry: string | null) => {
    if (!expiry) return 0;
    return Math.max(0, Math.ceil((new Date(expiry).getTime() - Date.now()) / 86400000));
  };

  if (!billing) return (
    <div className="p-8 flex items-center justify-center h-64">
      <RefreshCw size={20} className="animate-spin" style={{ color: "#6b7280" }} />
    </div>
  );

  return (
    <div className="p-8" style={{ color: "#fff" }}>
      <div className="mb-8">
        <h1 className="text-2xl font-black">Facturation</h1>
        <p className="text-sm mt-1" style={{ color: "#6b7280" }}>{billing.email}</p>
      </div>

      {/* Solde + Stats */}
      <div className="grid grid-cols-3 gap-4 mb-8">
        <div className="p-6 rounded-2xl border" style={{ background: "#111118", borderColor: "#1e1e2e" }}>
          <div className="flex items-center gap-2 mb-2" style={{ color: "#6b7280" }}>
            <DollarSign size={16} /><span className="text-sm">Solde disponible</span>
          </div>
          <div className="text-3xl font-black" style={{ color: "#10b981" }}>${billing.balance.toFixed(2)}</div>
          <div className="text-xs mt-1" style={{ color: "#6b7280" }}>Chaque licence coûte ${licensePrice}/mois</div>
        </div>

        <div className="p-6 rounded-2xl border" style={{ background: "#111118", borderColor: "#1e1e2e" }}>
          <div className="flex items-center gap-2 mb-2" style={{ color: "#6b7280" }}>
            <Star size={16} /><span className="text-sm">Stars vendues</span>
          </div>
          <div className="text-3xl font-black" style={{ color: "#f59e0b" }}>{billing.totalStarsSold.toLocaleString()}⭐</div>
          <div className="text-xs mt-1" style={{ color: "#6b7280" }}>
            Brut ${billing.totalRevenueUsd.toFixed(2)} · Commission ${billing.totalCommissionUsd.toFixed(2)}
          </div>
        </div>

        <div className="p-6 rounded-2xl border" style={{ background: "#111118", borderColor: "#1e1e2e" }}>
          <div className="flex items-center gap-2 mb-2" style={{ color: "#6b7280" }}>
            <CreditCard size={16} /><span className="text-sm">Licences actives</span>
          </div>
          <div className="text-3xl font-black" style={{ color: "#a855f7" }}>
            {Object.values(billing.creatorLicenses ?? {}).filter(l => l.active && l.expiry && new Date(l.expiry) > new Date()).length}
            <span className="text-lg font-normal text-gray-500">/{creators.length}</span>
          </div>
          <div className="text-xs mt-1" style={{ color: "#6b7280" }}>créateurs actifs</div>
        </div>
      </div>

      {msg && (
        <div className="mb-6 p-4 rounded-xl text-sm" style={{
          background: msg.startsWith("✅") ? "rgba(16,185,129,0.1)" : "rgba(239,68,68,0.1)",
          color: msg.startsWith("✅") ? "#10b981" : "#ef4444",
          border: `1px solid ${msg.startsWith("✅") ? "rgba(16,185,129,0.2)" : "rgba(239,68,68,0.2)"}`,
        }}>{msg}</div>
      )}

      {/* Licences par créateur */}
      <div className="rounded-2xl border p-6 mb-6" style={{ background: "#111118", borderColor: "#1e1e2e" }}>
        <h2 className="font-bold mb-4 flex items-center gap-2">
          <CreditCard size={16} style={{ color: "#a855f7" }} />
          Licences par créateur
        </h2>

        {creators.length === 0 ? (
          <p className="text-sm" style={{ color: "#6b7280" }}>Aucun créateur configuré.</p>
        ) : (
          <div className="space-y-3">
            {creators.map(c => {
              const lic = billing.creatorLicenses?.[c.id];
              const active = lic?.active && lic?.expiry && new Date(lic.expiry) > new Date();
              const days = daysLeft(lic?.expiry ?? null);
              const canBuy = billing.balance >= licensePrice;

              return (
                <div key={c.id} className="flex items-center gap-4 p-4 rounded-xl border"
                  style={{ borderColor: active ? "rgba(16,185,129,0.2)" : "#1e1e2e", background: "#0d0d14" }}>

                  {/* Status icon */}
                  <div className="flex-shrink-0">
                    {active
                      ? <CheckCircle size={20} style={{ color: "#10b981" }} />
                      : <XCircle size={20} style={{ color: "#ef4444" }} />}
                  </div>

                  {/* Nom + infos */}
                  <div className="flex-1 min-w-0">
                    <div className="font-medium text-sm">{c.name}</div>
                    {active ? (
                      <div className="text-xs mt-0.5" style={{ color: days <= 5 ? "#f59e0b" : "#6b7280" }}>
                        Expire dans {days} jour{days !== 1 ? "s" : ""} · {new Date(lic!.expiry!).toLocaleDateString("fr-FR")}
                      </div>
                    ) : (
                      <div className="text-xs mt-0.5" style={{ color: "#6b7280" }}>
                        {lic?.expiry ? "Licence expirée" : "Aucune licence"}
                      </div>
                    )}
                  </div>

                  {/* Auto-renouvellement */}
                  <div className="flex items-center gap-2">
                    <span className="text-xs" style={{ color: "#6b7280" }}>Auto</span>
                    <button
                      onClick={() => toggleAutoRenew(c.id, lic?.autoRenew ?? false)}
                      disabled={loading[`ar_${c.id}`]}
                      style={{ color: lic?.autoRenew ? "#10b981" : "#4b5563" }}>
                      {lic?.autoRenew
                        ? <ToggleRight size={24} />
                        : <ToggleLeft size={24} />}
                    </button>
                  </div>

                  {/* Bouton acheter/renouveler */}
                  <button
                    onClick={() => buyLicense(c.id, c.name)}
                    disabled={loading[c.id] || !canBuy}
                    className="flex-shrink-0 px-4 py-2 rounded-lg text-xs font-bold transition-all"
                    style={{
                      background: canBuy ? "linear-gradient(135deg,#a855f7,#7c3aed)" : "rgba(75,85,99,0.2)",
                      color: canBuy ? "#fff" : "#6b7280",
                      cursor: canBuy ? "pointer" : "not-allowed",
                      opacity: loading[c.id] ? 0.6 : 1,
                    }}>
                    {loading[c.id] ? "..." : active ? "Renouveler" : "Activer — $30"}
                  </button>
                </div>
              );
            })}
          </div>
        )}

        {billing.balance < licensePrice && (
          <div className="mt-4 p-3 rounded-lg text-xs" style={{
            background: "rgba(239,68,68,0.08)", color: "#ef4444",
            border: "1px solid rgba(239,68,68,0.2)"
          }}>
            Solde insuffisant pour acheter une licence. Contacte l&apos;admin pour recharger ton compte.
          </div>
        )}
      </div>

      {isAdmin && (
        <div className="mb-6 p-4 rounded-xl text-sm font-medium"
          style={{ background: "rgba(168,85,247,0.1)", color: "#a855f7", border: "1px solid rgba(168,85,247,0.2)" }}>
          Compte administrateur —{" "}
          <a href="/dashboard/admin" style={{ textDecoration: "underline" }}>Panneau admin</a>
        </div>
      )}

      {/* Historique */}
      <div className="rounded-2xl border p-6" style={{ background: "#111118", borderColor: "#1e1e2e" }}>
        <h2 className="font-bold mb-4">Historique des transactions</h2>
        {billing.transactions.length === 0 ? (
          <p className="text-sm" style={{ color: "#6b7280" }}>Aucune transaction.</p>
        ) : (
          <div className="space-y-2">
            {billing.transactions.map((tx) => (
              <div key={tx.id} className="flex items-center justify-between py-3 border-b last:border-0"
                style={{ borderColor: "#1e1e2e" }}>
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-full flex items-center justify-center"
                    style={{
                      background: tx.amount > 0 ? "rgba(16,185,129,0.15)" : "rgba(239,68,68,0.15)",
                      color: tx.amount > 0 ? "#10b981" : "#ef4444",
                    }}>
                    {tx.type === "deposit" ? <ArrowDownLeft size={14} /> :
                      tx.type === "stars_sale" ? <Star size={14} /> :
                        <CreditCard size={14} />}
                  </div>
                  <div>
                    <div className="text-sm font-medium">{tx.description}</div>
                    <div className="flex items-center gap-1 text-xs" style={{ color: "#6b7280" }}>
                      <Clock size={10} />
                      {new Date(tx.createdAt).toLocaleString("fr-FR")}
                    </div>
                  </div>
                </div>
                <div className={`text-sm font-bold ${tx.amount > 0 ? "text-green-400" : "text-red-400"}`}>
                  {tx.amount > 0 ? "+" : ""}{tx.amount.toFixed(2)}$
                  {tx.stars ? <span className="ml-1 text-yellow-400">({tx.stars}⭐)</span> : null}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
