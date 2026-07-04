"use client";
import Link from "next/link";
import { usePathname, useParams, useRouter } from "next/navigation";
import { useState, useEffect } from "react";
import { ChevronLeft, RefreshCw, Eye, EyeOff, Lock, CheckCircle, ToggleLeft, ToggleRight } from "lucide-react";

interface Creator {
  id: string; name: string; botUsername: string; botToken: string;
  enableIA: boolean; syncStatus: string; businessConnection: string | null;
}

interface CreatorLicense {
  active: boolean; expiry: string | null; autoRenew: boolean;
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

const tabs = [
  { label: "Fans", href: "" },
  { label: "Medias", href: "/medias" },
  { label: "Scripts", href: "/scripts" },
  { label: "Schedules", href: "/schedules", soon: true },
  { label: "Settings", href: "/settings" },
  { label: "Re-engagements", href: "/reengagements" },
  { label: "Notifications", href: "/notifications" },
];

export default function CreatorLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const base = `/dashboard/creators/${params.id}`;

  const [creator, setCreator] = useState<Creator | null>(null);
  const [newToken, setNewToken] = useState("");
  const [showToken, setShowToken] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState("");

  // Licence
  const [licenseActive, setLicenseActive] = useState<boolean | null>(null); // null = loading
  const [license, setLicense] = useState<CreatorLicense | null>(null);
  const [balance, setBalance] = useState(0);
  const [pool, setPool] = useState(0);
  const [creatorName, setCreatorName] = useState("");
  const [licLoading, setLicLoading] = useState(false);
  const [licMsg, setLicMsg] = useState("");

  useEffect(() => {
    fetch("/api/creators").then(r => r.json()).then(d => {
      const found = d.creators?.find((c: Creator) => c.id === params.id) ?? null;
      setCreator(found);
      if (found) setCreatorName(found.name);
    });
    fetchBilling();
  }, [params.id]);

  const fetchBilling = async () => {
    try {
      const r = await fetch(`/api/billing?t=${Date.now()}`, { cache: "no-store" });
      if (!r.ok) return;
      const d = await r.json();
      const lic: CreatorLicense | undefined = d?.billing?.creatorLicenses?.[params.id];
      setLicense(lic ?? null);
      const active = !!(lic?.active && lic?.expiry && new Date(lic.expiry) > new Date());
      setLicenseActive(active);
      setBalance(d?.billing?.balance ?? 0);
      setPool(d?.billing?.telegramLicensePool ?? 0);
      const c = (d?.creators ?? []).find((x: { id: string; name: string }) => x.id === params.id);
      if (c) setCreatorName(c.name);
    } catch { setLicenseActive(false); }
  };

  const assignLicense = async () => {
    setLicLoading(true); setLicMsg("");
    const r = await fetch("/api/billing", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "buy-creator-license", creatorId: params.id, creatorName }),
    });
    const d = await r.json();
    if (d.ok) { setLicMsg("✅ Licence activée !"); await fetchBilling(); }
    else setLicMsg(`❌ ${d.error}`);
    setLicLoading(false);
  };

  const toggleAutoRenew = async () => {
    const newVal = !(license?.autoRenew ?? false);
    await fetch("/api/billing", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "toggle-autorenew", creatorId: params.id, autoRenew: newVal }),
    });
    fetchBilling();
  };

  const toggleIA = async (v: boolean) => {
    if (!creator) return;
    await fetch("/api/creators", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "toggle-ia", id: creator.id, value: v }),
    });
    setCreator(c => c ? { ...c, enableIA: v } : c);
  };

  const renewToken = async () => {
    if (!newToken.trim() || !creator) return;
    setSaving(true);
    const appUrl = window.location.origin;
    const res = await fetch("/api/creators", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "renew-token", id: creator.id, botToken: newToken.trim(), appUrl }),
    });
    const d = await res.json();
    setSaving(false);
    if (d.ok) { setSaveMsg("Token renouvelé et webhook reconnecté ✓"); setNewToken(""); }
    else setSaveMsg(d.error ?? "Erreur");
    setTimeout(() => setSaveMsg(""), 4000);
  };

  const daysLeft = (expiry: string | null) =>
    expiry ? Math.max(0, Math.ceil((new Date(expiry).getTime() - Date.now()) / 86400000)) : 0;

  const canBuy = pool > 0 || balance >= 30;

  // Chargement
  if (!creator || licenseActive === null) return (
    <div className="flex items-center justify-center h-40" style={{ color: "#4b5563" }}>
      <RefreshCw size={16} className="animate-spin mr-2" /> Chargement...
    </div>
  );

  // ── GATE LICENCE ──
  if (!licenseActive) {
    const isSuspended = !!(license && !license.active && license.expiry && new Date(license.expiry) > new Date());
    return (
      <div className="flex flex-col min-h-full" style={{ color: "#fff" }}>
        <div className="px-8 pt-6">
          <button onClick={() => router.push("/dashboard/creators")}
            className="flex items-center gap-1.5 text-sm mb-5 hover:text-white transition-all"
            style={{ color: "#6b7280" }}>
            <ChevronLeft size={15} /> Go back to creators
          </button>
          <div className="flex items-center gap-4 mb-8">
            <div className="w-14 h-14 rounded-full flex items-center justify-center text-2xl"
              style={{ background: "#1e1e2e", border: "2px solid #2a1a20" }}>🤖</div>
            <div>
              <h1 className="text-2xl font-bold">{creator.name}</h1>
              <p className="text-sm" style={{ color: "#6b7280" }}>{creator.botUsername}</p>
            </div>
          </div>
        </div>

        {/* Écran de blocage */}
        <div className="flex-1 flex items-center justify-center px-8">
          <div className="max-w-md w-full rounded-2xl border p-8 text-center"
            style={{ background: "#111118", borderColor: "#1e1e2e" }}>
            <div className="w-16 h-16 rounded-full flex items-center justify-center mx-auto mb-5"
              style={{ background: "rgba(225,29,72,0.1)", border: "2px solid rgba(225,29,72,0.3)" }}>
              <Lock size={28} style={{ color: "#e11d48" }} />
            </div>

            <h2 className="text-xl font-bold mb-2">Licence requise</h2>
            <p className="text-sm mb-6" style={{ color: "#6b7280" }}>
              {isSuspended
                ? `La licence de ${creator.name} est suspendue. Réactivez-la pour accéder au tableau de bord.`
                : `Activez une licence Telegram pour accéder au tableau de bord de ${creator.name} et utiliser le bot IA.`}
            </p>

            {/* Infos licence si suspendue */}
            {isSuspended && license?.expiry && (
              <div className="mb-5 p-3 rounded-xl text-sm"
                style={{ background: "rgba(245,158,11,0.1)", border: "1px solid rgba(245,158,11,0.2)", color: "#f59e0b" }}>
                ⏸ Suspendue · {daysLeft(license.expiry)}j restants — vous pouvez la réactiver gratuitement
              </div>
            )}

            {/* Solde & pool */}
            <div className="flex justify-between text-sm mb-5 p-3 rounded-xl"
              style={{ background: "#0d0d14", border: "1px solid #1e1e2e" }}>
              <span style={{ color: "#6b7280" }}>Solde disponible</span>
              <span className="font-bold" style={{ color: "#10b981" }}>${balance.toFixed(2)}</span>
            </div>
            {pool > 0 && (
              <div className="mb-4 text-xs" style={{ color: "#6b7280" }}>
                🎟 {pool} licence{pool > 1 ? "s" : ""} disponible{pool > 1 ? "s" : ""} dans le pool
              </div>
            )}

            {licMsg && (
              <div className="mb-4 text-sm" style={{ color: licMsg.startsWith("✅") ? "#10b981" : "#ef4444" }}>
                {licMsg}
              </div>
            )}

            {/* Bouton principal */}
            {isSuspended ? (
              <button onClick={async () => {
                setLicLoading(true); setLicMsg("");
                const r = await fetch("/api/billing", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ action: "reactivate-license", creatorId: params.id }) });
                const d = await r.json();
                if (d.ok) { setLicMsg("✅ Licence réactivée !"); await fetchBilling(); }
                else setLicMsg(`❌ ${d.error}`);
                setLicLoading(false);
              }} disabled={licLoading}
                className="w-full py-3 rounded-xl text-sm font-bold mb-3"
                style={{ background: "#10b981", color: "#fff" }}>
                {licLoading ? "..." : "▶ Réactiver la licence"}
              </button>
            ) : (
              <button onClick={assignLicense} disabled={licLoading || !canBuy}
                className="w-full py-3 rounded-xl text-sm font-bold mb-3"
                style={{
                  background: canBuy ? "#e11d48" : "rgba(75,85,99,0.3)",
                  color: canBuy ? "#fff" : "#6b7280",
                  cursor: canBuy ? "pointer" : "not-allowed",
                }}>
                {licLoading ? "..." : pool > 0 ? `Activer depuis le pool (${pool} dispo)` : canBuy ? "Activer — $30" : "Solde insuffisant"}
              </button>
            )}

            {/* Auto-renouvellement */}
            {license && (
              <div className="flex items-center justify-between mt-3 pt-3 border-t"
                style={{ borderColor: "#1e1e2e" }}>
                <span className="text-xs" style={{ color: "#6b7280" }}>Renouvellement automatique</span>
                <button onClick={toggleAutoRenew} style={{ color: license.autoRenew ? "#10b981" : "#4b5563" }}>
                  {license.autoRenew ? <ToggleRight size={22} /> : <ToggleLeft size={22} />}
                </button>
              </div>
            )}

            <div className="mt-4">
              <a href="/dashboard/billing" className="text-xs underline" style={{ color: "#6b7280" }}>
                Gérer les licences dans Facturation
              </a>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // ── LAYOUT NORMAL (licence active) ──
  return (
    <div className="flex flex-col min-h-full" style={{ color: "#fff" }}>
      <div className="px-8 pt-6">
        <button onClick={() => router.push("/dashboard/creators")}
          className="flex items-center gap-1.5 text-sm mb-5 hover:text-white transition-all"
          style={{ color: "#6b7280" }}>
          <ChevronLeft size={15} /> Go back to creators
        </button>

        {/* Creator header */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-4">
            <div className="w-14 h-14 rounded-full flex items-center justify-center text-2xl"
              style={{ background: "#1e1e2e", border: "2px solid #2a1a20" }}>🤖</div>
            <div>
              <h1 className="text-2xl font-bold">{creator.name}</h1>
              <p className="text-sm" style={{ color: "#6b7280" }}>{creator.botUsername}</p>
            </div>
          </div>
          <div className="flex items-center gap-4">
            {/* Badge licence */}
            <div className="flex items-center gap-1.5 text-xs px-3 py-1 rounded-full"
              style={{ background: "rgba(16,185,129,0.1)", color: "#10b981", border: "1px solid rgba(16,185,129,0.2)" }}>
              <CheckCircle size={12} /> Licence active · {daysLeft(license?.expiry ?? null)}j
            </div>
            <span className="text-sm" style={{ color: "#9ca3af" }}>Enable IA</span>
            <Toggle value={creator.enableIA} onChange={toggleIA} />
          </div>
        </div>

        {/* Renew token card */}
        <div className="rounded-xl border p-5 mb-6" style={{ borderColor: "#1e1e2e", background: "#0f0f1a" }}>
          <h3 className="font-semibold text-sm mb-1">Renew bot token</h3>
          <p className="text-xs mb-4" style={{ color: "#6b7280" }}>
            If you ever need to rotate your Telegram token, open{" "}
            <a href="https://t.me/BotFather" target="_blank" rel="noopener"
              className="underline" style={{ color: "#93c5fd" }}>BotFather</a>
            , select your bot → <strong>API Token</strong> → <strong>Revoke current token</strong>, then paste the new token below.
          </p>
          <p className="text-xs mb-2 font-medium" style={{ color: "#9ca3af" }}>New bot token</p>
          <div className="flex gap-3">
            <div className="relative flex-1">
              <input value={newToken} onChange={e => setNewToken(e.target.value)}
                type={showToken ? "text" : "password"}
                placeholder="123456789:AAH..."
                className="w-full px-4 py-2.5 rounded-lg text-sm outline-none pr-10 font-mono"
                style={{ background: "#0a0a0f", border: "1px solid #1e1e2e", color: "#d1d5db" }} />
              <button onClick={() => setShowToken(s => !s)}
                className="absolute right-3 top-1/2 -translate-y-1/2" style={{ color: "#4b5563" }}>
                {showToken ? <EyeOff size={14} /> : <Eye size={14} />}
              </button>
            </div>
            <button onClick={renewToken} disabled={saving || !newToken.trim()}
              className="flex items-center gap-2 px-5 py-2.5 rounded-lg text-sm font-medium disabled:opacity-50"
              style={{ background: "#e11d48", color: "#fff" }}>
              {saving ? <RefreshCw size={12} className="animate-spin" /> : null}
              Save new token &amp; reconnect webhook
            </button>
          </div>
          {saveMsg && <p className="mt-2 text-xs" style={{ color: saveMsg.includes("✓") ? "#10b981" : "#f87171" }}>{saveMsg}</p>}
        </div>
      </div>

      {/* Tab bar */}
      <div className="flex items-center gap-1 px-8 pb-0 border-b" style={{ borderColor: "#1e1e2e" }}>
        {tabs.map(t => {
          const href = `${base}${t.href}`;
          const active = t.href === "" ? pathname === base : pathname.startsWith(href);
          return (
            <Link key={t.label} href={t.soon ? "#" : href}
              className="flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium border-b-2 transition-all -mb-px"
              style={{
                borderColor: active ? "#e11d48" : "transparent",
                color: active ? "#fff" : t.soon ? "#4b5563" : "#9ca3af",
                cursor: t.soon ? "not-allowed" : "pointer",
              }}>
              {t.label}
              {t.soon && <span className="text-xs px-1.5 py-0.5 rounded" style={{ background: "#1e1e2e", color: "#6b7280" }}>Soon</span>}
            </Link>
          );
        })}
      </div>

      <div className="flex-1">{children}</div>
    </div>
  );
}
