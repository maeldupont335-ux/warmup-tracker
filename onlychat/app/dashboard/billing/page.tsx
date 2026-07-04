"use client";
import { useEffect, useState } from "react";
import { DollarSign, Star, CreditCard, CheckCircle, XCircle, Clock, ArrowDownLeft, RefreshCw, ToggleLeft, ToggleRight, X, MessageCircle } from "lucide-react";

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
  telegramLicensePool: number;
  transactions: Transaction[];
}
interface Creator { id: string; name: string; }

const LICENSE_PRICE = 30;

function BuyModal({ balance, onClose, onConfirm }: {
  balance: number;
  onClose: () => void;
  onConfirm: (qty: number) => Promise<void>;
}) {
  const [qty, setQty] = useState(1);
  const [confirming, setConfirming] = useState(false);
  const total = qty * LICENSE_PRICE;
  const newBalance = balance - total;
  const canBuy = newBalance >= 0;

  const handleConfirm = async () => {
    setConfirming(true);
    await onConfirm(qty);
    setConfirming(false);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: "rgba(0,0,0,0.75)" }}
      onClick={e => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="rounded-2xl border p-6 w-full max-w-md"
        style={{ background: "#111118", borderColor: "#1e1e2e" }}>
        <div className="flex items-center justify-between mb-6">
          <h2 className="font-bold text-lg" style={{ color: "#fff" }}>Purchase Licenses</h2>
          <button onClick={onClose} className="p-1 rounded hover:bg-white/10" style={{ color: "#6b7280" }}>
            <X size={18} />
          </button>
        </div>

        {/* Platform selector (Telegram only for now) */}
        <p className="text-sm mb-3" style={{ color: "#6b7280" }}>Choose license platform</p>
        <div className="grid grid-cols-2 gap-3 mb-5">
          <div className="p-4 rounded-xl border opacity-40 cursor-not-allowed"
            style={{ borderColor: "#1e1e2e", background: "#0d0d14" }}>
            <div className="flex items-center gap-2 mb-1">
              <Star size={14} style={{ color: "#6b7280" }} />
              <span className="text-sm font-semibold" style={{ color: "#9ca3af" }}>OnlyFans</span>
            </div>
            <div className="text-xs" style={{ color: "#4b5563" }}>Bientôt disponible</div>
          </div>
          <div className="p-4 rounded-xl border"
            style={{ borderColor: "#e11d48", background: "rgba(225,29,72,0.06)" }}>
            <div className="flex items-center gap-2 mb-1">
              <MessageCircle size={14} style={{ color: "#e11d48" }} />
              <span className="text-sm font-semibold" style={{ color: "#fff" }}>Telegram</span>
            </div>
            <div className="text-xs" style={{ color: "#9ca3af" }}>${LICENSE_PRICE}/month</div>
          </div>
        </div>

        {/* Info licence */}
        <div className="flex items-center justify-between px-4 py-3 rounded-xl mb-5"
          style={{ background: "#0d0d14", border: "1px solid #1e1e2e" }}>
          <span className="text-sm" style={{ color: "#9ca3af" }}>Telegram license</span>
          <span className="text-sm font-bold px-3 py-1 rounded-lg"
            style={{ background: "#1e1e2e", color: "#d1d5db" }}>${LICENSE_PRICE}/month</span>
        </div>

        {/* Quantité */}
        <p className="text-sm mb-2" style={{ color: "#6b7280" }}>How many licenses?</p>
        <input
          type="number" min={1} max={20} value={qty}
          onChange={e => setQty(Math.max(1, Math.min(20, parseInt(e.target.value) || 1)))}
          className="w-full px-4 py-3 rounded-xl text-sm outline-none mb-5"
          style={{ background: "#0d0d14", border: "1px solid #1e1e2e", color: "#fff" }}
        />

        {/* Confirmation */}
        <button
          onClick={handleConfirm}
          disabled={confirming || !canBuy}
          className="w-full py-3 rounded-xl text-sm font-bold transition-all mb-3"
          style={{
            background: canBuy ? "#e11d48" : "rgba(75,85,99,0.3)",
            color: canBuy ? "#fff" : "#6b7280",
            cursor: canBuy ? "pointer" : "not-allowed",
          }}>
          {confirming ? "Traitement..." : `Confirm Purchase ($${total})`}
        </button>

        <div className="text-xs text-center" style={{ color: newBalance < 0 ? "#ef4444" : "#6b7280" }}>
          {canBuy
            ? `New Balance after purchase: $${newBalance.toFixed(2)}`
            : `Solde insuffisant — il manque $${Math.abs(newBalance).toFixed(2)}`}
        </div>
      </div>
    </div>
  );
}

export default function BillingPage() {
  const [billing, setBilling] = useState<BillingData | null>(null);
  const [creators, setCreators] = useState<Creator[]>([]);
  const [isAdmin, setIsAdmin] = useState(false);
  const [loading, setLoading] = useState<Record<string, boolean>>({});
  const [msg, setMsg] = useState("");
  const [showBuyModal, setShowBuyModal] = useState(false);

  async function load() {
    const r = await fetch(`/api/billing?t=${Date.now()}`, { cache: "no-store" });
    if (!r.ok) return;
    const d = await r.json();
    setBilling(d.billing);
    setIsAdmin(d.isAdmin);
    setCreators(d.creators ?? []);
  }

  useEffect(() => {
    load();
    const interval = setInterval(load, 5000);
    return () => clearInterval(interval);
  }, []);

  function setL(key: string, v: boolean) { setLoading(p => ({ ...p, [key]: v })); }

  async function handleBuyPool(qty: number) {
    const r = await fetch("/api/billing", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "buy-telegram-licenses", quantity: qty }),
    });
    const d = await r.json();
    if (d.ok) { setMsg(`✅ ${qty} licence${qty > 1 ? "s" : ""} Telegram ajoutée${qty > 1 ? "s" : ""} !`); load(); }
    else setMsg(`❌ ${d.error}`);
    setShowBuyModal(false);
  }

  async function assignLicense(creatorId: string, creatorName: string) {
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

  async function suspendLicense(creatorId: string, creatorName: string) {
    setL(`sus_${creatorId}`, true); setMsg("");
    const r = await fetch("/api/billing", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "suspend-license", creatorId }),
    });
    const d = await r.json();
    if (d.ok) { setMsg(`⏸️ Licence suspendue pour ${creatorName} — jours restants conservés`); load(); }
    else setMsg(`❌ Erreur`);
    setL(`sus_${creatorId}`, false);
  }

  async function reactivateLicense(creatorId: string, creatorName: string) {
    setL(`sus_${creatorId}`, true); setMsg("");
    const r = await fetch("/api/billing", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "reactivate-license", creatorId }),
    });
    const d = await r.json();
    if (d.ok) { setMsg(`✅ Licence réactivée pour ${creatorName} !`); load(); }
    else setMsg(`❌ ${d.error}`);
    setL(`sus_${creatorId}`, false);
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

  const daysLeft = (expiry: string | null) =>
    expiry ? Math.max(0, Math.ceil((new Date(expiry).getTime() - Date.now()) / 86400000)) : 0;

  if (!billing) return (
    <div className="p-8 flex items-center justify-center h-64">
      <RefreshCw size={20} className="animate-spin" style={{ color: "#6b7280" }} />
    </div>
  );

  const activeLicenses = Object.values(billing.creatorLicenses ?? {})
    .filter(l => l.active && l.expiry && new Date(l.expiry) > new Date());
  const pool = billing.telegramLicensePool ?? 0;

  return (
    <div className="p-8" style={{ color: "#fff" }}>
      {showBuyModal && (
        <BuyModal
          balance={billing.balance}
          onClose={() => setShowBuyModal(false)}
          onConfirm={handleBuyPool}
        />
      )}

      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-black">Licenses</h1>
          <p className="text-sm mt-1" style={{ color: "#6b7280" }}>{billing.email}</p>
        </div>
        <button onClick={() => setShowBuyModal(true)}
          className="px-5 py-2.5 rounded-xl text-sm font-bold transition-all"
          style={{ background: "#e11d48", color: "#fff" }}>
          Buy Licenses
        </button>
      </div>

      {msg && (
        <div className="mb-6 p-4 rounded-xl text-sm" style={{
          background: msg.startsWith("✅") ? "rgba(16,185,129,0.1)" : "rgba(239,68,68,0.1)",
          color: msg.startsWith("✅") ? "#10b981" : "#ef4444",
          border: `1px solid ${msg.startsWith("✅") ? "rgba(16,185,129,0.2)" : "rgba(239,68,68,0.2)"}`,
        }}>{msg}</div>
      )}

      {/* Stats rapides */}
      <div className="grid grid-cols-4 gap-4 mb-6">
        {[
          { label: "OnlyFans Active", value: "0" },
          { label: "OnlyFans Available", value: "0" },
          { label: "Telegram Active", value: String(activeLicenses.length) },
          { label: "Telegram Available", value: String(pool) },
        ].map(s => (
          <div key={s.label} className="p-4 rounded-xl border" style={{ background: "#111118", borderColor: "#1e1e2e" }}>
            <div className="text-xs mb-1" style={{ color: "#6b7280" }}>{s.label}</div>
            <div className="text-2xl font-black">{s.value}</div>
          </div>
        ))}
      </div>

      {/* Solde */}
      <div className="p-4 rounded-xl border mb-6 flex items-center justify-between"
        style={{ background: "#111118", borderColor: "#1e1e2e" }}>
        <div className="flex items-center gap-2">
          <DollarSign size={16} style={{ color: "#10b981" }} />
          <span className="text-sm" style={{ color: "#6b7280" }}>Solde disponible</span>
        </div>
        <div className="flex items-center gap-4">
          <span className="text-2xl font-black" style={{ color: "#10b981" }}>${billing.balance.toFixed(2)}</span>
          <div className="text-xs" style={{ color: "#6b7280" }}>
            {pool} licence{pool !== 1 ? "s" : ""} dans le pool · ${LICENSE_PRICE}/créateur/mois
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-6 mb-6">
        {/* OnlyFans — bientôt */}
        <div className="rounded-2xl border p-6" style={{ background: "#111118", borderColor: "#1e1e2e" }}>
          <h2 className="font-bold mb-1">OnlyFans Licenses</h2>
          <p className="text-xs mb-4" style={{ color: "#6b7280" }}>Basic and Premium license inventory and assignments</p>
          {[
            ["Active licenses", "0"], ["Available licenses", "0"],
            ["Basic / Premium stock", "0 / 0"], ["Commission rate", "10%"],
          ].map(([k, v]) => (
            <div key={k} className="flex justify-between py-2 border-b text-sm" style={{ borderColor: "#1e1e2e" }}>
              <span style={{ color: "#9ca3af" }}>{k}</span>
              <span className="font-medium">{v}</span>
            </div>
          ))}
          <div className="flex justify-between text-xs mt-3 uppercase tracking-wider" style={{ color: "#4b5563" }}>
            <span>Creator</span><span>Type</span><span>Expires</span>
          </div>
          <p className="text-xs mt-3" style={{ color: "#4b5563" }}>No active OnlyFans licenses.</p>
        </div>

        {/* Telegram */}
        <div className="rounded-2xl border p-6" style={{ background: "#111118", borderColor: "#1e1e2e" }}>
          <h2 className="font-bold mb-1">Telegram Licenses</h2>
          <p className="text-xs mb-4" style={{ color: "#6b7280" }}>Telegram license assignments and availability</p>
          {[
            ["Active licenses", String(activeLicenses.length)],
            ["Available licenses", String(pool)],
            ["Price per license", `$${LICENSE_PRICE}`],
            ["Commission rate", "15%"],
          ].map(([k, v]) => (
            <div key={k} className="flex justify-between py-2 border-b text-sm" style={{ borderColor: "#1e1e2e" }}>
              <span style={{ color: "#9ca3af" }}>{k}</span>
              <span className="font-medium">{v}</span>
            </div>
          ))}
          <div className="flex justify-between text-xs mt-3 uppercase tracking-wider" style={{ color: "#4b5563" }}>
            <span>Creator</span><span>Expires</span>
          </div>
          {activeLicenses.length === 0 ? (
            <p className="text-xs mt-3" style={{ color: "#4b5563" }}>No active Telegram licenses.</p>
          ) : (
            <div className="mt-2 space-y-2">
              {activeLicenses.map(l => (
                <div key={l.creatorId} className="flex justify-between text-sm">
                  <span className="font-medium">{l.creatorName}</span>
                  <span style={{ color: "#a855f7" }}>
                    {l.expiry ? new Date(l.expiry).toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" }) : "—"}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Assigner licences aux créateurs */}
      {creators.length > 0 && (
        <div className="rounded-2xl border p-6 mb-6" style={{ background: "#111118", borderColor: "#1e1e2e" }}>
          <h2 className="font-bold mb-4 flex items-center gap-2">
            <MessageCircle size={16} style={{ color: "#e11d48" }} />
            Assigner les licences aux créateurs
          </h2>
          <div className="space-y-3">
            {creators.map(c => {
              const lic = billing.creatorLicenses?.[c.id];
              const active = lic?.active && lic?.expiry && new Date(lic.expiry) > new Date();
              const days = daysLeft(lic?.expiry ?? null);
              const canAssign = pool > 0 || billing.balance >= LICENSE_PRICE;

              return (
                <div key={c.id} className="flex items-center gap-4 p-4 rounded-xl border"
                  style={{ borderColor: active ? "rgba(16,185,129,0.2)" : "#1e1e2e", background: "#0d0d14" }}>
                  {active
                    ? <CheckCircle size={18} style={{ color: "#10b981" }} />
                    : <XCircle size={18} style={{ color: "#ef4444" }} />}

                  <div className="flex-1 min-w-0">
                    <div className="font-medium text-sm">{c.name}</div>
                    {active ? (
                      <div className="text-xs mt-0.5" style={{ color: days <= 5 ? "#f59e0b" : "#6b7280" }}>
                        Expire dans {days} jour{days !== 1 ? "s" : ""} · {new Date(lic!.expiry!).toLocaleDateString("fr-FR")}
                      </div>
                    ) : lic?.expiry && new Date(lic.expiry) > new Date() ? (
                      <div className="text-xs mt-0.5" style={{ color: "#f59e0b" }}>
                        ⏸ Suspendue · {daysLeft(lic.expiry)}j restants
                      </div>
                    ) : (
                      <div className="text-xs mt-0.5" style={{ color: "#6b7280" }}>
                        {lic?.expiry ? "Licence expirée" : "Aucune licence assignée"}
                      </div>
                    )}
                  </div>

                  {/* Auto-renew toggle */}
                  <div className="flex items-center gap-1.5">
                    <span className="text-xs" style={{ color: "#6b7280" }}>Auto</span>
                    <button onClick={() => toggleAutoRenew(c.id, lic?.autoRenew ?? false)}
                      disabled={loading[`ar_${c.id}`]}
                      style={{ color: lic?.autoRenew ? "#10b981" : "#4b5563" }}>
                      {lic?.autoRenew ? <ToggleRight size={22} /> : <ToggleLeft size={22} />}
                    </button>
                  </div>

                  {/* Suspendre / Réactiver */}
                  {active ? (
                    <button
                      onClick={() => suspendLicense(c.id, c.name)}
                      disabled={loading[`sus_${c.id}`]}
                      className="flex-shrink-0 px-3 py-2 rounded-lg text-xs font-bold"
                      style={{ background: "rgba(245,158,11,0.15)", color: "#f59e0b", opacity: loading[`sus_${c.id}`] ? 0.6 : 1 }}>
                      {loading[`sus_${c.id}`] ? "..." : "⏸ Suspendre"}
                    </button>
                  ) : lic?.expiry && new Date(lic.expiry) > new Date() ? (
                    <button
                      onClick={() => reactivateLicense(c.id, c.name)}
                      disabled={loading[`sus_${c.id}`]}
                      className="flex-shrink-0 px-3 py-2 rounded-lg text-xs font-bold"
                      style={{ background: "rgba(16,185,129,0.15)", color: "#10b981", opacity: loading[`sus_${c.id}`] ? 0.6 : 1 }}>
                      {loading[`sus_${c.id}`] ? "..." : "▶ Réactiver"}
                    </button>
                  ) : null}

                  <button
                    onClick={() => assignLicense(c.id, c.name)}
                    disabled={loading[c.id] || !canAssign}
                    className="flex-shrink-0 px-4 py-2 rounded-lg text-xs font-bold"
                    style={{
                      background: canAssign ? "#e11d48" : "rgba(75,85,99,0.2)",
                      color: canAssign ? "#fff" : "#6b7280",
                      cursor: canAssign ? "pointer" : "not-allowed",
                      opacity: loading[c.id] ? 0.6 : 1,
                    }}>
                    {loading[c.id] ? "..." : active ? "Renouveler" : pool > 0 ? "Assigner" : "Acheter — $30"}
                  </button>
                </div>
              );
            })}
          </div>
        </div>
      )}

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
            {billing.transactions.filter(tx => tx.amount !== 0).map((tx) => (
              <div key={tx.id} className="flex items-center justify-between py-3 border-b last:border-0"
                style={{ borderColor: "#1e1e2e" }}>
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-full flex items-center justify-center"
                    style={{
                      background: tx.amount > 0 ? "rgba(16,185,129,0.15)" : "rgba(239,68,68,0.15)",
                      color: tx.amount > 0 ? "#10b981" : "#ef4444",
                    }}>
                    {tx.type === "deposit" ? <ArrowDownLeft size={14} /> :
                      tx.type === "stars_sale" ? <Star size={14} /> : <CreditCard size={14} />}
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
