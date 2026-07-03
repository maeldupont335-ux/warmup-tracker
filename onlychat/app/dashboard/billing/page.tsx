"use client";
import { useEffect, useState } from "react";
import { DollarSign, Star, CreditCard, CheckCircle, XCircle, Clock, ArrowDownLeft } from "lucide-react";

interface Transaction {
  id: string;
  type: string;
  amount: number;
  stars?: number;
  description: string;
  createdAt: string;
}

interface BillingData {
  userId: string;
  email: string;
  balance: number;
  totalStarsSold: number;
  totalRevenueUsd: number;
  totalCommissionUsd: number;
  licenseActive: boolean;
  licenseExpiry: string | null;
  transactions: Transaction[];
}

export default function BillingPage() {
  const [billing, setBilling] = useState<BillingData | null>(null);
  const [licensePrice, setLicensePrice] = useState(30);
  const [isAdmin, setIsAdmin] = useState(false);
  const [buying, setBuying] = useState(false);
  const [msg, setMsg] = useState("");

  async function load() {
    const r = await fetch("/api/billing");
    if (!r.ok) return;
    const d = await r.json();
    setBilling(d.billing);
    setLicensePrice(d.licensePrice);
    setIsAdmin(d.isAdmin);
  }

  useEffect(() => { load(); }, []);

  async function buyLicense() {
    setBuying(true);
    setMsg("");
    const r = await fetch("/api/billing", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "buy-license" }),
    });
    const d = await r.json();
    if (d.ok) { setMsg("✅ Licence activée avec succès !"); load(); }
    else setMsg(`❌ ${d.error}`);
    setBuying(false);
  }

  if (!billing) return (
    <div className="p-8 flex items-center justify-center" style={{ color: "#6b7280" }}>
      Chargement...
    </div>
  );

  const licenseOk = billing.licenseActive && billing.licenseExpiry && new Date(billing.licenseExpiry) > new Date();

  return (
    <div className="p-8" style={{ color: "#fff" }}>
      <div className="mb-8">
        <h1 className="text-2xl font-black">Facturation</h1>
        <p className="text-sm mt-1" style={{ color: "#6b7280" }}>{billing.email}</p>
      </div>

      {/* Solde + Licence */}
      <div className="grid grid-cols-3 gap-4 mb-8">
        <div className="p-6 rounded-2xl border" style={{ background: "#111118", borderColor: "#1e1e2e" }}>
          <div className="flex items-center gap-2 mb-2" style={{ color: "#6b7280" }}>
            <DollarSign size={16} />
            <span className="text-sm">Solde disponible</span>
          </div>
          <div className="text-3xl font-black" style={{ color: "#10b981" }}>
            ${billing.balance.toFixed(2)}
          </div>
        </div>

        <div className="p-6 rounded-2xl border" style={{ background: "#111118", borderColor: "#1e1e2e" }}>
          <div className="flex items-center gap-2 mb-2" style={{ color: "#6b7280" }}>
            <Star size={16} />
            <span className="text-sm">Stars vendues</span>
          </div>
          <div className="text-3xl font-black" style={{ color: "#f59e0b" }}>
            {billing.totalStarsSold.toLocaleString()}⭐
          </div>
          <div className="text-xs mt-1" style={{ color: "#6b7280" }}>
            Brut ${billing.totalRevenueUsd.toFixed(2)} · Commission ${billing.totalCommissionUsd.toFixed(2)}
          </div>
        </div>

        <div className="p-6 rounded-2xl border" style={{ background: "#111118", borderColor: "#1e1e2e" }}>
          <div className="flex items-center gap-2 mb-2" style={{ color: "#6b7280" }}>
            <CreditCard size={16} />
            <span className="text-sm">Licence</span>
          </div>
          {licenseOk ? (
            <>
              <div className="flex items-center gap-2" style={{ color: "#10b981" }}>
                <CheckCircle size={20} />
                <span className="text-lg font-bold">Active</span>
              </div>
              <div className="text-xs mt-1" style={{ color: "#6b7280" }}>
                Expire le {new Date(billing.licenseExpiry!).toLocaleDateString("fr-FR")}
              </div>
            </>
          ) : (
            <>
              <div className="flex items-center gap-2" style={{ color: "#ef4444" }}>
                <XCircle size={20} />
                <span className="text-lg font-bold">Inactive</span>
              </div>
              <button
                onClick={buyLicense}
                disabled={buying || billing.balance < licensePrice}
                className="mt-3 w-full py-2 rounded-lg text-sm font-bold transition-all"
                style={{
                  background: billing.balance >= licensePrice ? "rgba(168,85,247,0.15)" : "rgba(75,85,99,0.2)",
                  color: billing.balance >= licensePrice ? "#a855f7" : "#6b7280",
                  border: `1px solid ${billing.balance >= licensePrice ? "rgba(168,85,247,0.3)" : "#374151"}`,
                  cursor: billing.balance < licensePrice ? "not-allowed" : "pointer",
                }}>
                {buying ? "..." : `Acheter — $${licensePrice}`}
              </button>
              {billing.balance < licensePrice && (
                <div className="text-xs mt-1" style={{ color: "#6b7280" }}>
                  Solde insuffisant (${(licensePrice - billing.balance).toFixed(2)} manquant)
                </div>
              )}
            </>
          )}
        </div>
      </div>

      {msg && (
        <div className="mb-6 p-4 rounded-xl text-sm" style={{
          background: msg.startsWith("✅") ? "rgba(16,185,129,0.1)" : "rgba(239,68,68,0.1)",
          color: msg.startsWith("✅") ? "#10b981" : "#ef4444",
          border: `1px solid ${msg.startsWith("✅") ? "rgba(16,185,129,0.2)" : "rgba(239,68,68,0.2)"}`,
        }}>
          {msg}
        </div>
      )}

      {isAdmin && (
        <div className="mb-6 p-4 rounded-xl text-sm font-medium"
          style={{ background: "rgba(168,85,247,0.1)", color: "#a855f7", border: "1px solid rgba(168,85,247,0.2)" }}>
          Compte administrateur — Accéder au{" "}
          <a href="/dashboard/admin" style={{ textDecoration: "underline" }}>panneau admin</a>
        </div>
      )}

      {/* Historique transactions */}
      <div className="rounded-2xl border p-6" style={{ background: "#111118", borderColor: "#1e1e2e" }}>
        <h2 className="font-bold mb-4">Historique des transactions</h2>
        {billing.transactions.length === 0 ? (
          <p className="text-sm" style={{ color: "#6b7280" }}>Aucune transaction pour le moment.</p>
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
                        tx.type === "license" ? <CreditCard size={14} /> : <DollarSign size={14} />}
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
