"use client";
import React, { useState, useEffect, useRef, Component } from "react";

/* ── Error Boundary ── */
class ErrorBoundary extends Component<{ children: React.ReactNode }, { error: string | null }> {
  constructor(props: { children: React.ReactNode }) { super(props); this.state = { error: null }; }
  static getDerivedStateFromError(e: Error) { return { error: e.message + "\n" + e.stack }; }
  render() {
    if (this.state.error) return (
      <div style={{ padding: 40, fontFamily: "monospace", background: "#0b0b12", color: "#f87171", minHeight: "100vh" }}>
        <h2 style={{ color: "#ef4444" }}>Erreur bot-docs</h2>
        <pre style={{ whiteSpace: "pre-wrap", wordBreak: "break-all", background: "#1a0000", padding: 20, borderRadius: 8, fontSize: 12 }}>{this.state.error}</pre>
      </div>
    );
    return this.props.children;
  }
}

/* ── Types ── */
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

interface FlowStep {
  id: string;
  icon: string;
  label: string;
  description: string;
  color: string;
  timingNote: string;
}

interface BotPhase {
  id: string;
  name: string;
  icon: string;
  prompt: string;
  advanceAfterMessages: number;
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
  flowSteps: FlowStep[];
  phases: BotPhase[];
}

/* ── Défauts ── */
const DEFAULT_PHASES: BotPhase[] = [
  { id: "phase1", name: "Phase 1 — Nouveau client", icon: "👋", prompt: "C'est la toute première conversation avec ce fan. Accueille-le chaleureusement, présente-toi brièvement et crée une connexion naturelle. Pose-lui une question simple sur lui (son prénom, sa journée).", advanceAfterMessages: 5 },
  { id: "phase2", name: "Phase 2 — Présentation", icon: "💬", prompt: "Tu connais déjà un peu ce fan. Approfondis la relation : parle de toi, de ce que tu fais, de ton quotidien. Montre-toi intéressante et mystérieuse. Continue à apprendre à le connaître.", advanceAfterMessages: 10 },
  { id: "phase3", name: "Phase 3 — Fidélisation", icon: "🔥", prompt: "Le fan te connaît bien maintenant. Renforce la relation, rappelle-toi de détails qu'il t'a partagés, sois plus intime et complice. Commence à créer une tension légère et intrigante.", advanceAfterMessages: 20 },
  { id: "phase4", name: "Phase 4 — Lancement script", icon: "🎬", prompt: "Le fan est fidèle et engagé. Le moment est venu de l'amener vers du contenu exclusif. Crée l'envie naturellement, sois mystérieuse et taquine.", advanceAfterMessages: 0 },
];

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

const DEFAULT_FLOW_STEPS: FlowStep[] = [
  { id: "s1", icon: "📩", label: "Message fan", description: "Telegram webhook reçoit le message", color: "#10b981", timingNote: "" },
  { id: "s2", icon: "🔑", label: "Contrôle licence", description: "Vérifie que la licence créatrice est active", color: "#f59e0b", timingNote: "" },
  { id: "s3", icon: "⭐", label: "Paiement Stars ?", description: "Événement successful_payment détecté ?", color: "#e11d48", timingNote: "" },
  { id: "s4", icon: "✅", label: "Avance script", description: "Paiement OK → stepIndex += 1", color: "#10b981", timingNote: "" },
  { id: "s5", icon: "⏳", label: "Attente paiement ?", description: "Média payant en attente de validation", color: "#f59e0b", timingNote: "Timeout : {paymentTimeoutMin} min" },
  { id: "s6", icon: "💸", label: "Prompt réduction", description: "Discount kw ou timeout → propose prix réduit", color: "#f59e0b", timingNote: "" },
  { id: "s7", icon: "🔥", label: "Relance vente", description: "Après timeout → salePushSent → stop", color: "#e11d48", timingNote: "" },
  { id: "s8", icon: "⏱️", label: "Cooldown sexualisation", description: "Vérifie cooldownDays ou mot-clé sexy", color: "#6366f1", timingNote: "" },
  { id: "s9", icon: "📋", label: "Script à lancer ?", description: "pickBestScript() sélectionne le script", color: "#7c3aed", timingNote: "" },
  { id: "s10", icon: "🔥", label: "Warmup", description: "Premier script → messages de chauffe", color: "#7c3aed", timingNote: "Délai : {warmupDelayMin}-{warmupDelayMax}s" },
  { id: "s11", icon: "🎬", label: "Étape script", description: "Messages ≥ needed → sendScriptStep()", color: "#6366f1", timingNote: "Vitesse : rapide/normal/lent" },
  { id: "s12", icon: "🤖", label: "Réponse IA", description: "GPT génère et envoie la réponse", color: "#10b981", timingNote: "Délai : {responseDelayMin}-{responseDelayMax}s + typing {typingBeforeSendMs}ms" },
  { id: "s13", icon: "👤", label: "Profil fan mis à jour", description: "Mise à jour async après envoi", color: "#4b5563", timingNote: "" },
];

const COLORS = ["#10b981", "#f59e0b", "#e11d48", "#7c3aed", "#6366f1", "#4b5563", "#3b82f6", "#ec4899", "#14b8a6", "#f97316"];

const NAV = [
  { id: "flow", label: "🗺 Flux du bot" },
  { id: "phases", label: "🔄 Phases" },
  { id: "timings", label: "⏱ Timings" },
  { id: "prompts", label: "🤖 Prompts IA" },
  { id: "keywords", label: "🔑 Mots-clés" },
];

/* ── UI helpers ── */
function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 20 }}>
      <div style={{ flex: 1, height: 1, background: "#1e1e2e" }} />
      <span style={{ color: "#6b7280", fontSize: 11, fontWeight: 700, letterSpacing: "0.1em", textTransform: "uppercase", whiteSpace: "nowrap" }}>{children}</span>
      <div style={{ flex: 1, height: 1, background: "#1e1e2e" }} />
    </div>
  );
}

function PromptEditor({ label, value, editMode, onChange, color = "#7c3aed", hint }: {
  label: string; value: string; editMode: boolean; onChange: (v: string) => void; color?: string; hint?: string;
}) {
  return (
    <div style={{ marginBottom: 28 }}>
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

function KeywordEditor({ label, value, editMode, onChange, color, hint }: {
  label: string; value: string[]; editMode: boolean; onChange: (v: string[]) => void; color: string; hint?: string;
}) {
  return (
    <div style={{ marginBottom: 24 }}>
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

/* ── Drag & Drop Flow List ── */
function FlowList({ steps, editMode, onReorder, onUpdate, onDelete, onAdd, onReset }: {
  steps: FlowStep[]; editMode: boolean;
  onReorder: (steps: FlowStep[]) => void;
  onUpdate: (i: number, s: FlowStep) => void;
  onDelete: (i: number) => void;
  onAdd: () => void;
  onReset: () => void;
}) {
  const dragIdx = useRef<number | null>(null);
  const [overIdx, setOverIdx] = useState<number | null>(null);
  const [openIdx, setOpenIdx] = useState<number | null>(null);

  const handleDragStart = (i: number) => { dragIdx.current = i; };
  const handleDragOver = (e: React.DragEvent, i: number) => {
    e.preventDefault();
    setOverIdx(i);
  };
  const handleDrop = (e: React.DragEvent, i: number) => {
    e.preventDefault();
    if (dragIdx.current === null || dragIdx.current === i) { setOverIdx(null); return; }
    const arr = [...steps];
    const [moved] = arr.splice(dragIdx.current, 1);
    arr.splice(i, 0, moved);
    onReorder(arr);
    dragIdx.current = null;
    setOverIdx(null);
  };
  const handleDragEnd = () => { dragIdx.current = null; setOverIdx(null); };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 0 }}>
      {editMode && (
        <div style={{ display: "flex", gap: 10, marginBottom: 14 }}>
          <button onClick={onAdd} style={{ padding: "8px 16px", borderRadius: 8, border: "1px solid #7c3aed55", background: "rgba(124,58,237,0.12)", color: "#a78bfa", fontSize: 13, fontWeight: 600, cursor: "pointer", fontFamily: "inherit" }}>+ Ajouter une étape</button>
          <button onClick={onReset} style={{ padding: "8px 14px", borderRadius: 8, border: "1px solid #2e2e4e", background: "transparent", color: "#6b7280", fontSize: 12, cursor: "pointer", fontFamily: "inherit" }}>↺ Réinitialiser</button>
        </div>
      )}

      {steps.map((step, i) => (
        <React.Fragment key={step.id}>
          {/* Zone de dépôt au-dessus */}
          {editMode && overIdx === i && dragIdx.current !== null && dragIdx.current !== i && (
            <div style={{ height: 4, background: "#7c3aed", borderRadius: 4, margin: "2px 0", transition: "all 0.1s" }} />
          )}

          <div
            draggable={editMode}
            onDragStart={() => handleDragStart(i)}
            onDragOver={e => handleDragOver(e, i)}
            onDrop={e => handleDrop(e, i)}
            onDragEnd={handleDragEnd}
            style={{
              opacity: editMode && dragIdx.current === i ? 0.4 : 1,
              transition: "opacity 0.15s",
            }}
          >
            {editMode ? (
              <div style={{ background: "#111119", border: `1px solid ${step.color}55`, borderRadius: 12, padding: "14px 18px", cursor: "grab" }}>
                <div style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 10 }}>
                  {/* Poignée drag */}
                  <div title="Glisser pour déplacer" style={{ cursor: "grab", color: "#4b5563", fontSize: 16, lineHeight: 1, userSelect: "none", flexShrink: 0 }}>⠿</div>
                  {/* Numéro */}
                  <div style={{ width: 22, height: 22, borderRadius: "50%", background: step.color + "22", border: `1px solid ${step.color}44`, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 10, fontWeight: 700, color: step.color, flexShrink: 0 }}>{i + 1}</div>
                  {/* Emoji */}
                  <input value={step.icon} onChange={e => onUpdate(i, { ...step, icon: e.target.value })} onClick={e => e.stopPropagation()} style={{ width: 44, padding: "3px 6px", background: "#0d0d18", border: "1px solid #2e2e4e", borderRadius: 7, color: "#e4e4f0", fontSize: 18, textAlign: "center", outline: "none" }} />
                  {/* Label */}
                  <input value={step.label} onChange={e => onUpdate(i, { ...step, label: e.target.value })} onClick={e => e.stopPropagation()} placeholder="Titre" style={{ flex: 1, padding: "6px 10px", background: "#0d0d18", border: "1px solid #2e2e4e", borderRadius: 7, color: "#e4e4f0", fontSize: 14, fontWeight: 700, outline: "none" }} />
                  {/* Couleur */}
                  <select value={step.color} onChange={e => onUpdate(i, { ...step, color: e.target.value })} style={{ padding: "5px 8px", background: "#0d0d18", border: "1px solid #2e2e4e", borderRadius: 7, color: step.color, fontSize: 12, outline: "none", cursor: "pointer" }}>
                    {COLORS.map(c => <option key={c} value={c} style={{ color: c }}>{c}</option>)}
                  </select>
                  {/* Supprimer */}
                  <button onClick={e => { e.stopPropagation(); onDelete(i); }} style={{ padding: "4px 10px", background: "#3f0000", border: "1px solid #e11d4844", borderRadius: 6, color: "#ef4444", cursor: "pointer", fontSize: 12, fontWeight: 600, flexShrink: 0 }}>✕</button>
                </div>
                <input value={step.description} onChange={e => onUpdate(i, { ...step, description: e.target.value })} placeholder="Description" onClick={e => e.stopPropagation()} style={{ width: "100%", padding: "6px 12px", background: "#0d0d18", border: "1px solid #2e2e4e", borderRadius: 7, color: "#c9c9e8", fontSize: 13, outline: "none", boxSizing: "border-box", marginBottom: 6 }} />
                <input value={step.timingNote} onChange={e => onUpdate(i, { ...step, timingNote: e.target.value })} placeholder="Note de timing (ex: {warmupDelayMin}-{warmupDelayMax}s)" onClick={e => e.stopPropagation()} style={{ width: "100%", padding: "6px 12px", background: "#0d0d18", border: "1px solid #2e2e4e", borderRadius: 7, color: "#6b7280", fontSize: 12, outline: "none", boxSizing: "border-box" }} />
              </div>
            ) : (
              <div onClick={() => setOpenIdx(openIdx === i ? null : i)} style={{ background: "#111119", border: `1px solid ${step.color}44`, borderRadius: 10, padding: "12px 18px", cursor: "pointer", userSelect: "none" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                  <div style={{ width: 24, height: 24, borderRadius: "50%", background: step.color + "22", border: `1px solid ${step.color}44`, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 10, fontWeight: 700, color: step.color, flexShrink: 0 }}>{i + 1}</div>
                  <span style={{ fontSize: 18 }}>{step.icon}</span>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontWeight: 700, fontSize: 13, color: step.color }}>{step.label}</div>
                    {openIdx === i && <div style={{ color: "#9ca3af", fontSize: 12, marginTop: 4 }}>{step.description}</div>}
                  </div>
                  {step.timingNote && <span style={{ fontSize: 10, color: "#4b5563", background: "#0d0d18", border: "1px solid #1e1e2e", borderRadius: 5, padding: "2px 7px" }}>{step.timingNote}</span>}
                  <span style={{ color: "#4b5563", fontSize: 12 }}>{openIdx === i ? "▲" : "▼"}</span>
                </div>
              </div>
            )}
          </div>

          {/* Flèche entre étapes */}
          {i < steps.length - 1 && (
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", padding: "2px 0" }}>
              <div style={{ width: 1, height: 14, background: "#2e2e4e" }} />
              <div style={{ width: 0, height: 0, borderLeft: "5px solid transparent", borderRight: "5px solid transparent", borderTop: "6px solid #2e2e4e" }} />
            </div>
          )}
        </React.Fragment>
      ))}

      {editMode && (
        <button onClick={onAdd} style={{ width: "100%", marginTop: 14, padding: "10px", borderRadius: 8, border: "1px dashed #2e2e4e", background: "transparent", color: "#4b5563", fontSize: 13, cursor: "pointer", fontFamily: "inherit" }}>
          + Ajouter une étape en bas
        </button>
      )}
    </div>
  );
}

/* ── Page ── */
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
        if (raw) setConfig({
          ...raw,
          timings: { ...DEFAULT_TIMINGS, ...(raw.timings ?? {}) },
          flowSteps: raw.flowSteps ?? DEFAULT_FLOW_STEPS,
          phases: raw.phases ?? DEFAULT_PHASES,
        });
      })
      .catch(() => {});
  }, []);

  const update = (key: keyof BotDocsConfig, value: BotDocsConfig[keyof BotDocsConfig]) => {
    setConfig(c => c ? { ...c, [key]: value } : c);
  };

  const updateTiming = (key: keyof BotTiming, value: number) => {
    setConfig(c => c ? { ...c, timings: { ...c.timings, [key]: value } } : c);
  };

  const updateStep = (index: number, step: FlowStep) => {
    setConfig(c => {
      if (!c) return c;
      const steps = [...c.flowSteps];
      steps[index] = step;
      return { ...c, flowSteps: steps };
    });
  };

  const deleteStep = (index: number) => {
    setConfig(c => {
      if (!c) return c;
      const steps = [...c.flowSteps];
      steps.splice(index, 1);
      return { ...c, flowSteps: steps };
    });
  };

  const updatePhase = (i: number, p: BotPhase) => setConfig(c => { if (!c) return c; const phases = [...c.phases]; phases[i] = p; return { ...c, phases }; });
  const deletePhase = (i: number) => setConfig(c => { if (!c) return c; const phases = [...c.phases]; phases.splice(i, 1); return { ...c, phases }; });
  const addPhase = () => setConfig(c => { if (!c) return c; const n = c.phases.length + 1; return { ...c, phases: [...c.phases, { id: "p" + Date.now(), name: `Phase ${n} — Nouvelle phase`, icon: "⚡", prompt: "", advanceAfterMessages: 10 }] }; });

  const reorderSteps = (steps: FlowStep[]) => {
    setConfig(c => c ? { ...c, flowSteps: steps } : c);
  };

  const addStep = () => {
    const newStep: FlowStep = {
      id: "s" + Date.now(),
      icon: "⚡",
      label: "Nouvelle étape",
      description: "Description de cette étape",
      color: "#7c3aed",
      timingNote: "",
    };
    setConfig(c => c ? { ...c, flowSteps: [...c.flowSteps, newStep] } : c);
  };

  const resetFlow = () => {
    setConfig(c => c ? { ...c, flowSteps: DEFAULT_FLOW_STEPS } : c);
  };

  const handleSave = async () => {
    if (!config) return;
    setSaving(true);
    await fetch("/api/bot-docs", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(config) });
    setSaving(false); setSaved(true); setEditMode(false);
    setTimeout(() => setSaved(false), 3000);
  };

  const scrollTo = (id: string) => {
    setActiveNav(id);
    document.getElementById("sec-" + id)?.scrollIntoView({ behavior: "smooth" });
  };

  if (!config) return <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "60vh", color: "#6b7280", fontFamily: "system-ui,sans-serif" }}>Chargement…</div>;

  const inp = (val: string, onChange: (v: string) => void, placeholder?: string, mono?: boolean): React.CSSProperties => ({});

  return (
    <div style={{ minHeight: "100vh", background: "#0b0b12", color: "#e4e4f0", display: "flex", fontFamily: "system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif" }}>

      {/* Sidebar */}
      <nav style={{ width: 200, flexShrink: 0, position: "sticky", top: 0, height: "100vh", padding: "24px 0", borderRight: "1px solid #1a1a2a", background: "#0d0d1a", overflowY: "auto" }}>
        <div style={{ padding: "0 16px 16px", borderBottom: "1px solid #1a1a2a", marginBottom: 12 }}>
          <div style={{ fontSize: 10, fontWeight: 700, color: "#e11d48", letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: 2 }}>OnlyChat AI</div>
          <div style={{ fontSize: 13, fontWeight: 700, color: "#e4e4f0" }}>Config & Flux</div>
        </div>
        {NAV.map(n => (
          <button key={n.id} onClick={() => scrollTo(n.id)} style={{ width: "100%", textAlign: "left", padding: "9px 16px", background: activeNav === n.id ? "#7c3aed18" : "transparent", border: "none", borderLeft: activeNav === n.id ? "2px solid #7c3aed" : "2px solid transparent", color: activeNav === n.id ? "#a78bfa" : "#6b7280", fontSize: 13, cursor: "pointer", fontFamily: "inherit" }}>
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
            <p style={{ margin: 0, color: "#6b7280", fontSize: 14 }}>{editMode ? "Mode édition — modifie librement puis publie." : "Clique Modifier pour éditer les étapes, prompts et timings."}</p>
          </div>
          <div style={{ display: "flex", gap: 10, flexShrink: 0 }}>
            {editMode ? <>
              <button onClick={() => setEditMode(false)} style={{ padding: "9px 16px", borderRadius: 8, border: "1px solid #2e2e4e", background: "transparent", color: "#6b7280", fontSize: 13, cursor: "pointer", fontFamily: "inherit" }}>Annuler</button>
              <button onClick={handleSave} disabled={saving} style={{ padding: "9px 22px", borderRadius: 8, border: "none", background: saving ? "#4c1d95" : "linear-gradient(135deg,#7c3aed,#a855f7)", color: "#fff", fontSize: 13, fontWeight: 700, cursor: saving ? "not-allowed" : "pointer", fontFamily: "inherit" }}>
                {saving ? "Publication…" : "✓ Sauvegarder & Publier"}
              </button>
            </> : (
              <button onClick={() => setEditMode(true)} style={{ padding: "9px 20px", borderRadius: 8, border: "1px solid #7c3aed55", background: "rgba(124,58,237,0.1)", color: "#a78bfa", fontSize: 13, fontWeight: 600, cursor: "pointer", fontFamily: "inherit" }}>
                ✏️ Modifier
              </button>
            )}
          </div>
        </div>

        {saved && (
          <div style={{ position: "fixed", top: 20, right: 24, zIndex: 100, background: "#064e3b", border: "1px solid #10b981", borderRadius: 10, padding: "12px 20px", color: "#34d399", fontSize: 14, fontWeight: 600, boxShadow: "0 8px 24px rgba(0,0,0,0.4)" }}>
            ✓ Publié — le bot utilise maintenant ta nouvelle config
          </div>
        )}

        {/* ── FLUX ── */}
        <section id="sec-flow" style={{ scrollMarginTop: 80, marginBottom: 52 }}>
          <SectionTitle>Flux du bot — étapes</SectionTitle>
          {editMode && <p style={{ color: "#6b7280", fontSize: 12, marginBottom: 14, marginTop: -10 }}>⠿ Glisse les cartes pour les réordonner · Clique sur ✕ pour supprimer</p>}
          <FlowList
            steps={config.flowSteps}
            editMode={editMode}
            onReorder={reorderSteps}
            onUpdate={updateStep}
            onDelete={deleteStep}
            onAdd={addStep}
            onReset={resetFlow}
          />
        </section>

        {/* ── PHASES ── */}
        <section id="sec-phases" style={{ scrollMarginTop: 80, marginBottom: 52 }}>
          <SectionTitle>Phases de la relation</SectionTitle>
          <p style={{ color: "#6b7280", fontSize: 13, marginBottom: 20, marginTop: -10 }}>
            Chaque fan passe automatiquement d'une phase à l'autre. Le prompt de chaque phase est injecté dans l'IA pour adapter le comportement du bot.
          </p>
          {editMode && (
            <button onClick={addPhase} style={{ padding: "8px 16px", borderRadius: 8, border: "1px solid #7c3aed55", background: "rgba(124,58,237,0.12)", color: "#a78bfa", fontSize: 13, fontWeight: 600, cursor: "pointer", fontFamily: "inherit", marginBottom: 16 }}>
              + Ajouter une phase
            </button>
          )}
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            {config.phases.map((phase, i) => (
              <div key={phase.id} style={{ background: "#111119", border: "1px solid #7c3aed33", borderRadius: 14, padding: "20px 24px", position: "relative" }}>
                {/* Numéro de phase */}
                <div style={{ position: "absolute", top: -12, left: 20, background: "#7c3aed", color: "#fff", fontSize: 11, fontWeight: 800, padding: "2px 12px", borderRadius: 20, letterSpacing: "0.05em" }}>
                  {phase.icon} PHASE {i + 1}
                </div>
                <div style={{ display: "flex", gap: 12, alignItems: "center", marginBottom: 12, marginTop: 4 }}>
                  {editMode ? (
                    <>
                      <input value={phase.icon} onChange={e => updatePhase(i, { ...phase, icon: e.target.value })} style={{ width: 44, padding: "4px 6px", background: "#0d0d18", border: "1px solid #2e2e4e", borderRadius: 7, color: "#e4e4f0", fontSize: 18, textAlign: "center", outline: "none" }} />
                      <input value={phase.name} onChange={e => updatePhase(i, { ...phase, name: e.target.value })} style={{ flex: 1, padding: "7px 12px", background: "#0d0d18", border: "1px solid #2e2e4e", borderRadius: 8, color: "#e4e4f0", fontSize: 14, fontWeight: 700, outline: "none" }} />
                      <button onClick={() => deletePhase(i)} style={{ padding: "5px 12px", background: "#3f0000", border: "1px solid #e11d4844", borderRadius: 6, color: "#ef4444", cursor: "pointer", fontSize: 12, fontWeight: 600 }}>✕</button>
                    </>
                  ) : (
                    <div style={{ fontWeight: 700, fontSize: 15, color: "#e4e4f0" }}>{phase.name}</div>
                  )}
                </div>

                {/* Prompt */}
                <div style={{ marginBottom: 12 }}>
                  <div style={{ fontSize: 11, fontWeight: 700, color: "#6b7280", marginBottom: 6, textTransform: "uppercase" as const, letterSpacing: "0.06em" }}>Prompt IA pendant cette phase</div>
                  {editMode
                    ? <textarea value={phase.prompt} onChange={e => updatePhase(i, { ...phase, prompt: e.target.value })} rows={4} style={{ width: "100%", padding: "10px 14px", background: "#0d0d18", border: "1px solid #7c3aed55", borderRadius: 8, color: "#c9c9e8", fontSize: 13, lineHeight: 1.65, fontFamily: "ui-monospace,Menlo,monospace", resize: "vertical", outline: "none", boxSizing: "border-box" }} />
                    : <p style={{ margin: 0, padding: "10px 14px", background: "#0d0d18", border: "1px solid #1e1e2e", borderRadius: 8, color: "#9ca3af", fontSize: 13, lineHeight: 1.65, fontFamily: "ui-monospace,Menlo,monospace", whiteSpace: "pre-wrap" }}>{phase.prompt || <em style={{ color: "#4b5563" }}>Aucun prompt configuré</em>}</p>
                  }
                </div>

                {/* Avancement */}
                <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                  <span style={{ fontSize: 12, color: "#6b7280" }}>Passer à la phase suivante après</span>
                  {editMode
                    ? <input type="number" value={phase.advanceAfterMessages} min={0} max={500} onChange={e => updatePhase(i, { ...phase, advanceAfterMessages: Number(e.target.value) })} style={{ width: 64, padding: "5px 10px", background: "#0d0d18", border: "1px solid #7c3aed55", borderRadius: 7, color: "#a78bfa", fontSize: 14, fontWeight: 700, outline: "none", fontFamily: "ui-monospace,Menlo,monospace" }} />
                    : <span style={{ color: "#a78bfa", fontWeight: 800, fontSize: 16, fontFamily: "ui-monospace,Menlo,monospace" }}>{phase.advanceAfterMessages}</span>
                  }
                  <span style={{ fontSize: 12, color: "#6b7280" }}>messages du fan {phase.advanceAfterMessages === 0 ? <strong style={{ color: "#f59e0b" }}>(phase finale — pas d'avancement auto)</strong> : ""}</span>
                </div>

                {/* Flèche vers suivante */}
                {i < config.phases.length - 1 && !editMode && (
                  <div style={{ position: "absolute", bottom: -20, left: "50%", transform: "translateX(-50%)", display: "flex", flexDirection: "column", alignItems: "center", zIndex: 1 }}>
                    <div style={{ width: 1, height: 12, background: "#7c3aed55" }} />
                    <div style={{ width: 0, height: 0, borderLeft: "5px solid transparent", borderRight: "5px solid transparent", borderTop: "6px solid #7c3aed55" }} />
                  </div>
                )}
              </div>
            ))}
          </div>
        </section>

        {/* ── TIMINGS ── */}
        <section id="sec-timings" style={{ scrollMarginTop: 80, marginBottom: 52 }}>
          <SectionTitle>Timings & Vitesses</SectionTitle>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>

            <div style={{ background: "#111119", border: "1px solid #1e1e2e", borderRadius: 12, padding: "20px 24px" }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: "#f59e0b", marginBottom: 16, textTransform: "uppercase" as const, letterSpacing: "0.05em" }}>⏱ Timeout paiement</div>
              <NumInput label="Délai avant réduction / relance" unit="minutes" value={config.timings.paymentTimeoutMin} editMode={editMode} onChange={v => updateTiming("paymentTimeoutMin", v)} min={1} max={60} />
            </div>

            <div style={{ background: "#111119", border: "1px solid #1e1e2e", borderRadius: 12, padding: "20px 24px" }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: "#10b981", marginBottom: 16, textTransform: "uppercase" as const, letterSpacing: "0.05em" }}>🚀 Délai réponse IA</div>
              <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
                <NumInput label="Min" unit="sec" value={config.timings.responseDelayMin} editMode={editMode} onChange={v => updateTiming("responseDelayMin", v)} min={0} max={300} />
                <NumInput label="Max" unit="sec" value={config.timings.responseDelayMax} editMode={editMode} onChange={v => updateTiming("responseDelayMax", v)} min={0} max={300} />
                <NumInput label="Typing" unit="ms" value={config.timings.typingBeforeSendMs} editMode={editMode} onChange={v => updateTiming("typingBeforeSendMs", v)} min={0} max={30000} />
              </div>
            </div>

            <div style={{ background: "#111119", border: "1px solid #1e1e2e", borderRadius: 12, padding: "20px 24px" }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: "#7c3aed", marginBottom: 16, textTransform: "uppercase" as const, letterSpacing: "0.05em" }}>⏳ Délai warmup</div>
              <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
                <NumInput label="Min" unit="sec" value={config.timings.warmupDelayMin} editMode={editMode} onChange={v => updateTiming("warmupDelayMin", v)} min={0} max={300} />
                <NumInput label="Max" unit="sec" value={config.timings.warmupDelayMax} editMode={editMode} onChange={v => updateTiming("warmupDelayMax", v)} min={0} max={300} />
              </div>
            </div>

            <div style={{ background: "#111119", border: "1px solid #1e1e2e", borderRadius: 12, padding: "20px 24px" }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: "#6366f1", marginBottom: 16, textTransform: "uppercase" as const, letterSpacing: "0.05em" }}>💬 Inter-bulles</div>
              <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
                <NumInput label="Min" unit="sec" value={config.timings.interBubbleMin} editMode={editMode} onChange={v => updateTiming("interBubbleMin", v)} min={1} max={60} />
                <NumInput label="Max" unit="sec" value={config.timings.interBubbleMax} editMode={editMode} onChange={v => updateTiming("interBubbleMax", v)} min={1} max={60} />
              </div>
            </div>

            <div style={{ background: "#111119", border: "1px solid #1e1e2e", borderRadius: 12, padding: "20px 24px", gridColumn: "1 / -1" }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: "#e4e4f0", marginBottom: 6, textTransform: "uppercase" as const, letterSpacing: "0.05em" }}>📊 Vitesse script</div>
              <div style={{ color: "#4b5563", fontSize: 12, marginBottom: 16 }}>Nombre de messages du fan requis avant la prochaine étape script.</div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 16 }}>
                <div style={{ background: "#0d0d18", borderRadius: 10, padding: "16px 18px", border: "1px solid #10b98133" }}>
                  <div style={{ fontSize: 11, fontWeight: 700, color: "#10b981", marginBottom: 12 }}>⚡ RAPIDE</div>
                  <div style={{ display: "flex", gap: 12 }}><NumInput label="Min" value={config.timings.fastMin} editMode={editMode} onChange={v => updateTiming("fastMin", v)} min={1} max={20} /><NumInput label="Max" value={config.timings.fastMax} editMode={editMode} onChange={v => updateTiming("fastMax", v)} min={1} max={20} /></div>
                </div>
                <div style={{ background: "#0d0d18", borderRadius: 10, padding: "16px 18px", border: "1px solid #f59e0b33" }}>
                  <div style={{ fontSize: 11, fontWeight: 700, color: "#f59e0b", marginBottom: 12 }}>📍 NORMAL</div>
                  <div style={{ display: "flex", gap: 12 }}><NumInput label="Min" value={config.timings.normalMin} editMode={editMode} onChange={v => updateTiming("normalMin", v)} min={1} max={30} /><NumInput label="Max" value={config.timings.normalMax} editMode={editMode} onChange={v => updateTiming("normalMax", v)} min={1} max={30} /></div>
                </div>
                <div style={{ background: "#0d0d18", borderRadius: 10, padding: "16px 18px", border: "1px solid #e11d4833" }}>
                  <div style={{ fontSize: 11, fontWeight: 700, color: "#e11d48", marginBottom: 12 }}>🐢 LENT</div>
                  <div style={{ display: "flex", gap: 12 }}><NumInput label="Min" value={config.timings.slowMin} editMode={editMode} onChange={v => updateTiming("slowMin", v)} min={1} max={50} /><NumInput label="Max" value={config.timings.slowMax} editMode={editMode} onChange={v => updateTiming("slowMax", v)} min={1} max={50} /></div>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* ── PROMPTS ── */}
        <section id="sec-prompts" style={{ scrollMarginTop: 80, marginBottom: 52 }}>
          <SectionTitle>Prompts IA</SectionTitle>
          <PromptEditor label="Warmup" color="#7c3aed" hint="Envoyé une seule fois avant le 1er script" value={config.warmupPrompt} editMode={editMode} onChange={v => update("warmupPrompt", v)} />
          <PromptEditor label="Inter-étape" color="#6366f1" hint="{remaining} = messages restants · {teaser} = indice" value={config.interStepContext} editMode={editMode} onChange={v => update("interStepContext", v)} />
          <PromptEditor label="Attente paiement" color="#e11d48" hint="Remplace l'inter-étape quand waitingForPayment = true" value={config.waitingPaymentContext} editMode={editMode} onChange={v => update("waitingPaymentContext", v)} />
          <PromptEditor label="Réduction" color="#f59e0b" hint="{reason} = raison de l'hésitation" value={config.discountPrompt} editMode={editMode} onChange={v => update("discountPrompt", v)} />
          <PromptEditor label="Relance vente" color="#e11d48" hint="Après timeout paiement" value={config.salePushPrompt} editMode={editMode} onChange={v => update("salePushPrompt", v)} />
          <PromptEditor label="Règles de réponse" color="#10b981" hint="Injecté à la fin de chaque réponse IA" value={config.responseRules} editMode={editMode} onChange={v => update("responseRules", v)} />
        </section>

        {/* ── KEYWORDS ── */}
        <section id="sec-keywords" style={{ scrollMarginTop: 80, marginBottom: 52 }}>
          <SectionTitle>Mots-clés déclencheurs</SectionTitle>
          <KeywordEditor label="Mots sexy" color="#e11d48" hint="Court-circuite le cooldown" value={config.sexyKeywords} editMode={editMode} onChange={v => update("sexyKeywords", v)} />
          <KeywordEditor label="Mots réduction" color="#f59e0b" hint="Déclenche la réduction sans attendre le timeout" value={config.discountKeywords} editMode={editMode} onChange={v => update("discountKeywords", v)} />
          <KeywordEditor label="Mots paiement" color="#10b981" hint="Fallback si webhook manqué" value={config.paidKeywords} editMode={editMode} onChange={v => update("paidKeywords", v)} />
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
