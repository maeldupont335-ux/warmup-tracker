"use client";
import React, { useState, useEffect, useCallback, Component } from "react";

class ErrorBoundary extends Component<{ children: React.ReactNode }, { error: string | null }> {
  constructor(props: { children: React.ReactNode }) { super(props); this.state = { error: null }; }
  static getDerivedStateFromError(e: Error) { return { error: e.message + "\n" + e.stack }; }
  render() {
    if (this.state.error) return (
      <div style={{ padding: 40, fontFamily: "monospace", background: "#0b0b12", color: "#f87171", minHeight: "100vh" }}>
        <h2 style={{ color: "#ef4444" }}>Erreur sur la page bot-docs</h2>
        <pre style={{ whiteSpace: "pre-wrap", wordBreak: "break-all", background: "#1a0000", padding: 20, borderRadius: 8, fontSize: 12 }}>{this.state.error}</pre>
      </div>
    );
    return this.props.children;
  }
}

interface BotTiming {
  paymentTimeoutMin: number;
  fastMin: number; fastMax: number;
  normalMin: number; normalMax: number;
  slowMin: number; slowMax: number;
  responseDelayMin: number; responseDelayMax: number;
  typingBeforeSendMs: number;
  warmupDelayMin: number; warmupDelayMax: number;
  interBubbleMin: number; interBubbleMax: number;
}

interface BotDocsConfig {
  warmupPrompt: string;
  interStepContext: string;
  waitingPaymentContext: string;
  discountPrompt: string;
  salePushPrompt: string;
  responseRules: string;
  sexyKeywords: string[];
  discountKeywords: string[];
  paidKeywords: string[];
  timings: BotTiming;
}

const DEFAULT_TIMINGS: BotTiming = {
  paymentTimeoutMin: 10,
  fastMin: 1, fastMax: 3,
  normalMin: 4, normalMax: 7,
  slowMin: 8, slowMax: 13,
  responseDelayMin: 20, responseDelayMax: 60,
  typingBeforeSendMs: 8000,
  warmupDelayMin: 15, warmupDelayMax: 35,
  interBubbleMin: 4, interBubbleMax: 9,
};

const NAV = [
  { id: "flow", label: "🗺 Flux du bot" },
  { id: "timings", label: "⏱ Timings" },
  { id: "prompts", label: "🤖 Prompts IA" },
  { id: "keywords", label: "🔑 Mots-clés" },
];

/* ── Composants UI ── */

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 20 }}>
      <div style={{ flex: 1, height: 1, background: "#1e1e2e" }} />
      <span style={{ color: "#6b7280", fontSize: 11, fontWeight: 700, letterSpacing: "0.1em", textTransform: "uppercase", whiteSpace: "nowrap" }}>{children}</span>
      <div style={{ flex: 1, height: 1, background: "#1e1e2e" }} />
    </div>
  );
}

function PromptEditor({ id, label, value, editMode, onChange, color = "#7c3aed", hint }: {
  id: string; label: string; value: string; editMode: boolean; onChange: (v: string) => void; color?: string; hint?: string;
}) {
  return (
    <div id={id} style={{ marginBottom: 28 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
        <span style={{ background: color + "22", border: `1px solid ${color}44`, color, padding: "2px 9px", borderRadius: 5, fontSize: 11, fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase" as const }}>{label}</span>
        {hint && <span style={{ color: "#4b5563", fontSize: 12 }}>{hint}</span>}
      </div>
      {editMode
        ? <textarea value={value} onChange={e => onChange(e.target.value)} style={{ width: "100%", minHeight: 130, padding: "12px 14px", background: "#0d0d18", border: `1px solid ${color}66`, borderRadius: 8, color: "#c9c9e8", fontSize: 13, lineHeight: 1.65, fontFamily: "ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace", resize: "vertical", outline: "none", boxSizing: "border-box" }} />
        : <pre style={{ margin: 0, padding: "12px 14px", background: "#0d0d18", border: "1px solid #1e1e2e", borderRadius: 8, color: "#c9c9e8", fontSize: 13, lineHeight: 1.65, fontFamily: "ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace", whiteSpace: "pre-wrap", wordBreak: "break-word" }}>{value}</pre>
      }
    </div>
  );
}

function KeywordEditor({ id, label, value, editMode, onChange, color, hint }: {
  id: string; label: string; value: string[]; editMode: boolean; onChange: (v: string[]) => void; color: string; hint?: string;
}) {
  return (
    <div id={id} style={{ marginBottom: 24 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
        <span style={{ background: color + "22", border: `1px solid ${color}44`, color, padding: "2px 9px", borderRadius: 5, fontSize: 11, fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase" as const }}>{label}</span>
        {hint && <span style={{ color: "#4b5563", fontSize: 12 }}>{hint}</span>}
      </div>
      {editMode
        ? <textarea value={value.join(", ")} onChange={e => onChange(e.target.value.split(",").map(k => k.trim()).filter(Boolean))} style={{ width: "100%", minHeight: 70, padding: "10px 14px", background: "#0d0d18", border: `1px solid ${color}66`, borderRadius: 8, color: "#c9c9e8", fontSize: 13, lineHeight: 1.65, fontFamily: "ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace", resize: "vertical", outline: "none", boxSizing: "border-box" }} />
        : <div style={{ display: "flex", flexWrap: "wrap", gap: 7, padding: "8px 0" }}>{value.map(kw => <code key={kw} style={{ background: color + "15", border: `1px solid ${color}33`, color, padding: "2px 9px", borderRadius: 5, fontSize: 12, fontFamily: "ui-monospace,Menlo,monospace" }}>{kw}</code>)}</div>
      }
    </div>
  );
}

function NumInput({ label, unit, value, editMode, onChange, min = 0, max = 9999 }: {
  label: string; unit?: string; value: number; editMode: boolean; onChange: (v: number) => void; min?: number; max?: number;
}) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
      <span style={{ fontSize: 11, color: "#6b7280", fontWeight: 600 }}>{label}</span>
      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
        {editMode
          ? <input type="number" value={value} min={min} max={max} onChange={e => onChange(Number(e.target.value))} style={{ width: 72, padding: "6px 10px", background: "#0d0d18", border: "1px solid #7c3aed66", borderRadius: 7, color: "#e4e4f0", fontSize: 14, fontWeight: 700, outline: "none", fontFamily: "ui-monospace,Menlo,monospace" }} />
          : <span style={{ fontSize: 16, fontWeight: 800, color: "#a78bfa", fontFamily: "ui-monospace,Menlo,monospace" }}>{value}</span>
        }
        {unit && <span style={{ fontSize: 12, color: "#4b5563" }}>{unit}</span>}
      </div>
    </div>
  );
}

/* ── Flow Diagram ── */
function FlowDiagram({ timings }: { timings: BotTiming }) {
  const node = (icon: string, label: string, sub: string, color: string) => (
    <div style={{ background: "#111119", border: `1px solid ${color}55`, borderRadius: 10, padding: "10px 16px", minWidth: 148, textAlign: "center", boxShadow: `0 0 16px ${color}18` }}>
      <div style={{ fontSize: 18, marginBottom: 3 }}>{icon}</div>
      <div style={{ color, fontWeight: 700, fontSize: 13 }}>{label}</div>
      {sub && <div style={{ color: "#6b7280", fontSize: 10, marginTop: 2 }}>{sub}</div>}
    </div>
  );
  const arrow = (label?: string) => (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 1, padding: "2px 0" }}>
      {label && <span style={{ color: "#4b5563", fontSize: 10, fontStyle: "italic", marginBottom: 2 }}>{label}</span>}
      <div style={{ width: 1, height: 20, background: "#2e2e4e" }} />
      <div style={{ width: 0, height: 0, borderLeft: "5px solid transparent", borderRight: "5px solid transparent", borderTop: "7px solid #2e2e4e" }} />
    </div>
  );
  const badge = (text: string, color: string) => (
    <span style={{ background: color + "22", border: `1px solid ${color}44`, color, fontSize: 10, fontWeight: 700, padding: "1px 7px", borderRadius: 4 }}>{text}</span>
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 0, overflowX: "auto", padding: "8px 0" }}>
      {node("📩", "Message fan", "Telegram webhook", "#10b981")}
      {arrow("vérif. licence")}
      {node("🔑", "Contrôle licence", "isCreatorLicenseActive()", "#f59e0b")}
      {arrow("licence OK")}
      {node("⭐", "Paiement Stars ?", "successful_payment", "#e11d48")}

      <div style={{ display: "flex", gap: 40, margin: "6px 0", alignItems: "flex-start" }}>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
          <div style={{ fontSize: 10, fontWeight: 700, color: "#10b981", marginBottom: 6 }}>OUI → paiement confirmé</div>
          {node("✅", "Avance script", "stepIndex += 1", "#10b981")}
        </div>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 0 }}>
          <div style={{ fontSize: 10, fontWeight: 700, color: "#e11d48", marginBottom: 6 }}>NON → texte normal</div>
          {node("⏳", "waitingForPayment ?", "média payant en attente", "#f59e0b")}
          {arrow()}
          <div style={{ display: "flex", gap: 16, alignItems: "flex-start" }}>
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
              <div style={{ fontSize: 9, color: "#f59e0b", fontWeight: 600, marginBottom: 5, textAlign: "center" }}>discount kw<br />ou {timings.paymentTimeoutMin} min</div>
              {node("💸", "Prompt réduction", "prix réduit", "#f59e0b")}
            </div>
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
              <div style={{ fontSize: 9, color: "#e11d48", fontWeight: 600, marginBottom: 5, textAlign: "center" }}>skipFollowup OFF<br />+ {timings.paymentTimeoutMin} min</div>
              {node("🔥", "Relance vente", "salePushSent → stop", "#e11d48")}
            </div>
          </div>
        </div>
      </div>

      {arrow("flux normal")}
      {node("⏱️", "Cooldown sexualisation", "cooldownDays ou sexy kw", "#6366f1")}
      {arrow("cooldown OK")}
      {node("📋", "Script à lancer ?", "pickBestScript()", "#7c3aed")}
      {arrow()}

      <div style={{ display: "flex", gap: 40, margin: "6px 0", alignItems: "flex-start" }}>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
          <div style={{ fontSize: 9, color: "#7c3aed", fontWeight: 600, marginBottom: 5, textAlign: "center" }}>1er script<br />+ pas encore de warmup</div>
          {node("🔥", "Warmup", `délai ${timings.warmupDelayMin}-${timings.warmupDelayMax}s`, "#7c3aed")}
        </div>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
          <div style={{ fontSize: 9, color: "#6366f1", fontWeight: 600, marginBottom: 5, textAlign: "center" }}>messages ≥ needed<br />{badge(`⚡ ${timings.fastMin}-${timings.fastMax}`, "#10b981")} {badge(`📍 ${timings.normalMin}-${timings.normalMax}`, "#f59e0b")} {badge(`🐢 ${timings.slowMin}-${timings.slowMax}`, "#e11d48")}</div>
          {node("🎬", "Étape script", "sendScriptStep()", "#6366f1")}
        </div>
      </div>

      {arrow()}
      {node("🤖", "Réponse IA", `délai ${timings.responseDelayMin}-${timings.responseDelayMax}s + typing ${timings.typingBeforeSendMs / 1000}s`, "#10b981")}
      {arrow()}
      {node("👤", "Profil fan mis à jour", "async, après envoi", "#4b5563")}
    </div>
  );
}

/* ── Page principale ── */
function BotDocsPageInner() {
  const [config, setConfig] = useState<BotDocsConfig | null>(null);
  const [editMode, setEditMode] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [activeNav, setActiveNav] = useState("flow");

  useEffect(() => {
    fetch("/api/bot-docs")
      .then(r => r.json())
      .then(d => {
        const raw = d.config ?? d.defaults;
        if (raw) setConfig({ ...raw, timings: { ...DEFAULT_TIMINGS, ...(raw.timings ?? {}) } });
      })
      .catch(() => {});
  }, []);

  const update = useCallback(<K extends keyof BotDocsConfig>(key: K, value: BotDocsConfig[K]) => {
    setConfig(c => c ? { ...c, [key]: value } : c);
  }, []);

  const updateTiming = useCallback((key: keyof BotTiming, value: number) => {
    setConfig(c => c ? { ...c, timings: { ...c.timings, [key]: value } } : c);
  }, []);

  const handleSave = async () => {
    if (!config) return;
    setSaving(true);
    await fetch("/api/bot-docs", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(config) });
    setSaving(false); setSaved(true); setEditMode(false);
    setTimeout(() => setSaved(false), 3000);
  };

  const scrollTo = (id: string) => {
    setActiveNav(id);
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth" });
  };

  if (!config) return <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "60vh", color: "#6b7280", fontFamily: "system-ui,sans-serif" }}>Chargement…</div>;

  const s: React.CSSProperties = { fontFamily: "system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif" };

  return (
    <div style={{ minHeight: "100vh", background: "#0b0b12", color: "#e4e4f0", display: "flex", ...s }}>

      {/* Sidebar */}
      <nav style={{ width: 200, flexShrink: 0, position: "sticky", top: 0, height: "100vh", padding: "24px 0", borderRight: "1px solid #1a1a2a", background: "#0d0d1a", overflowY: "auto" }}>
        <div style={{ padding: "0 16px 16px", borderBottom: "1px solid #1a1a2a", marginBottom: 12 }}>
          <div style={{ fontSize: 10, fontWeight: 700, color: "#e11d48", letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: 2 }}>OnlyChat AI</div>
          <div style={{ fontSize: 13, fontWeight: 700, color: "#e4e4f0" }}>Config & Flux</div>
        </div>
        {NAV.map(n => (
          <button key={n.id} onClick={() => scrollTo(n.id)} style={{ width: "100%", textAlign: "left", padding: "9px 16px", background: activeNav === n.id ? "#7c3aed18" : "transparent", borderLeft: activeNav === n.id ? "2px solid #7c3aed" : "2px solid transparent", border: "none", color: activeNav === n.id ? "#a78bfa" : "#6b7280", fontSize: 13, cursor: "pointer", fontFamily: "inherit", transition: "all 0.12s" }}>
            {n.label}
          </button>
        ))}
      </nav>

      {/* Main */}
      <main style={{ flex: 1, padding: "36px 44px", maxWidth: 900, overflowY: "auto" }}>

        {/* Header */}
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 40 }}>
          <div>
            <h1 style={{ margin: "0 0 6px", fontSize: 26, fontWeight: 800 }}>Bot — Configuration</h1>
            <p style={{ margin: 0, color: "#6b7280", fontSize: 14 }}>{editMode ? "Mode édition actif — modifie librement puis publie." : "Clique Modifier pour éditer les prompts, timings et mots-clés."}</p>
          </div>
          <div style={{ display: "flex", gap: 10, flexShrink: 0 }}>
            {editMode
              ? <>
                  <button onClick={() => setEditMode(false)} style={{ padding: "9px 16px", borderRadius: 8, border: "1px solid #2e2e4e", background: "transparent", color: "#6b7280", fontSize: 13, cursor: "pointer", fontFamily: "inherit" }}>Annuler</button>
                  <button onClick={handleSave} disabled={saving} style={{ padding: "9px 22px", borderRadius: 8, border: "none", background: saving ? "#4c1d95" : "linear-gradient(135deg,#7c3aed,#a855f7)", color: "#fff", fontSize: 13, fontWeight: 700, cursor: saving ? "not-allowed" : "pointer", fontFamily: "inherit" }}>
                    {saving ? "Publication…" : "✓ Sauvegarder & Publier"}
                  </button>
                </>
              : <button onClick={() => setEditMode(true)} style={{ padding: "9px 20px", borderRadius: 8, border: "1px solid #7c3aed55", background: "rgba(124,58,237,0.1)", color: "#a78bfa", fontSize: 13, fontWeight: 600, cursor: "pointer", fontFamily: "inherit" }}>
                  ✏️ Modifier
                </button>
            }
          </div>
        </div>

        {saved && (
          <div style={{ position: "fixed", top: 20, right: 24, zIndex: 100, background: "#064e3b", border: "1px solid #10b981", borderRadius: 10, padding: "12px 20px", color: "#34d399", fontSize: 14, fontWeight: 600, boxShadow: "0 8px 24px rgba(0,0,0,0.4)" }}>
            ✓ Publié — le bot utilise maintenant ta nouvelle config
          </div>
        )}

        {/* ── FLUX ── */}
        <section id="flow" style={{ scrollMarginTop: 80, marginBottom: 52 }}>
          <SectionTitle>Flux du bot — étape par étape</SectionTitle>
          <p style={{ color: "#6b7280", fontSize: 13, marginBottom: 20 }}>
            Les valeurs affichées dans le schéma sont celles actuellement configurées. Modifie-les dans la section Timings ci-dessous.
          </p>
          <FlowDiagram timings={config.timings} />
        </section>

        {/* ── TIMINGS ── */}
        <section id="timings" style={{ scrollMarginTop: 80, marginBottom: 52 }}>
          <SectionTitle>Timings & Vitesses</SectionTitle>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>

            <div style={{ background: "#111119", border: "1px solid #1e1e2e", borderRadius: 12, padding: "20px 24px" }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: "#f59e0b", marginBottom: 16, letterSpacing: "0.05em", textTransform: "uppercase" }}>⏱ Timeout paiement</div>
              <NumInput label="Délai avant réduction / relance" unit="minutes" value={config.timings.paymentTimeoutMin} editMode={editMode} onChange={v => updateTiming("paymentTimeoutMin", v)} min={1} max={60} />
              <p style={{ color: "#4b5563", fontSize: 12, marginTop: 10, marginBottom: 0 }}>Après ce délai sans paiement : propose une réduction (si activée) ou envoie une relance vente.</p>
            </div>

            <div style={{ background: "#111119", border: "1px solid #1e1e2e", borderRadius: 12, padding: "20px 24px" }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: "#10b981", marginBottom: 16, letterSpacing: "0.05em", textTransform: "uppercase" }}>🚀 Délai réponse IA</div>
              <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
                <NumInput label="Min" unit="sec" value={config.timings.responseDelayMin} editMode={editMode} onChange={v => updateTiming("responseDelayMin", v)} min={0} max={300} />
                <NumInput label="Max" unit="sec" value={config.timings.responseDelayMax} editMode={editMode} onChange={v => updateTiming("responseDelayMax", v)} min={0} max={300} />
                <NumInput label="Typing avant envoi" unit="ms" value={config.timings.typingBeforeSendMs} editMode={editMode} onChange={v => updateTiming("typingBeforeSendMs", v)} min={0} max={30000} />
              </div>
            </div>

            <div style={{ background: "#111119", border: "1px solid #1e1e2e", borderRadius: 12, padding: "20px 24px" }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: "#7c3aed", marginBottom: 16, letterSpacing: "0.05em", textTransform: "uppercase" }}>⏳ Délai warmup</div>
              <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
                <NumInput label="Min" unit="sec" value={config.timings.warmupDelayMin} editMode={editMode} onChange={v => updateTiming("warmupDelayMin", v)} min={0} max={300} />
                <NumInput label="Max" unit="sec" value={config.timings.warmupDelayMax} editMode={editMode} onChange={v => updateTiming("warmupDelayMax", v)} min={0} max={300} />
              </div>
            </div>

            <div style={{ background: "#111119", border: "1px solid #1e1e2e", borderRadius: 12, padding: "20px 24px" }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: "#6366f1", marginBottom: 16, letterSpacing: "0.05em", textTransform: "uppercase" }}>💬 Délai inter-bulles</div>
              <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
                <NumInput label="Min" unit="sec" value={config.timings.interBubbleMin} editMode={editMode} onChange={v => updateTiming("interBubbleMin", v)} min={1} max={60} />
                <NumInput label="Max" unit="sec" value={config.timings.interBubbleMax} editMode={editMode} onChange={v => updateTiming("interBubbleMax", v)} min={1} max={60} />
              </div>
            </div>

            <div style={{ background: "#111119", border: "1px solid #1e1e2e", borderRadius: 12, padding: "20px 24px", gridColumn: "1 / -1" }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: "#e4e4f0", marginBottom: 6, letterSpacing: "0.05em", textTransform: "uppercase" }}>📊 Vitesse d'avancement script</div>
              <div style={{ color: "#4b5563", fontSize: 12, marginBottom: 16 }}>Nombre de messages du fan requis avant que le bot envoie la prochaine étape.</div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 20 }}>
                <div style={{ background: "#0d0d18", borderRadius: 10, padding: "16px 18px", border: "1px solid #10b98133" }}>
                  <div style={{ fontSize: 11, fontWeight: 700, color: "#10b981", marginBottom: 12 }}>⚡ RAPIDE</div>
                  <div style={{ display: "flex", gap: 12 }}>
                    <NumInput label="Min" value={config.timings.fastMin} editMode={editMode} onChange={v => updateTiming("fastMin", v)} min={1} max={20} />
                    <NumInput label="Max" value={config.timings.fastMax} editMode={editMode} onChange={v => updateTiming("fastMax", v)} min={1} max={20} />
                  </div>
                </div>
                <div style={{ background: "#0d0d18", borderRadius: 10, padding: "16px 18px", border: "1px solid #f59e0b33" }}>
                  <div style={{ fontSize: 11, fontWeight: 700, color: "#f59e0b", marginBottom: 12 }}>📍 NORMAL</div>
                  <div style={{ display: "flex", gap: 12 }}>
                    <NumInput label="Min" value={config.timings.normalMin} editMode={editMode} onChange={v => updateTiming("normalMin", v)} min={1} max={30} />
                    <NumInput label="Max" value={config.timings.normalMax} editMode={editMode} onChange={v => updateTiming("normalMax", v)} min={1} max={30} />
                  </div>
                </div>
                <div style={{ background: "#0d0d18", borderRadius: 10, padding: "16px 18px", border: "1px solid #e11d4833" }}>
                  <div style={{ fontSize: 11, fontWeight: 700, color: "#e11d48", marginBottom: 12 }}>🐢 LENT</div>
                  <div style={{ display: "flex", gap: 12 }}>
                    <NumInput label="Min" value={config.timings.slowMin} editMode={editMode} onChange={v => updateTiming("slowMin", v)} min={1} max={50} />
                    <NumInput label="Max" value={config.timings.slowMax} editMode={editMode} onChange={v => updateTiming("slowMax", v)} min={1} max={50} />
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* ── PROMPTS ── */}
        <section id="prompts" style={{ scrollMarginTop: 80, marginBottom: 52 }}>
          <SectionTitle>Prompts IA</SectionTitle>
          <PromptEditor id="p-warmup" label="Warmup" color="#7c3aed" hint="Envoyé une seule fois avant le 1er script" value={config.warmupPrompt} editMode={editMode} onChange={v => update("warmupPrompt", v)} />
          <PromptEditor id="p-interstep" label="Inter-étape" color="#6366f1" hint="{remaining} = messages restants · {teaser} = indice contenu" value={config.interStepContext} editMode={editMode} onChange={v => update("interStepContext", v)} />
          <PromptEditor id="p-waiting" label="Attente paiement" color="#e11d48" hint="Remplace l'inter-étape quand waitingForPayment = true" value={config.waitingPaymentContext} editMode={editMode} onChange={v => update("waitingPaymentContext", v)} />
          <PromptEditor id="p-discount" label="Réduction" color="#f59e0b" hint="{reason} = raison de l'hésitation" value={config.discountPrompt} editMode={editMode} onChange={v => update("discountPrompt", v)} />
          <PromptEditor id="p-salepush" label="Relance vente" color="#e11d48" hint="Après timeout paiement (skipFollowup OFF)" value={config.salePushPrompt} editMode={editMode} onChange={v => update("salePushPrompt", v)} />
          <PromptEditor id="p-rules" label="Règles de réponse" color="#10b981" hint="Injecté à la fin de chaque réponse IA" value={config.responseRules} editMode={editMode} onChange={v => update("responseRules", v)} />
        </section>

        {/* ── KEYWORDS ── */}
        <section id="keywords" style={{ scrollMarginTop: 80, marginBottom: 52 }}>
          <SectionTitle>Mots-clés déclencheurs</SectionTitle>
          <KeywordEditor id="kw-sexy" label="Mots sexy" color="#e11d48" hint="Court-circuite le cooldown → lance le script immédiatement" value={config.sexyKeywords} editMode={editMode} onChange={v => update("sexyKeywords", v)} />
          <KeywordEditor id="kw-discount" label="Mots réduction" color="#f59e0b" hint="Déclenche la réduction sans attendre le timeout" value={config.discountKeywords} editMode={editMode} onChange={v => update("discountKeywords", v)} />
          <KeywordEditor id="kw-paid" label="Mots paiement" color="#10b981" hint="Fallback si le webhook successful_payment est manqué" value={config.paidKeywords} editMode={editMode} onChange={v => update("paidKeywords", v)} />
        </section>

        {editMode && (
          <div style={{ display: "flex", justifyContent: "flex-end", gap: 10, paddingTop: 20, borderTop: "1px solid #1a1a2a" }}>
            <button onClick={() => setEditMode(false)} style={{ padding: "10px 18px", borderRadius: 8, border: "1px solid #2e2e4e", background: "transparent", color: "#6b7280", fontSize: 13, cursor: "pointer", fontFamily: "inherit" }}>Annuler</button>
            <button onClick={handleSave} disabled={saving} style={{ padding: "10px 26px", borderRadius: 8, border: "none", background: saving ? "#4c1d95" : "linear-gradient(135deg,#7c3aed,#a855f7)", color: "#fff", fontSize: 13, fontWeight: 700, cursor: saving ? "not-allowed" : "pointer", fontFamily: "inherit" }}>
              {saving ? "Publication…" : "✓ Sauvegarder & Publier"}
            </button>
          </div>
        )}
        <div style={{ height: 60 }} />
      </main>
    </div>
  );
}

export default function BotDocsPage() {
  return <ErrorBoundary><BotDocsPageInner /></ErrorBoundary>;
}
