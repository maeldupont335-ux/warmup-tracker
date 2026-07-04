"use client";
import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import {
  Plus, Trash2, RefreshCw, Search, CheckCircle,
  AlertCircle, ChevronLeft, ChevronRight, Zap, Lock, ShoppingCart
} from "lucide-react";

interface Creator {
  id: string;
  name: string;
  botUsername: string;
  businessConnection: string | null;
  license: "none" | "telegram" | "onlyfans";
  syncStatus: "active" | "inactive";
  autoRenew: boolean;
  enableIA: boolean;
  webhookSet: boolean;
  createdAt: string;
}

interface BillingState {
  pool: number;
  balance: number;
  activeCreatorIds: string[];
}

function Toggle({ value, onChange, disabled }: { value: boolean; onChange: (v: boolean) => void; disabled?: boolean }) {
  if (disabled) {
    return (
      <div className="relative w-11 h-6 rounded-full flex-shrink-0 opacity-30 cursor-not-allowed"
        style={{ background: "#374151" }}>
        <div className="absolute top-0.5 left-[2px] w-5 h-5 rounded-full bg-white shadow" />
      </div>
    );
  }
  return (
    <button onClick={() => onChange(!value)}
      className="relative w-11 h-6 rounded-full transition-all flex-shrink-0"
      style={{ background: value ? "#e11d48" : "#374151" }}>
      <div className="absolute top-0.5 w-5 h-5 rounded-full bg-white transition-all shadow"
        style={{ left: value ? "calc(100% - 22px)" : "2px" }} />
    </button>
  );
}

export default function CreatorsPage() {
  const router = useRouter();
  const [tab, setTab] = useState<"onlyfans" | "telegram">("telegram");
  const [creators, setCreators] = useState<Creator[]>([]);
  const [billing, setBilling] = useState<BillingState>({ pool: 0, balance: 0, activeCreatorIds: [] });
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [showNoLicenseModal, setShowNoLicenseModal] = useState(false);
  const [showBusinessModal, setShowBusinessModal] = useState<Creator | null>(null);
  const [businessInput, setBusinessInput] = useState("");
  const [webhookLoading, setWebhookLoading] = useState<string | null>(null);
  const [webhookError, setWebhookError] = useState<Record<string, string>>({});
  const [assigningId, setAssigningId] = useState<string | null>(null);

  const [newName, setNewName] = useState("");
  const [newToken, setNewToken] = useState("");
  const [adding, setAdding] = useState(false);
  const [addError, setAddError] = useState("");

  const appUrl = typeof window !== "undefined" ? window.location.origin : "";

  const fetchBilling = useCallback(async () => {
    try {
      const res = await fetch(`/api/billing?t=${Date.now()}`, { cache: "no-store" });
      if (!res.ok) return;
      const d = await res.json();
      const activeCreatorIds: string[] = (d.creatorLicenses ?? [])
        .filter((l: { active: boolean; expiry: string }) => l.active && new Date(l.expiry) > new Date())
        .map((l: { creatorId: string }) => l.creatorId);
      setBilling({
        pool: d.telegramLicensePool ?? 0,
        balance: d.balance ?? 0,
        activeCreatorIds,
      });
    } catch { /* ignore */ }
  }, []);

  const fetch_ = useCallback(async () => {
    setLoading(true);
    const res = await fetch("/api/creators");
    const d = await res.json();
    setCreators(d.creators ?? []);
    setLoading(false);
  }, []);

  useEffect(() => { fetch_(); fetchBilling(); }, [fetch_, fetchBilling]);

  const action = async (id: string, actionName: string, extra?: Record<string, unknown>) => {
    await fetch("/api/creators", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: actionName, id, appUrl, ...extra }),
    });
    fetch_();
  };

  const handleAssignLicense = async (creator: Creator) => {
    const canAssign = billing.pool > 0 || billing.balance >= 30;
    if (!canAssign) { setShowNoLicenseModal(true); return; }
    setAssigningId(creator.id);
    try {
      const res = await fetch("/api/billing", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "buy-creator-license", creatorId: creator.id, creatorName: creator.name }),
      });
      if (res.ok) { await Promise.all([fetch_(), fetchBilling()]); }
    } finally { setAssigningId(null); }
  };

  const handleAdd = async () => {
    if (!newName.trim() || !newToken.trim()) return;
    setAdding(true); setAddError("");
    const res = await fetch("/api/creators", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: newName.trim(), botToken: newToken.trim() }),
    });
    const d = await res.json();
    if (!res.ok) { setAddError(d.error); setAdding(false); return; }
    setShowModal(false); setNewName(""); setNewToken(""); setAdding(false);
    fetch_();
  };

  const handleDelete = async (id: string) => {
    if (!confirm("Supprimer ce createur ?")) return;
    await fetch("/api/creators", {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id }),
    });
    fetch_();
  };

  const handleSetWebhook = async (id: string) => {
    setWebhookLoading(id);
    setWebhookError(e => ({ ...e, [id]: "" }));
    try {
      const res = await fetch("/api/creators", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "set-webhook", id, appUrl }),
      });
      const d = await res.json();
      if (!res.ok || !d.ok) {
        setWebhookError(e => ({ ...e, [id]: d.error ?? "Erreur inconnue" }));
      } else { fetch_(); }
    } catch (err) { setWebhookError(e => ({ ...e, [id]: String(err) })); }
    setWebhookLoading(null);
  };

  const handleSetBusiness = async () => {
    if (!showBusinessModal) return;
    await action(showBusinessModal.id, "set-business", { username: businessInput });
    setShowBusinessModal(null); setBusinessInput("");
  };

  const filtered = creators.filter(c =>
    c.name.toLowerCase().includes(search.toLowerCase()) ||
    c.botUsername.toLowerCase().includes(search.toLowerCase())
  );

  const formatDate = (d: string) =>
    new Date(d).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric", hour: "2-digit", minute: "2-digit" });

  return (
    <div className="p-8" style={{ color: "#fff", minHeight: "100vh" }}>
      <div className="mb-6">
        <h1 className="text-2xl font-bold mb-1">Creators</h1>
        <p className="text-sm" style={{ color: "#9ca3af" }}>Manage and monitor all your creators (OnlyFans and Telegram)</p>
      </div>

      <div className="flex gap-1 mb-8">
        {(["onlyfans", "telegram"] as const).map(t => (
          <button key={t} onClick={() => setTab(t)}
            className="px-5 py-2 rounded-lg text-sm font-medium transition-all border"
            style={tab === t
              ? { background: "#1e1e2e", color: "#fff", borderColor: "#3a3a4e" }
              : { background: "transparent", color: "#6b7280", borderColor: "transparent" }}>
            {t === "onlyfans" ? "Creators OnlyFans" : "Creators Telegram"}
          </button>
        ))}
      </div>

      {tab === "onlyfans" && (
        <div className="flex items-center justify-center h-48 rounded-2xl border" style={{ borderColor: "#1e1e2e", color: "#4b5563" }}>
          <p className="text-sm">Integration OnlyFans - bientot disponible</p>
        </div>
      )}

      {tab === "telegram" && (
        <>
          <div className="flex items-center justify-between mb-5 px-4 py-3 rounded-xl border"
            style={{ background: "#0d0d14", borderColor: "#1e1e2e" }}>
            <div className="flex items-center gap-4 text-sm">
              <span style={{ color: "#6b7280" }}>Licences disponibles :</span>
              <span className="font-bold" style={{ color: billing.pool > 0 ? "#10b981" : "#e11d48" }}>
                {billing.pool} dans le pool
              </span>
              <span style={{ color: "#4b5563" }}>·</span>
              <span style={{ color: "#9ca3af" }}>Solde : <strong style={{ color: "#fff" }}>${billing.balance.toFixed(2)}</strong></span>
            </div>
            <button onClick={() => router.push("/dashboard/billing")}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all hover:opacity-90"
              style={{ background: "#1e1e2e", color: "#9ca3af", border: "1px solid #2a2a3e" }}>
              <ShoppingCart size={12} /> Acheter des licences
            </button>
          </div>

          <div className="flex items-start justify-between mb-5">
            <div>
              <h2 className="font-bold text-lg mb-1">My Telegram creators</h2>
              <p className="text-sm" style={{ color: "#9ca3af" }}>Connect bots you created with BotFather to manage your subscribers and messages.</p>
            </div>
            <button onClick={() => { setShowModal(true); setAddError(""); setNewName(""); setNewToken(""); }}
              className="flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium transition-all hover:opacity-90"
              style={{ background: "#e11d48", color: "#fff" }}>
              <Plus size={15} />
              Add a creator
            </button>
          </div>

          <div className="flex items-center gap-3 mb-5">
            <div className="relative flex-1 max-w-sm">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: "#6b7280" }} />
              <input value={search} onChange={e => setSearch(e.target.value)}
                placeholder="Search creators by name or username..."
                className="w-full pl-9 pr-4 py-2.5 rounded-lg text-sm outline-none"
                style={{ background: "#111118", border: "1px solid #1e1e2e", color: "#d1d5db" }} />
            </div>
            <button onClick={() => { fetch_(); fetchBilling(); }} className="flex items-center gap-2 px-3 py-2.5 rounded-lg text-sm border transition-all hover:bg-white/5"
              style={{ borderColor: "#1e1e2e", color: "#6b7280" }}>
              <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
              Status
            </button>
          </div>

          <div className="rounded-xl border overflow-hidden" style={{ borderColor: "#1e1e2e" }}>
            <table className="w-full text-sm">
              <thead>
                <tr style={{ background: "#0d0d14", borderBottom: "1px solid #1e1e2e" }}>
                  {["Name", "Bot username", "Business Connection", "License", "Sync Status", "Created at", "Auto Renew", "Enable IA", "", ""].map(h => (
                    <th key={h} className="text-left px-4 py-3 font-medium" style={{ color: "#6b7280", whiteSpace: "nowrap" }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr><td colSpan={10} className="text-center py-12" style={{ color: "#4b5563" }}>
                    <RefreshCw size={18} className="animate-spin mx-auto mb-2" />Chargement...
                  </td></tr>
                ) : filtered.length === 0 ? (
                  <tr><td colSpan={10} className="text-center py-12" style={{ color: "#4b5563" }}>
                    Aucun createur - clique "Add a creator" pour commencer
                  </td></tr>
                ) : filtered.map((c, i) => {
                  const hasLicense = billing.activeCreatorIds.includes(c.id);
                  return (
                    <tr key={c.id}
                      onClick={() => router.push(`/dashboard/creators/${c.id}`)}
                      style={{ borderBottom: i < filtered.length - 1 ? "1px solid #1a1a28" : "none", background: "#0f0f1a", cursor: "pointer" }}
                      className="hover:bg-white/[0.02] transition-colors">
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <div className="w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0"
                            style={{ background: "#1e1e2e", color: "#e11d48", border: "1px solid #2a1a20" }}>
                            <span style={{ fontSize: 16 }}>👤</span>
                          </div>
                          <div className="flex flex-col">
                            <span className="font-medium">{c.name}</span>
                            {!hasLicense && c.webhookSet && (
                              <span className="text-xs flex items-center gap-1" style={{ color: "#f59e0b" }}>
                                <Lock size={10} /> Licence requise
                              </span>
                            )}
                          </div>
                        </div>
                      </td>

                      <td className="px-4 py-3" style={{ color: "#9ca3af" }}>{c.botUsername}</td>

                      <td className="px-4 py-3" onClick={e => e.stopPropagation()}>
                        {c.businessConnection ? (
                          <button onClick={() => { setShowBusinessModal(c); setBusinessInput(c.businessConnection ?? ""); }}
                            className="px-2.5 py-1 rounded-lg text-xs font-medium"
                            style={{ background: "#1e1e2e", color: "#d1d5db", border: "1px solid #2a2a3e" }}>
                            {c.businessConnection}
                          </button>
                        ) : (
                          <button onClick={() => { setShowBusinessModal(c); setBusinessInput(""); }}
                            className="text-xs hover:underline" style={{ color: "#6b7280" }}>
                            Not connected
                          </button>
                        )}
                      </td>

                      <td className="px-4 py-3">
                        {!hasLicense ? (
                          <span className="text-xs" style={{ color: "#6b7280" }}>No telegram license</span>
                        ) : (
                          <span className="px-2.5 py-1 rounded-lg text-xs font-medium"
                            style={{ background: "rgba(16,185,129,0.12)", color: "#10b981", border: "1px solid rgba(16,185,129,0.25)" }}>
                            Active
                          </span>
                        )}
                      </td>

                      <td className="px-4 py-3">
                        <span className="px-2.5 py-1 rounded-full text-xs font-medium"
                          style={{
                            background: c.syncStatus === "active" ? "rgba(16,185,129,0.12)" : "rgba(75,85,99,0.2)",
                            color: c.syncStatus === "active" ? "#10b981" : "#6b7280",
                            border: `1px solid ${c.syncStatus === "active" ? "rgba(16,185,129,0.25)" : "rgba(75,85,99,0.3)"}`,
                          }}>
                          {c.syncStatus}
                        </span>
                      </td>

                      <td className="px-4 py-3 text-xs" style={{ color: "#6b7280", whiteSpace: "nowrap" }}>
                        {formatDate(c.createdAt)}
                      </td>

                      <td className="px-4 py-3" onClick={e => e.stopPropagation()}>
                        {!hasLicense
                          ? <span style={{ color: "#4b5563" }}>-</span>
                          : <Toggle value={c.autoRenew} onChange={v => action(c.id, "toggle-renew", { value: v })} />}
                      </td>

                      <td className="px-4 py-3" onClick={e => e.stopPropagation()}>
                        <Toggle
                          value={c.enableIA}
                          disabled={!hasLicense}
                          onChange={v => action(c.id, "toggle-ia", { value: v })}
                        />
                      </td>

                      <td className="px-4 py-3" onClick={e => e.stopPropagation()}>
                        <button onClick={() => handleDelete(c.id)}
                          className="p-1.5 rounded-lg transition-all hover:bg-red-500/10"
                          style={{ color: "#e11d48", border: "1px solid rgba(225,29,72,0.2)" }}>
                          <Trash2 size={13} />
                        </button>
                      </td>

                      <td className="px-4 py-3" onClick={e => e.stopPropagation()}>
                        {!c.webhookSet ? (
                          <div className="flex flex-col gap-1">
                            <button onClick={() => handleSetWebhook(c.id)}
                              disabled={webhookLoading === c.id}
                              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all hover:opacity-90 disabled:opacity-50"
                              style={{ background: "#e11d48", color: "#fff" }}>
                              {webhookLoading === c.id ? <RefreshCw size={11} className="animate-spin" /> : <Zap size={11} />}
                              Activer
                            </button>
                            {webhookError[c.id] && (
                              <p className="text-xs max-w-[180px] leading-tight" style={{ color: "#f87171" }}>
                                {webhookError[c.id]}
                              </p>
                            )}
                          </div>
                        ) : !hasLicense ? (
                          <button
                            onClick={() => handleAssignLicense(c)}
                            disabled={assigningId === c.id}
                            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all hover:opacity-90 disabled:opacity-50"
                            style={{ background: "#7c3aed", color: "#fff" }}>
                            {assigningId === c.id
                              ? <RefreshCw size={11} className="animate-spin" />
                              : <Lock size={11} />}
                            {assigningId === c.id ? "En cours..." : "Assigner licence"}
                          </button>
                        ) : (
                          <div className="flex items-center gap-1 text-xs" style={{ color: "#10b981" }}>
                            <CheckCircle size={12} /> Actif
                          </div>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <div className="flex items-center justify-end gap-3 mt-4 text-sm" style={{ color: "#6b7280" }}>
            <span>Rows per page</span>
            <select className="px-2 py-1 rounded text-xs outline-none" style={{ background: "#111118", border: "1px solid #1e1e2e", color: "#d1d5db" }}>
              <option>10</option>
            </select>
            <span>Page 1 of 1</span>
            <div className="flex gap-1">
              {[ChevronLeft, ChevronLeft, ChevronRight, ChevronRight].map((Icon, idx) => (
                <button key={idx} className="p-1 rounded hover:bg-white/5"><Icon size={14} /></button>
              ))}
            </div>
          </div>
        </>
      )}

      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center px-4"
          style={{ background: "rgba(0,0,0,0.8)" }} onClick={() => setShowModal(false)}>
          <div className="w-full max-w-md rounded-2xl border p-6" style={{ background: "#111118", borderColor: "#1e1e2e" }}
            onClick={e => e.stopPropagation()}>
            <h2 className="font-black text-lg mb-1">Add a creator</h2>
            <p className="text-sm mb-5" style={{ color: "#6b7280" }}>Cree un bot sur @BotFather et colle le token ici</p>
            <div className="space-y-4">
              <div>
                <label className="block text-xs mb-1.5" style={{ color: "#6b7280" }}>Nom de la creatrice</label>
                <input value={newName} onChange={e => setNewName(e.target.value)} placeholder="Ex: Pauline, Alexya..."
                  className="w-full px-4 py-2.5 rounded-xl text-sm outline-none"
                  style={{ background: "#0a0a0f", border: "1px solid #1e1e2e", color: "#fff" }} />
              </div>
              <div>
                <label className="block text-xs mb-1.5" style={{ color: "#6b7280" }}>Token du bot (@BotFather)</label>
                <input value={newToken} onChange={e => setNewToken(e.target.value)} placeholder="1234567890:AAFxxxxxxxxxxxxxxx"
                  className="w-full px-4 py-2.5 rounded-xl text-sm outline-none font-mono"
                  style={{ background: "#0a0a0f", border: "1px solid #1e1e2e", color: "#d1d5db" }} />
              </div>
              <div className="p-3 rounded-xl text-xs" style={{ background: "rgba(59,130,246,0.06)", color: "#93c5fd", border: "1px solid rgba(59,130,246,0.15)" }}>
                Telegram -&gt; @BotFather -&gt; /newbot -&gt; copie le token
              </div>
              {addError && (
                <div className="flex items-center gap-2 p-3 rounded-xl text-sm"
                  style={{ background: "rgba(239,68,68,0.08)", color: "#fca5a5", border: "1px solid rgba(239,68,68,0.2)" }}>
                  <AlertCircle size={13} />{addError}
                </div>
              )}
              <div className="flex gap-3">
                <button onClick={() => setShowModal(false)} className="flex-1 py-2.5 rounded-xl text-sm border" style={{ borderColor: "#1e1e2e", color: "#9ca3af" }}>Annuler</button>
                <button onClick={handleAdd} disabled={adding || !newName || !newToken}
                  className="flex-1 py-2.5 rounded-xl text-sm font-medium disabled:opacity-40 flex items-center justify-center gap-2"
                  style={{ background: "#e11d48", color: "#fff" }}>
                  {adding ? <RefreshCw size={13} className="animate-spin" /> : <Plus size={13} />}
                  {adding ? "Verification..." : "Add creator"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {showBusinessModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center px-4"
          style={{ background: "rgba(0,0,0,0.8)" }} onClick={() => setShowBusinessModal(null)}>
          <div className="w-full max-w-sm rounded-2xl border p-6" style={{ background: "#111118", borderColor: "#1e1e2e" }}
            onClick={e => e.stopPropagation()}>
            <h2 className="font-bold mb-1">Business Connection</h2>
            <p className="text-sm mb-4" style={{ color: "#6b7280" }}>@username du compte Telegram Business connecte</p>
            <input value={businessInput} onChange={e => setBusinessInput(e.target.value)} placeholder="@paupauxx"
              className="w-full px-4 py-2.5 rounded-xl text-sm outline-none mb-4"
              style={{ background: "#0a0a0f", border: "1px solid #1e1e2e", color: "#fff" }} />
            <div className="p-3 rounded-xl text-xs mb-4" style={{ background: "rgba(168,85,247,0.06)", color: "#c4b5fd", border: "1px solid rgba(168,85,247,0.15)" }}>
              Sur Telegram mobile : Parametres -&gt; Telegram Business -&gt; Chatbots -&gt; selectionne {showBusinessModal.botUsername}
            </div>
            <div className="flex gap-3">
              <button onClick={() => setShowBusinessModal(null)} className="flex-1 py-2.5 rounded-xl text-sm border" style={{ borderColor: "#1e1e2e", color: "#9ca3af" }}>Annuler</button>
              <button onClick={handleSetBusiness} className="flex-1 py-2.5 rounded-xl text-sm font-medium" style={{ background: "#e11d48", color: "#fff" }}>Sauvegarder</button>
            </div>
          </div>
        </div>
      )}

      {showNoLicenseModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center px-4"
          style={{ background: "rgba(0,0,0,0.8)" }} onClick={() => setShowNoLicenseModal(false)}>
          <div className="w-full max-w-sm rounded-2xl border p-6" style={{ background: "#111118", borderColor: "#1e1e2e" }}
            onClick={e => e.stopPropagation()}>
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0"
                style={{ background: "rgba(245,158,11,0.12)", border: "1px solid rgba(245,158,11,0.25)" }}>
                <Lock size={18} style={{ color: "#f59e0b" }} />
              </div>
              <div>
                <h2 className="font-bold">Aucune licence disponible</h2>
                <p className="text-xs" style={{ color: "#6b7280" }}>Pool vide et solde insuffisant</p>
              </div>
            </div>
            <p className="text-sm mb-5" style={{ color: "#9ca3af" }}>
              Tu n'as pas de licences Telegram dans ton pool et ton solde est inferieur a $30.
              Achete des licences dans la page Facturation pour pouvoir assigner un createur.
            </p>
            <div className="flex gap-3">
              <button onClick={() => setShowNoLicenseModal(false)} className="flex-1 py-2.5 rounded-xl text-sm border" style={{ borderColor: "#1e1e2e", color: "#9ca3af" }}>Annuler</button>
              <button onClick={() => { setShowNoLicenseModal(false); router.push("/dashboard/billing"); }}
                className="flex-1 py-2.5 rounded-xl text-sm font-medium flex items-center justify-center gap-2"
                style={{ background: "#e11d48", color: "#fff" }}>
                <ShoppingCart size={13} /> Aller a Facturation
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
