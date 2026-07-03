"use client";
import { useState, useEffect } from "react";
import {
  Bot, CheckCircle, AlertCircle, RefreshCw, Copy,
  ExternalLink, Zap, ToggleLeft, ToggleRight, Trash2
} from "lucide-react";

interface BotInfo {
  id: number;
  username: string;
  first_name: string;
  can_join_groups: boolean;
}

interface BusinessStatus {
  connected: boolean;
  botToken: string | null;
  botInfo: BotInfo | null;
  webhookSet: boolean;
  businessEnabled: boolean;
}

export default function ConnectPage() {
  const [token, setToken] = useState("");
  const [status, setStatus] = useState<BusinessStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);
  const [aiEnabled, setAiEnabled] = useState(true);

  const appUrl = typeof window !== "undefined" ? window.location.origin : "";
  const webhookUrl = `${appUrl}/api/telegram/business`;

  const fetchStatus = async () => {
    try {
      const res = await fetch("/api/telegram/business");
      const d = await res.json();
      setStatus(d);
      if (d.botToken) setToken(d.botToken);
      if (d.businessEnabled !== undefined) setAiEnabled(d.businessEnabled);
    } catch { /* ignore */ }
  };

  useEffect(() => { fetchStatus(); }, []);

  const handleConnect = async () => {
    if (!token.trim()) return;
    setVerifying(true); setError("");
    try {
      const res = await fetch("/api/telegram/business", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "connect", token: token.trim() }),
      });
      const d = await res.json();
      if (!res.ok) throw new Error(d.error);
      await fetchStatus();
    } catch (e: unknown) { setError((e as Error).message); }
    finally { setVerifying(false); }
  };

  const handleSetWebhook = async () => {
    setLoading(true); setError("");
    try {
      const res = await fetch("/api/telegram/business", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "set-webhook", webhookUrl }),
      });
      const d = await res.json();
      if (!res.ok) throw new Error(d.error);
      await fetchStatus();
    } catch (e: unknown) { setError((e as Error).message); }
    finally { setLoading(false); }
  };

  const handleToggleAI = async () => {
    const next = !aiEnabled;
    setAiEnabled(next);
    await fetch("/api/telegram/business", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "toggle", enabled: next }),
    });
  };

  const handleDisconnect = async () => {
    await fetch("/api/telegram/business", { method: "DELETE" });
    setStatus(null); setToken("");
  };

  const copy = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  const steps = [
    {
      num: "01", done: !!status?.botInfo, title: "Crée ton bot avec @BotFather",
      content: (
        <div className="space-y-3">
          <p className="text-sm" style={{ color: "#9ca3af" }}>
            Dans Telegram, écris à <strong>@BotFather</strong> et envoie <code className="px-1 py-0.5 rounded text-xs" style={{ background: "#0a0a0f" }}>/newbot</code>.<br />
            Suis les instructions, récupère le token qui ressemble à : <code className="text-xs" style={{ color: "#a855f7" }}>1234567890:AAFxxxx...</code>
          </p>
          <a href="https://t.me/BotFather" target="_blank" rel="noreferrer"
            className="inline-flex items-center gap-2 text-sm px-3 py-2 rounded-lg transition-all hover:opacity-80"
            style={{ background: "rgba(168,85,247,0.1)", color: "#a855f7", border: "1px solid rgba(168,85,247,0.2)" }}>
            <ExternalLink size={13} /> Ouvrir @BotFather
          </a>
          <div>
            <label className="block text-xs mb-2" style={{ color: "#6b7280" }}>Token du bot</label>
            <div className="flex gap-2">
              <input
                value={token} onChange={e => setToken(e.target.value)}
                placeholder="1234567890:AAFxxxxxxxxxxxxxxx"
                className="flex-1 px-4 py-2.5 rounded-xl text-sm outline-none font-mono"
                style={{ background: "#0a0a0f", border: "1px solid #1e1e2e", color: "#d1d5db" }}
              />
              <button onClick={handleConnect} disabled={verifying || !token.trim()}
                className="px-4 py-2.5 rounded-xl text-sm font-medium disabled:opacity-40 flex items-center gap-2"
                style={{ background: "linear-gradient(135deg,#a855f7,#7c3aed)", color: "#fff" }}>
                {verifying ? <RefreshCw size={13} className="animate-spin" /> : <CheckCircle size={13} />}
                {verifying ? "..." : "Connecter"}
              </button>
            </div>
          </div>
          {status?.botInfo && (
            <div className="flex items-center gap-2 p-3 rounded-xl" style={{ background: "rgba(16,185,129,0.08)", border: "1px solid rgba(16,185,129,0.2)" }}>
              <CheckCircle size={14} style={{ color: "#10b981" }} />
              <span className="text-sm" style={{ color: "#10b981" }}>
                Bot connecté : <strong>@{status.botInfo.username}</strong> ({status.botInfo.first_name})
              </span>
              <button onClick={handleDisconnect} className="ml-auto" style={{ color: "#4b5563" }}>
                <Trash2 size={13} />
              </button>
            </div>
          )}
        </div>
      ),
    },
    {
      num: "02", done: !!status?.webhookSet, title: "Enregistre le webhook",
      content: (
        <div className="space-y-3">
          <p className="text-sm" style={{ color: "#9ca3af" }}>
            Le webhook dit à Telegram où envoyer les messages reçus par ton bot.
          </p>
          <div className="flex items-center gap-2 p-3 rounded-xl" style={{ background: "#0a0a0f", border: "1px solid #1e1e2e" }}>
            <code className="text-xs flex-1 truncate" style={{ color: "#a855f7" }}>{webhookUrl}</code>
            <button onClick={() => copy(webhookUrl)} className="flex-shrink-0" style={{ color: "#6b7280" }}>
              {copied ? <CheckCircle size={14} style={{ color: "#10b981" }} /> : <Copy size={14} />}
            </button>
          </div>
          <button onClick={handleSetWebhook} disabled={loading || !status?.botInfo}
            className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium disabled:opacity-40"
            style={{ background: "linear-gradient(135deg,#a855f7,#7c3aed)", color: "#fff" }}>
            {loading ? <RefreshCw size={13} className="animate-spin" /> : <Zap size={13} />}
            {loading ? "Enregistrement..." : "Enregistrer le webhook"}
          </button>
          {status?.webhookSet && (
            <div className="flex items-center gap-2 p-2 rounded-lg" style={{ color: "#10b981" }}>
              <CheckCircle size={13} /> <span className="text-xs">Webhook actif</span>
            </div>
          )}
        </div>
      ),
    },
    {
      num: "03", done: false, title: "Active Telegram Business sur ton compte",
      content: (
        <div className="space-y-3">
          <p className="text-sm" style={{ color: "#9ca3af" }}>
            Telegram Business te permet de connecter un bot à ton compte perso pour qu&apos;il réponde à ta place. Il faut <strong>Telegram Premium</strong> ou <strong>Telegram Business</strong>.
          </p>
          <div className="space-y-2 text-sm" style={{ color: "#9ca3af" }}>
            <div className="flex items-start gap-2">
              <span className="font-bold" style={{ color: "#a855f7" }}>1.</span>
              Ouvre Telegram sur ton téléphone → <strong>Paramètres</strong>
            </div>
            <div className="flex items-start gap-2">
              <span className="font-bold" style={{ color: "#a855f7" }}>2.</span>
              → <strong>Telegram Business</strong> (ou Premium)
            </div>
            <div className="flex items-start gap-2">
              <span className="font-bold" style={{ color: "#a855f7" }}>3.</span>
              → <strong>Chatbots</strong>
            </div>
            <div className="flex items-start gap-2">
              <span className="font-bold" style={{ color: "#a855f7" }}>4.</span>
              → Cherche <strong>@{status?.botInfo?.username ?? "ton_bot"}</strong> et sélectionne-le
            </div>
            <div className="flex items-start gap-2">
              <span className="font-bold" style={{ color: "#a855f7" }}>5.</span>
              Active <strong>&quot;Répondre aux messages&quot;</strong> ✓
            </div>
          </div>
          <div className="p-3 rounded-xl text-xs" style={{ background: "rgba(59,130,246,0.06)", color: "#93c5fd", border: "1px solid rgba(59,130,246,0.15)" }}>
            💡 Une fois connecté, <strong>tous les DMs que tu reçois</strong> passeront par ton bot — il répondra automatiquement avec l&apos;IA. Tu peux reprendre la main à tout moment en écrivant toi-même.
          </div>
        </div>
      ),
    },
  ];

  return (
    <div className="p-8" style={{ color: "#fff" }}>
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-black flex items-center gap-2">
            <Bot size={24} style={{ color: "#a855f7" }} />
            Connecter le bot Telegram
          </h1>
          <p className="text-sm mt-1" style={{ color: "#6b7280" }}>
            Ton bot répond à tes fans directement dans tes DMs Telegram Business
          </p>
        </div>

        {status?.botInfo && (
          <div className="flex items-center gap-3 px-4 py-2.5 rounded-xl border"
            style={{ background: "#111118", borderColor: "#1e1e2e" }}>
            <span className="text-sm" style={{ color: aiEnabled ? "#10b981" : "#6b7280" }}>
              IA {aiEnabled ? "Active" : "Inactive"}
            </span>
            <button onClick={handleToggleAI}>
              {aiEnabled
                ? <ToggleRight size={26} style={{ color: "#10b981" }} />
                : <ToggleLeft size={26} style={{ color: "#4b5563" }} />}
            </button>
          </div>
        )}
      </div>

      {error && (
        <div className="mb-6 flex items-center gap-2 p-4 rounded-xl text-sm"
          style={{ background: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.2)", color: "#fca5a5" }}>
          <AlertCircle size={15} /> {error}
        </div>
      )}

      {/* Statut global */}
      {status?.botInfo && status?.webhookSet && (
        <div className="mb-8 p-5 rounded-2xl border" style={{ background: "rgba(16,185,129,0.05)", borderColor: "rgba(16,185,129,0.25)" }}>
          <div className="flex items-center gap-3 mb-3">
            <div className="w-2 h-2 rounded-full animate-pulse" style={{ background: "#10b981" }} />
            <span className="font-bold" style={{ color: "#10b981" }}>Bot opérationnel</span>
          </div>
          <div className="grid grid-cols-3 gap-4 text-sm">
            <div>
              <div className="text-xs mb-1" style={{ color: "#6b7280" }}>Bot</div>
              <div className="font-medium">@{status.botInfo.username}</div>
            </div>
            <div>
              <div className="text-xs mb-1" style={{ color: "#6b7280" }}>Webhook</div>
              <div className="font-medium" style={{ color: "#10b981" }}>✓ Actif</div>
            </div>
            <div>
              <div className="text-xs mb-1" style={{ color: "#6b7280" }}>Mode</div>
              <div className="font-medium">Telegram Business</div>
            </div>
          </div>
        </div>
      )}

      {/* Steps */}
      <div className="space-y-5 max-w-2xl">
        {steps.map((s) => (
          <div key={s.num} className="rounded-2xl border p-6 transition-all"
            style={{ background: "#111118", borderColor: s.done ? "rgba(16,185,129,0.3)" : "#1e1e2e" }}>
            <div className="flex items-center gap-3 mb-4">
              <div className="w-8 h-8 rounded-full flex items-center justify-center text-sm font-black flex-shrink-0"
                style={s.done ? { background: "rgba(16,185,129,0.15)", color: "#10b981" } : { background: "rgba(168,85,247,0.1)", color: "#a855f7" }}>
                {s.done ? <CheckCircle size={16} /> : s.num}
              </div>
              <h2 className="font-bold">{s.title}</h2>
            </div>
            {s.content}
          </div>
        ))}
      </div>

      {/* Comment ça marche */}
      <div className="mt-8 max-w-2xl rounded-2xl border p-6" style={{ background: "#111118", borderColor: "#1e1e2e" }}>
        <h3 className="font-bold mb-4">Comment ça marche exactement</h3>
        <div className="space-y-3">
          {[
            { emoji: "📩", text: "Un fan t'envoie un DM sur ton compte Telegram" },
            { emoji: "🤖", text: "Telegram Business redirige le message vers ton bot" },
            { emoji: "🧠", text: "Le bot envoie le message à Claude avec ton style et ta personnalité" },
            { emoji: "💬", text: "Claude répond — la réponse apparaît dans le DM comme si c'était toi" },
            { emoji: "⭐", text: "Le bot peut envoyer des médias payants (Stars) automatiquement" },
            { emoji: "✋", text: "Tu peux reprendre la main à tout moment en répondant toi-même" },
          ].map(item => (
            <div key={item.emoji} className="flex items-center gap-3 text-sm" style={{ color: "#9ca3af" }}>
              <span className="text-lg">{item.emoji}</span>
              {item.text}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
