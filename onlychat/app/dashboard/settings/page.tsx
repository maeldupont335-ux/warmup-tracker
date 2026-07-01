"use client";
import { useState, useEffect, useCallback } from "react";
import { Save, Zap, Clock, MessageCircle, Bell, DollarSign, Eye, Send, RefreshCw } from "lucide-react";

const personalities = [
  { value: "sweet", label: "Douce & affectueuse", desc: "Ton doux, câlin, beaucoup d'émojis 💕", emoji: "🥰" },
  { value: "flirty", label: "Coquine & directe", desc: "Ton flirteur, taquin, provocateur 🔥", emoji: "😈" },
  { value: "girlfriend", label: "GFE (Girlfriend Exp.)", desc: "Comme une vraie copine, intime 💋", emoji: "💋" },
  { value: "custom", label: "Personnalisée", desc: "Tu définis le ton toi-même", emoji: "✏️" },
];

const languages = ["Français", "English", "Español", "Deutsch", "Português", "Italiano", "日本語", "العربية"];

interface Settings {
  personality: string;
  customPrompt: string;
  languages: string[];
  ppvEnabled: boolean;
  ppvPrice: string;
  nudgeDelay: string;
  welcomeEnabled: boolean;
  creatorName: string;
}

export default function SettingsPage() {
  const [settings, setSettings] = useState<Settings>({
    personality: "flirty",
    customPrompt: "",
    languages: ["Français", "English"],
    ppvEnabled: true,
    ppvPrice: "15",
    nudgeDelay: "48",
    welcomeEnabled: true,
    creatorName: "",
  });

  const [generatedPrompt, setGeneratedPrompt] = useState("");
  const [showPrompt, setShowPrompt] = useState(false);
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);

  // App URL
  const [appUrl, setAppUrl] = useState("");
  const [appUrlSaved, setAppUrlSaved] = useState(false);
  const [appUrlSaving, setAppUrlSaving] = useState(false);

  useEffect(() => {
    fetch("/api/app-config").then(r => r.json()).then(d => {
      setAppUrl(d.productionUrl ?? "");
    });
  }, []);

  const saveAppUrl = async () => {
    setAppUrlSaving(true);
    await fetch("/api/app-config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ productionUrl: appUrl }),
    });
    setAppUrlSaving(false);
    setAppUrlSaved(true);
    setTimeout(() => setAppUrlSaved(false), 2500);
  };

  // Test chat
  const [testMsg, setTestMsg] = useState("");
  const [testReply, setTestReply] = useState("");
  const [testLoading, setTestLoading] = useState(false);

  const fetchSettings = useCallback(async () => {
    try {
      const res = await fetch("/api/settings");
      const data = await res.json();
      setSettings(data.settings);
      setGeneratedPrompt(data.prompt);
    } catch {
      // ignore, use defaults
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchSettings(); }, [fetchSettings]);

  const updateSettings = (patch: Partial<Settings>) => {
    const next = { ...settings, ...patch };
    setSettings(next);
    // Rebuild prompt preview via API
    fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(next),
    }).then(r => r.json()).then(d => {
      if (d.prompt) setGeneratedPrompt(d.prompt);
    });
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const res = await fetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(settings),
      });
      const data = await res.json();
      if (data.prompt) setGeneratedPrompt(data.prompt);
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async () => {
    if (!testMsg.trim()) return;
    setTestLoading(true);
    setTestReply("");
    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: testMsg }),
      });
      const data = await res.json();
      setTestReply(data.reply || data.error || "Erreur");
    } finally {
      setTestLoading(false);
    }
  };

  const toggleLang = (l: string) => {
    const next = settings.languages.includes(l)
      ? settings.languages.filter(x => x !== l)
      : [...settings.languages, l];
    updateSettings({ languages: next });
  };

  if (loading) {
    return (
      <div className="p-8 flex items-center justify-center h-64">
        <RefreshCw size={20} className="animate-spin" style={{ color: "#a855f7" }} />
      </div>
    );
  }

  return (
    <div className="p-8" style={{ color: "#fff" }}>
      {/* App URL — bloc en haut */}
      <div className="rounded-xl border p-5 mb-8" style={{ borderColor: "#1e1e2e", background: "#0f0f1a" }}>
        <h2 className="font-semibold text-sm mb-1 flex items-center gap-2">
          🌐 URL de production (Render)
        </h2>
        <p className="text-xs mb-3" style={{ color: "#6b7280" }}>
          Colle l&apos;URL de ton app Render ici — utilisée pour le webhook Telegram. A saisir une seule fois.
        </p>
        <div className="flex gap-3">
          <input
            value={appUrl}
            onChange={e => setAppUrl(e.target.value)}
            placeholder="https://onlychat-ai.onrender.com"
            className="flex-1 px-4 py-2.5 rounded-xl text-sm outline-none font-mono"
            style={{ background: "#0a0a0f", border: "1px solid #1e1e2e", color: "#d1d5db" }}
          />
          <button onClick={saveAppUrl} disabled={appUrlSaving}
            className="flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-medium disabled:opacity-50"
            style={{ background: appUrlSaved ? "#10b981" : "#e11d48", color: "#fff" }}>
            {appUrlSaving ? <RefreshCw size={13} className="animate-spin" /> : null}
            {appUrlSaved ? "Sauvegardé ✓" : "Sauvegarder"}
          </button>
        </div>
      </div>

      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-black">Paramètres IA</h1>
          <p className="text-sm mt-1" style={{ color: "#6b7280" }}>Chaque modification reconstruit le prompt automatiquement</p>
        </div>
        <div className="flex items-center gap-3">
          <button onClick={() => setShowPrompt(!showPrompt)}
            className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm border transition-all hover:bg-white/5"
            style={{ borderColor: "#1e1e2e", color: "#9ca3af" }}>
            <Eye size={14} />
            {showPrompt ? "Masquer" : "Voir"} le prompt
          </button>
          <button onClick={handleSave} disabled={saving}
            className="flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-medium transition-all hover:opacity-90 disabled:opacity-60"
            style={{ background: saved ? "rgba(16,185,129,0.2)" : "linear-gradient(135deg,#a855f7,#7c3aed)", color: saved ? "#10b981" : "#fff" }}>
            <Save size={14} />
            {saved ? "Sauvegardé ✓" : saving ? "..." : "Sauvegarder"}
          </button>
        </div>
      </div>

      {/* Prompt Preview */}
      {showPrompt && (
        <div className="mb-6 rounded-2xl border p-5" style={{ background: "#0a0a0f", borderColor: "#a855f7" }}>
          <div className="flex items-center gap-2 mb-3 text-xs font-bold" style={{ color: "#a855f7" }}>
            <Zap size={12} />
            PROMPT GÉNÉRÉ — envoyé à Claude à chaque message
          </div>
          <pre className="text-xs leading-relaxed whitespace-pre-wrap" style={{ color: "#9ca3af", fontFamily: "monospace" }}>
            {generatedPrompt || "Sauvegarde les settings pour générer le prompt..."}
          </pre>
        </div>
      )}

      <div className="grid grid-cols-2 gap-6">
        {/* Nom créateur */}
        <div className="col-span-2 rounded-2xl border p-6" style={{ background: "#111118", borderColor: "#1e1e2e" }}>
          <div className="flex items-center gap-2 mb-4">
            <MessageCircle size={16} style={{ color: "#a855f7" }} />
            <h2 className="font-bold">Identité du créateur</h2>
          </div>
          <div>
            <label className="block text-xs mb-2" style={{ color: "#6b7280" }}>Prénom / pseudo de la créatrice (utilisé dans le prompt)</label>
            <input
              type="text"
              value={settings.creatorName}
              onChange={e => updateSettings({ creatorName: e.target.value })}
              placeholder="Ex: Alexya, Luna, Jade..."
              className="w-full max-w-sm px-4 py-3 rounded-xl text-sm outline-none"
              style={{ background: "#0a0a0f", border: "1px solid #1e1e2e", color: "#fff" }}
            />
          </div>
        </div>

        {/* Personnalité */}
        <div className="rounded-2xl border p-6" style={{ background: "#111118", borderColor: "#1e1e2e" }}>
          <div className="flex items-center gap-2 mb-4">
            <MessageCircle size={16} style={{ color: "#a855f7" }} />
            <h2 className="font-bold">Personnalité de l&apos;IA</h2>
          </div>
          <div className="space-y-2 mb-4">
            {personalities.map((p) => (
              <button key={p.value} onClick={() => updateSettings({ personality: p.value })}
                className="w-full text-left p-3 rounded-xl border transition-all"
                style={{
                  background: settings.personality === p.value ? "rgba(168,85,247,0.08)" : "transparent",
                  borderColor: settings.personality === p.value ? "#a855f7" : "#1e1e2e",
                }}>
                <div className="flex items-center gap-2">
                  <span>{p.emoji}</span>
                  <div>
                    <div className="text-sm font-medium" style={{ color: settings.personality === p.value ? "#a855f7" : "#d1d5db" }}>{p.label}</div>
                    <div className="text-xs" style={{ color: "#6b7280" }}>{p.desc}</div>
                  </div>
                </div>
              </button>
            ))}
          </div>
          {settings.personality === "custom" && (
            <div>
              <label className="block text-xs mb-2" style={{ color: "#6b7280" }}>Prompt personnalisé</label>
              <textarea
                value={settings.customPrompt}
                onChange={e => updateSettings({ customPrompt: e.target.value })}
                placeholder="Ex: Tu es Luna, 22 ans, étudiante en mode à Paris. Tu parles de façon décontractée avec des abréviations (tfk, mdr, jsp...). Tu es curieuse des goûts de tes fans..."
                rows={6}
                className="w-full px-4 py-3 rounded-xl text-sm outline-none resize-none"
                style={{ background: "#0a0a0f", border: "1px solid #1e1e2e", color: "#d1d5db" }}
              />
              <div className="text-xs mt-1" style={{ color: "#4b5563" }}>
                {settings.customPrompt.length} caractères — plus c&apos;est précis, mieux l&apos;IA performe
              </div>
            </div>
          )}
        </div>

        {/* Langues + Horaires */}
        <div className="space-y-6">
          <div className="rounded-2xl border p-6" style={{ background: "#111118", borderColor: "#1e1e2e" }}>
            <div className="flex items-center gap-2 mb-4">
              <Clock size={16} style={{ color: "#a855f7" }} />
              <h2 className="font-bold">Horaires</h2>
            </div>
            <label className="flex items-center gap-3 cursor-pointer">
              <div className={`w-10 h-5 rounded-full relative transition-all ${true ? "bg-purple-500" : "bg-gray-700"}`}>
                <div className="absolute top-0.5 left-5 w-4 h-4 rounded-full bg-white" />
              </div>
              <span className="text-sm">Actif 24h/24 (recommandé)</span>
            </label>
          </div>

          <div className="rounded-2xl border p-6" style={{ background: "#111118", borderColor: "#1e1e2e" }}>
            <div className="flex items-center gap-2 mb-4">
              <Zap size={16} style={{ color: "#a855f7" }} />
              <h2 className="font-bold">Langues</h2>
            </div>
            <p className="text-xs mb-3" style={{ color: "#6b7280" }}>L&apos;IA détecte et répond dans la langue du fan</p>
            <div className="flex flex-wrap gap-2">
              {languages.map(l => (
                <button key={l} onClick={() => toggleLang(l)}
                  className="px-3 py-1.5 rounded-lg text-xs font-medium transition-all"
                  style={{
                    background: settings.languages.includes(l) ? "rgba(168,85,247,0.15)" : "#0a0a0f",
                    border: `1px solid ${settings.languages.includes(l) ? "#a855f7" : "#1e1e2e"}`,
                    color: settings.languages.includes(l) ? "#a855f7" : "#6b7280",
                  }}>
                  {l}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* PPV */}
        <div className="rounded-2xl border p-6" style={{ background: "#111118", borderColor: "#1e1e2e" }}>
          <div className="flex items-center gap-2 mb-4">
            <DollarSign size={16} style={{ color: "#a855f7" }} />
            <h2 className="font-bold">Vente PPV automatique</h2>
          </div>
          <label className="flex items-center gap-3 mb-4 cursor-pointer">
            <div className={`w-10 h-5 rounded-full relative transition-all ${settings.ppvEnabled ? "bg-purple-500" : "bg-gray-700"}`}
              onClick={() => updateSettings({ ppvEnabled: !settings.ppvEnabled })}>
              <div className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-all ${settings.ppvEnabled ? "left-5" : "left-0.5"}`} />
            </div>
            <span className="text-sm">L&apos;IA propose le PPV dans la conversation</span>
          </label>
          {settings.ppvEnabled && (
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs mb-1" style={{ color: "#6b7280" }}>Prix par défaut ($)</label>
                <input type="number" value={settings.ppvPrice}
                  onChange={e => updateSettings({ ppvPrice: e.target.value })}
                  className="w-full px-3 py-2 rounded-lg text-sm outline-none"
                  style={{ background: "#0a0a0f", border: "1px solid #1e1e2e", color: "#fff" }} />
              </div>
              <div>
                <label className="block text-xs mb-1" style={{ color: "#6b7280" }}>Délai relance (h)</label>
                <input type="number" value={settings.nudgeDelay}
                  onChange={e => updateSettings({ nudgeDelay: e.target.value })}
                  className="w-full px-3 py-2 rounded-lg text-sm outline-none"
                  style={{ background: "#0a0a0f", border: "1px solid #1e1e2e", color: "#fff" }} />
              </div>
            </div>
          )}
          <div className="mt-4">
            <label className="flex items-center gap-3 cursor-pointer">
              <div className={`w-10 h-5 rounded-full relative transition-all ${settings.welcomeEnabled ? "bg-purple-500" : "bg-gray-700"}`}
                onClick={() => updateSettings({ welcomeEnabled: !settings.welcomeEnabled })}>
                <div className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-all ${settings.welcomeEnabled ? "left-5" : "left-0.5"}`} />
              </div>
              <span className="text-sm">Message de bienvenue automatique</span>
            </label>
          </div>
        </div>

        {/* Telegram */}
        <div className="rounded-2xl border p-6" style={{ background: "#111118", borderColor: "#1e1e2e" }}>
          <div className="flex items-center gap-2 mb-4">
            <Bell size={16} style={{ color: "#a855f7" }} />
            <h2 className="font-bold">Alertes Telegram</h2>
          </div>
          <div className="space-y-3">
            <div className="text-xs p-3 rounded-lg" style={{ background: "rgba(168,85,247,0.06)", color: "#a855f7", border: "1px solid rgba(168,85,247,0.15)" }}>
              Webhook actif sur : <code className="font-mono">/api/telegram/webhook</code>
            </div>
            <div className="text-xs p-3 rounded-lg" style={{ background: "rgba(59,130,246,0.06)", color: "#60a5fa", border: "1px solid rgba(59,130,246,0.15)" }}>
              💡 Configure <code>TELEGRAM_BOT_TOKEN</code> dans le fichier <code>.env.local</code>, puis enregistre le webhook avec :<br />
              <code className="block mt-1 font-mono">https://api.telegram.org/bot&lt;TOKEN&gt;/setWebhook?url=https://ton-site.com/api/telegram/webhook</code>
            </div>
          </div>
        </div>

        {/* Test Chat */}
        <div className="col-span-2 rounded-2xl border p-6" style={{ background: "#111118", borderColor: "#1e1e2e" }}>
          <div className="flex items-center gap-2 mb-4">
            <Send size={16} style={{ color: "#a855f7" }} />
            <h2 className="font-bold">Tester l&apos;IA en direct</h2>
            <span className="text-xs px-2 py-0.5 rounded-full" style={{ background: "rgba(16,185,129,0.1)", color: "#10b981" }}>Live</span>
          </div>
          <div className="flex gap-3 mb-3">
            <input
              type="text" value={testMsg} onChange={e => setTestMsg(e.target.value)}
              onKeyDown={e => e.key === "Enter" && handleTest()}
              placeholder="Envoie un message comme un fan... Ex: 'salut t'es là?' ou 'tu as des contenu spéciaux ?'"
              className="flex-1 px-4 py-3 rounded-xl text-sm outline-none"
              style={{ background: "#0a0a0f", border: "1px solid #1e1e2e", color: "#fff" }}
            />
            <button onClick={handleTest} disabled={testLoading || !testMsg.trim()}
              className="px-5 py-3 rounded-xl text-sm font-medium transition-all hover:opacity-90 disabled:opacity-40"
              style={{ background: "linear-gradient(135deg,#a855f7,#7c3aed)", color: "#fff" }}>
              {testLoading ? "..." : <Send size={16} />}
            </button>
          </div>
          {testReply && (
            <div className="p-4 rounded-xl" style={{ background: "rgba(168,85,247,0.05)", border: "1px solid rgba(168,85,247,0.15)" }}>
              <div className="text-xs mb-2 font-bold" style={{ color: "#a855f7" }}>Réponse de l&apos;IA :</div>
              <div className="text-sm leading-relaxed" style={{ color: "#d1d5db" }}>{testReply}</div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
