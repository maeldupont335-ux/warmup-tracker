"use client";
import React, { useState, useEffect, useCallback } from "react";

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
}

const SECTIONS = [
  { id: "warmup", label: "Warmup" },
  { id: "interstep", label: "Inter-étape" },
  { id: "waitingpayment", label: "Attente paiement" },
  { id: "discount", label: "Réduction" },
  { id: "salepush", label: "Relance vente" },
  { id: "rules", label: "Règles de réponse" },
  { id: "sexy", label: "Mots sexy" },
  { id: "discountkw", label: "Mots réduction" },
  { id: "paidkw", label: "Mots paiement" },
];

function PromptEditor({
  id, label, value, editMode, onChange, color = "#7c3aed", hint,
}: {
  id: string; label: string; value: string; editMode: boolean; onChange: (v: string) => void;
  color?: string; hint?: string;
}) {
  return (
    <section id={id} style={{ scrollMarginTop: 80, marginBottom: 40 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
        <span style={{
          background: color + "22", border: `1px solid ${color}44`,
          color, padding: "3px 10px", borderRadius: 5,
          fontSize: 11, fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase" as const,
        }}>{label}</span>
        {hint && <span style={{ color: "#6b7280", fontSize: 12 }}>{hint}</span>}
      </div>
      {editMode ? (
        <textarea
          value={value}
          onChange={e => onChange(e.target.value)}
          style={{
            width: "100%", minHeight: 160, padding: "14px 16px",
            background: "#0d0d18", border: `1px solid ${color}55`,
            borderRadius: 8, color: "#c9c9e8", fontSize: 13, lineHeight: 1.65,
            fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
            resize: "vertical", outline: "none", boxSizing: "border-box",
          }}
          onFocus={e => { e.currentTarget.style.borderColor = color; }}
          onBlur={e => { e.currentTarget.style.borderColor = color + "55"; }}
        />
      ) : (
        <pre style={{
          margin: 0, padding: "14px 16px",
          background: "#0d0d18", border: "1px solid #1e1e2e",
          borderRadius: 8, color: "#c9c9e8", fontSize: 13, lineHeight: 1.65,
          fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
          whiteSpace: "pre-wrap", wordBreak: "break-word",
        }}>{value}</pre>
      )}
    </section>
  );
}

function KeywordEditor({
  id, label, value, editMode, onChange, color,
}: {
  id: string; label: string; value: string[]; editMode: boolean; onChange: (v: string[]) => void; color: string;
}) {
  const text = value.join(", ");
  return (
    <section id={id} style={{ scrollMarginTop: 80, marginBottom: 40 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
        <span style={{
          background: color + "22", border: `1px solid ${color}44`,
          color, padding: "3px 10px", borderRadius: 5,
          fontSize: 11, fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase" as const,
        }}>{label}</span>
        <span style={{ color: "#6b7280", fontSize: 12 }}>séparés par des virgules</span>
      </div>
      {editMode ? (
        <textarea
          value={text}
          onChange={e => onChange(e.target.value.split(",").map(k => k.trim()).filter(Boolean))}
          style={{
            width: "100%", minHeight: 80, padding: "12px 14px",
            background: "#0d0d18", border: `1px solid ${color}55`,
            borderRadius: 8, color: "#c9c9e8", fontSize: 13, lineHeight: 1.65,
            fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
            resize: "vertical", outline: "none", boxSizing: "border-box",
          }}
          onFocus={e => { e.currentTarget.style.borderColor = color; }}
          onBlur={e => { e.currentTarget.style.borderColor = color + "55"; }}
        />
      ) : (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, padding: "12px 0" }}>
          {value.map(kw => (
            <code key={kw} style={{
              background: color + "15", border: `1px solid ${color}33`,
              color, padding: "3px 10px", borderRadius: 5, fontSize: 12,
              fontFamily: "ui-monospace, Menlo, monospace",
            }}>{kw}</code>
          ))}
        </div>
      )}
    </section>
  );
}

export default function BotDocsPage() {
  const [config, setConfig] = useState<BotDocsConfig | null>(null);
  const [defaults, setDefaults] = useState<BotDocsConfig | null>(null);
  const [editMode, setEditMode] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [activeSection, setActiveSection] = useState("warmup");

  useEffect(() => {
    fetch("/api/bot-docs").then(r => r.json()).then(d => {
      setConfig(d.config);
      setDefaults(d.defaults);
    });
  }, []);

  const update = useCallback(<K extends keyof BotDocsConfig>(key: K, value: BotDocsConfig[K]) => {
    setConfig(c => c ? { ...c, [key]: value } : c);
  }, []);

  const handleSave = async () => {
    if (!config) return;
    setSaving(true);
    await fetch("/api/bot-docs", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(config) });
    setSaving(false);
    setSaved(true);
    setEditMode(false);
    setTimeout(() => setSaved(false), 3000);
  };

  const handleReset = () => {
    if (defaults) setConfig({ ...defaults });
  };

  const scrollTo = (id: string) => {
    setActiveSection(id);
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth" });
  };

  if (!config) return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "60vh", color: "#6b7280", fontFamily: "system-ui, sans-serif" }}>
      Chargement…
    </div>
  );

  return (
    <div style={{
      minHeight: "100vh", background: "#0b0b12", color: "#e4e4f0",
      fontFamily: "system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
      display: "flex",
    }}>
      {/* Sidebar */}
      <nav style={{
        width: 210, flexShrink: 0, position: "sticky", top: 0, height: "100vh",
        padding: "24px 0", borderRight: "1px solid #1a1a2a", overflowY: "auto",
        background: "#0d0d1a",
      }}>
        <div style={{ padding: "0 18px 18px", borderBottom: "1px solid #1a1a2a", marginBottom: 12 }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: "#e11d48", letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: 2 }}>Bot</div>
          <div style={{ fontSize: 14, fontWeight: 600, color: "#e4e4f0" }}>Prompts & Config</div>
        </div>
        {SECTIONS.map(s => (
          <button key={s.id} onClick={() => scrollTo(s.id)} style={{
            width: "100%", textAlign: "left", padding: "8px 18px",
            background: activeSection === s.id ? "#7c3aed18" : "transparent",
            borderLeft: activeSection === s.id ? "2px solid #7c3aed" : "2px solid transparent",
            border: "none", color: activeSection === s.id ? "#a78bfa" : "#6b7280",
            fontSize: 13, cursor: "pointer", fontFamily: "inherit", transition: "all 0.12s",
          }}>{s.label}</button>
        ))}
      </nav>

      {/* Main */}
      <main style={{ flex: 1, padding: "36px 44px", maxWidth: 860, overflowY: "auto" }}>
        {/* Header */}
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 36 }}>
          <div>
            <h1 style={{ margin: "0 0 6px", fontSize: 26, fontWeight: 800, color: "#e4e4f0" }}>Prompts du bot</h1>
            <p style={{ margin: 0, color: "#6b7280", fontSize: 14 }}>
              {editMode ? "Mode édition — modifie librement, puis publie." : "Clique sur Modifier pour éditer les prompts et mots-clés."}
            </p>
          </div>
          <div style={{ display: "flex", gap: 10, flexShrink: 0 }}>
            {editMode && (
              <button onClick={handleReset} style={{
                padding: "9px 16px", borderRadius: 8, border: "1px solid #2e2e4e",
                background: "transparent", color: "#6b7280", fontSize: 13, cursor: "pointer", fontFamily: "inherit",
              }}>
                Réinitialiser
              </button>
            )}
            {editMode ? (
              <button onClick={handleSave} disabled={saving} style={{
                padding: "9px 20px", borderRadius: 8, border: "none",
                background: saving ? "#4c1d95" : "linear-gradient(135deg, #7c3aed, #a855f7)",
                color: "#fff", fontSize: 13, fontWeight: 700, cursor: saving ? "not-allowed" : "pointer",
                fontFamily: "inherit", display: "flex", alignItems: "center", gap: 8,
              }}>
                {saving ? "Publication…" : "✓ Sauvegarder & Publier"}
              </button>
            ) : (
              <button onClick={() => setEditMode(true)} style={{
                padding: "9px 20px", borderRadius: 8, border: "1px solid #7c3aed55",
                background: "rgba(124,58,237,0.1)", color: "#a78bfa",
                fontSize: 13, fontWeight: 600, cursor: "pointer", fontFamily: "inherit",
              }}>
                ✏️ Modifier
              </button>
            )}
          </div>
        </div>

        {/* Toast succès */}
        {saved && (
          <div style={{
            position: "fixed", top: 20, right: 24, zIndex: 100,
            background: "#064e3b", border: "1px solid #10b981", borderRadius: 10,
            padding: "12px 20px", color: "#34d399", fontSize: 14, fontWeight: 600,
            boxShadow: "0 8px 24px rgba(0,0,0,0.4)",
          }}>
            ✓ Publié — le bot utilise maintenant tes nouveaux prompts
          </div>
        )}

        {/* Prompts */}
        <div style={{ borderBottom: "1px solid #1a1a2a", marginBottom: 32, paddingBottom: 8 }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: "#6b7280", letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: 20 }}>Prompts IA</div>
        </div>

        <PromptEditor id="warmup" label="Warmup" color="#7c3aed"
          hint="Envoyé une seule fois avant le 1er script"
          value={config.warmupPrompt} editMode={editMode}
          onChange={v => update("warmupPrompt", v)} />

        <PromptEditor id="interstep" label="Inter-étape" color="#6366f1"
          hint="Variables : {remaining} = messages restants, {teaser} = indice du prochain contenu"
          value={config.interStepContext} editMode={editMode}
          onChange={v => update("interStepContext", v)} />

        <PromptEditor id="waitingpayment" label="Attente paiement" color="#e11d48"
          hint="Remplace l'inter-étape quand waitingForPayment = true"
          value={config.waitingPaymentContext} editMode={editMode}
          onChange={v => update("waitingPaymentContext", v)} />

        <PromptEditor id="discount" label="Réduction" color="#f59e0b"
          hint="Variable : {reason} = raison de l'hésitation"
          value={config.discountPrompt} editMode={editMode}
          onChange={v => update("discountPrompt", v)} />

        <PromptEditor id="salepush" label="Relance vente" color="#e11d48"
          hint="Dernière relance après 10 min sans paiement (skipFollowup OFF)"
          value={config.salePushPrompt} editMode={editMode}
          onChange={v => update("salePushPrompt", v)} />

        <PromptEditor id="rules" label="Règles de réponse" color="#10b981"
          hint="Injecté à la fin de chaque prompt IA principal"
          value={config.responseRules} editMode={editMode}
          onChange={v => update("responseRules", v)} />

        {/* Keywords */}
        <div style={{ borderBottom: "1px solid #1a1a2a", margin: "36px 0 28px", paddingBottom: 8 }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: "#6b7280", letterSpacing: "0.08em", textTransform: "uppercase" }}>Mots-clés déclencheurs</div>
        </div>

        <KeywordEditor id="sexy" label="Mots sexy" color="#e11d48"
          hint="Court-circuite le cooldown de sexualisation → lance le script immédiatement"
          value={config.sexyKeywords} editMode={editMode}
          onChange={v => update("sexyKeywords", v)} />

        <KeywordEditor id="discountkw" label="Mots réduction" color="#f59e0b"
          hint="Déclenche l'offre de réduction sans attendre les 10 min"
          value={config.discountKeywords} editMode={editMode}
          onChange={v => update("discountKeywords", v)} />

        <KeywordEditor id="paidkw" label="Mots paiement" color="#10b981"
          hint="Fallback si le webhook successful_payment est manqué"
          value={config.paidKeywords} editMode={editMode}
          onChange={v => update("paidKeywords", v)} />

        {editMode && (
          <div style={{ display: "flex", justifyContent: "flex-end", gap: 10, marginTop: 20, paddingTop: 24, borderTop: "1px solid #1a1a2a" }}>
            <button onClick={() => setEditMode(false)} style={{
              padding: "10px 18px", borderRadius: 8, border: "1px solid #2e2e4e",
              background: "transparent", color: "#6b7280", fontSize: 13, cursor: "pointer", fontFamily: "inherit",
            }}>Annuler</button>
            <button onClick={handleSave} disabled={saving} style={{
              padding: "10px 24px", borderRadius: 8, border: "none",
              background: saving ? "#4c1d95" : "linear-gradient(135deg, #7c3aed, #a855f7)",
              color: "#fff", fontSize: 13, fontWeight: 700, cursor: saving ? "not-allowed" : "pointer", fontFamily: "inherit",
            }}>
              {saving ? "Publication…" : "✓ Sauvegarder & Publier"}
            </button>
          </div>
        )}
        <div style={{ height: 60 }} />
      </main>
    </div>
  );
}
