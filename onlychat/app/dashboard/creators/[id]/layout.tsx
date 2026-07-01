"use client";
import Link from "next/link";
import { usePathname, useParams, useRouter } from "next/navigation";
import { useState, useEffect } from "react";
import { ChevronLeft, RefreshCw, Eye, EyeOff } from "lucide-react";

interface Creator {
  id: string; name: string; botUsername: string; botToken: string;
  enableIA: boolean; syncStatus: string; businessConnection: string | null;
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

  useEffect(() => {
    fetch("/api/creators").then(r => r.json()).then(d => {
      const found = d.creators?.find((c: Creator) => c.id === params.id) ?? null;
      setCreator(found);
    });
  }, [params.id]);

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
    // Met à jour le token via une action dédiée
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

  if (!creator) return (
    <div className="flex items-center justify-center h-40" style={{ color: "#4b5563" }}>
      <RefreshCw size={16} className="animate-spin mr-2" /> Chargement...
    </div>
  );

  return (
    <div className="flex flex-col min-h-full" style={{ color: "#fff" }}>
      {/* Back link */}
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
              style={{ background: "#1e1e2e", border: "2px solid #2a1a20" }}>
              🤖
            </div>
            <div>
              <h1 className="text-2xl font-bold">{creator.name}</h1>
              <p className="text-sm" style={{ color: "#6b7280" }}>{creator.botUsername}</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
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
