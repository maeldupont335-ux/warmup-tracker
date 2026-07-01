"use client";
import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import {
  Plus, Trash2, RefreshCw, Search, CheckCircle,
  AlertCircle, ChevronLeft, ChevronRight, Zap
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

function Toggle({ value, onChange }: { value: boolean; onChange: (v: boolean) => void }) {
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
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [showLicenseModal, setShowLicenseModal] = useState<Creator | null>(null);
  const [showBusinessModal, setShowBusinessModal] = useState<Creator | null>(null);
  const [businessInput, setBusinessInput] = useState("");
  const [webhookLoading, setWebhookLoading] = useState<string | null>(null);
  const [webhookError, setWebhookError] = useState<Record<string, string>>({});

  // Formulaire nouveau créateur
  const [newName, setNewName] = useState("");
  const [newToken, setNewToken] = useState("");
  const [adding, setAdding] = useState(false);
  const [addError, setAddError] = useState("");

  const appUrl = typeof window !== "undefined" ? window.location.origin : "";

  const fetch_ = async () => {
    setLoading(true);
    const res = await fetch("/api/creators");
    const d = await res.json();
    setCreators(d.creators ?? []);
    setLoading(false);
  };

  useEffect(() => { fetch_(); }, []);

  const action = async (id: string, actionName: string, extra?: Record<string, unknown>) => {
    await fetch("/api/creators", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: actionName, id, appUrl, ...extra }),
    });
    fetch_();
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
    if (!confirm("Supprimer ce créateur ?")) return;
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
      } else {
        fetch_();
      }
    } catch (err) {
      setWebhookError(e => ({ ...e, [id]: String(err) }));
    }
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
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold mb-1">Creators</h1>
        <p className="text-sm" style={{ color: "#9ca3af" }}>Manage and monitor all your creators (OnlyFans and Telegram)</p>
      </div>

      {/* Tabs */}
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
          <p className="text-sm">Intégration OnlyFans — bientôt disponible</p>
        </div>
      )}

      {tab === "telegram" && (
        <>
          {/* Section header */}
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

          {/* Search + Status */}
          <div className="flex items-center gap-3 mb-5">
            <div className="relative flex-1 max-w-sm">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: "#6b7280" }} />
              <input
                value={search} onChange={e => setSearch(e.target.value)}
                placeholder="Search creators by name or username..."
                className="w-full pl-9 pr-4 py-2.5 rounded-lg text-sm outline-none"
                style={{ background: "#111118", border: "1px solid #1e1e2e", color: "#d1d5db" }}
              />
            </div>
            <button onClick={fetch_} className="flex items-center gap-2 px-3 py-2.5 rounded-lg text-sm border transition-all hover:bg-white/5"
              style={{ borderColor: "#1e1e2e", color: "#6b7280" }}>
              <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
              Status
            </button>
          </div>

          {/* Table */}
          <div className="rounded-xl border overflow-hidden" style={{ borderColor: "#1e1e2e" }}>
            <table className="w-full text-sm">
              <thead>
                <tr style={{ background: "#0d0d14", borderBottom: "1px solid #1e1e2e" }}>
                  {["Name", "Bot username", "Business Connection", "License", "Sync Status", "Created at ↕", "Auto Renew", "Enable IA", "", ""].map(h => (
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
                    Aucun créateur — clique &quot;Add a creator&quot; pour commencer
                  </td></tr>
                ) : filtered.map((c, i) => (
                  <tr key={c.id}
                    onClick={() => router.push(`/dashboard/creators/${c.id}`)}
                    style={{ borderBottom: i < filtered.length - 1 ? "1px solid #1a1a28" : "none", background: "#0f0f1a", cursor: "pointer" }}
                    className="hover:bg-white/[0.02] transition-colors">
                    {/* Name */}
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <div className="w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0"
                          style={{ background: "#1e1e2e", color: "#e11d48", border: "1px solid #2a1a20" }}>
                          <span style={{ fontSize: 16 }}>👤</span>
                        </div>
                        <span className="font-medium">{c.name}</span>
                      </div>
                    </td>

                    {/* Bot username */}
                    <td className="px-4 py-3" style={{ color: "#9ca3af" }}>{c.botUsername}</td>

                    {/* Business Connection */}
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

                    {/* License */}
                    <td className="px-4 py-3">
                      {c.license === "none" ? (
                        <span className="text-xs" style={{ color: "#6b7280" }}>No telegram license</span>
                      ) : (
                        <span className="px-2.5 py-1 rounded-lg text-xs font-medium"
                          style={{ background: "#1e1e2e", color: "#d1d5db", border: "1px solid #2a2a3e" }}>
                          {c.license === "telegram" ? "Telegram" : "OnlyFans"}
                        </span>
                      )}
                    </td>

                    {/* Sync Status */}
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

                    {/* Created at */}
                    <td className="px-4 py-3 text-xs" style={{ color: "#6b7280", whiteSpace: "nowrap" }}>
                      {formatDate(c.createdAt)}
                    </td>

                    {/* Auto Renew */}
                    <td className="px-4 py-3" onClick={e => e.stopPropagation()}>
                      {c.license === "none"
                        ? <span style={{ color: "#4b5563" }}>—</span>
                        : <Toggle value={c.autoRenew} onChange={v => action(c.id, "toggle-renew", { value: v })} />}
                    </td>

                    {/* Enable IA */}
                    <td className="px-4 py-3" onClick={e => e.stopPropagation()}>
                      <Toggle value={c.enableIA} onChange={v => action(c.id, "toggle-ia", { value: v })} />
                    </td>

                    {/* Delete */}
                    <td className="px-4 py-3" onClick={e => e.stopPropagation()}>
                      <button onClick={() => handleDelete(c.id)}
                        className="p-1.5 rounded-lg transition-all hover:bg-red-500/10"
                        style={{ color: "#e11d48", border: "1px solid rgba(225,29,72,0.2)" }}>
                        <Trash2 size={13} />
                      </button>
                    </td>

                    {/* Webhook / License */}
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
                      ) : c.license === "none" ? (
                        <button onClick={() => setShowLicenseModal(c)}
                          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all hover:opacity-90"
                          style={{ background: "#e11d48", color: "#fff" }}>
                          Assign License
                        </button>
                      ) : (
                        <div className="flex items-center gap-1 text-xs" style={{ color: "#10b981" }}>
                          <CheckCircle size={12} /> Actif
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          <div className="flex items-center justify-end gap-3 mt-4 text-sm" style={{ color: "#6b7280" }}>
            <span>Rows per page</span>
            <select className="px-2 py-1 rounded text-xs outline-none" style={{ background: "#111118", border: "1px solid #1e1e2e", color: "#d1d5db" }}>
              <option>10</option>
            </select>
            <span>Page 1 of 1</span>
            <div className="flex gap-1">
              {[ChevronLeft, ChevronLeft, ChevronRight, ChevronRight].map((Icon, i) => (
                <button key={i} className="p-1 rounded hover:bg-white/5"><Icon size={14} /></button>
              ))}
            </div>
          </div>
        </>
      )}

      {/* Modal — Ajouter créateur */}
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center px-4"
          style={{ background: "rgba(0,0,0,0.8)" }} onClick={() => setShowModal(false)}>
          <div className="w-full max-w-md rounded-2xl border p-6" style={{ background: "#111118", borderColor: "#1e1e2e" }}
            onClick={e => e.stopPropagation()}>
            <h2 className="font-black text-lg mb-1">Add a creator</h2>
            <p className="text-sm mb-5" style={{ color: "#6b7280" }}>Crée un bot sur @BotFather et colle le token ici</p>

            <div className="space-y-4">
              <div>
                <label className="block text-xs mb-1.5" style={{ color: "#6b7280" }}>Nom de la créatrice</label>
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
                📌 Telegram → @BotFather → /newbot → copie le token
              </div>

              {addError && (
                <div className="flex items-center gap-2 p-3 rounded-xl text-sm"
                  style={{ background: "rgba(239,68,68,0.08)", color: "#fca5a5", border: "1px solid rgba(239,68,68,0.2)" }}>
                  <AlertCircle size={13} />{addError}
                </div>
              )}

              <div className="flex gap-3">
                <button onClick={() => setShowModal(false)}
                  className="flex-1 py-2.5 rounded-xl text-sm border"
                  style={{ borderColor: "#1e1e2e", color: "#9ca3af" }}>
                  Annuler
                </button>
                <button onClick={handleAdd} disabled={adding || !newName || !newToken}
                  className="flex-1 py-2.5 rounded-xl text-sm font-medium disabled:opacity-40 flex items-center justify-center gap-2"
                  style={{ background: "#e11d48", color: "#fff" }}>
                  {adding ? <RefreshCw size={13} className="animate-spin" /> : <Plus size={13} />}
                  {adding ? "Vérification..." : "Add creator"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Modal — Business Connection */}
      {showBusinessModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center px-4"
          style={{ background: "rgba(0,0,0,0.8)" }} onClick={() => setShowBusinessModal(null)}>
          <div className="w-full max-w-sm rounded-2xl border p-6" style={{ background: "#111118", borderColor: "#1e1e2e" }}
            onClick={e => e.stopPropagation()}>
            <h2 className="font-bold mb-1">Business Connection</h2>
            <p className="text-sm mb-4" style={{ color: "#6b7280" }}>@username du compte Telegram Business connecté</p>
            <input value={businessInput} onChange={e => setBusinessInput(e.target.value)} placeholder="@paupauxx"
              className="w-full px-4 py-2.5 rounded-xl text-sm outline-none mb-4"
              style={{ background: "#0a0a0f", border: "1px solid #1e1e2e", color: "#fff" }} />
            <div className="p-3 rounded-xl text-xs mb-4" style={{ background: "rgba(168,85,247,0.06)", color: "#c4b5fd", border: "1px solid rgba(168,85,247,0.15)" }}>
              Sur Telegram mobile : Paramètres → Telegram Business → Chatbots → sélectionne <strong>{showBusinessModal.botUsername}</strong>
            </div>
            <div className="flex gap-3">
              <button onClick={() => setShowBusinessModal(null)} className="flex-1 py-2.5 rounded-xl text-sm border" style={{ borderColor: "#1e1e2e", color: "#9ca3af" }}>Annuler</button>
              <button onClick={handleSetBusiness} className="flex-1 py-2.5 rounded-xl text-sm font-medium" style={{ background: "#e11d48", color: "#fff" }}>Sauvegarder</button>
            </div>
          </div>
        </div>
      )}

      {/* Modal — License */}
      {showLicenseModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center px-4"
          style={{ background: "rgba(0,0,0,0.8)" }} onClick={() => setShowLicenseModal(null)}>
          <div className="w-full max-w-sm rounded-2xl border p-6" style={{ background: "#111118", borderColor: "#1e1e2e" }}
            onClick={e => e.stopPropagation()}>
            <h2 className="font-bold mb-4">Assign License — {showLicenseModal.name}</h2>
            <div className="space-y-2 mb-4">
              {(["telegram", "onlyfans"] as const).map(l => (
                <button key={l} onClick={async () => { await action(showLicenseModal.id, "assign-license", { license: l }); setShowLicenseModal(null); }}
                  className="w-full py-3 rounded-xl text-sm font-medium text-left px-4 border transition-all hover:border-red-500/40"
                  style={{ background: "#0a0a0f", borderColor: "#1e1e2e", color: "#d1d5db" }}>
                  {l === "telegram" ? "🤖 Telegram" : "💎 OnlyFans"}
                </button>
              ))}
            </div>
            <button onClick={() => setShowLicenseModal(null)} className="w-full py-2.5 rounded-xl text-sm border" style={{ borderColor: "#1e1e2e", color: "#9ca3af" }}>Annuler</button>
          </div>
        </div>
      )}
    </div>
  );
}
