"use client";
import { useState, useEffect, useRef } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  ChevronLeft, Plus, Trash2, GripVertical, Upload, X,
  ChevronDown, ChevronUp, Save, RefreshCw, Star, Image as ImageIcon
} from "lucide-react";
import type { Script, ScriptStep, PostMediaMessage } from "@/lib/scripts-store";

/* ── helpers ── */
function Toggle({ value, onChange, label }: { value: boolean; onChange: (v: boolean) => void; label?: string }) {
  return (
    <label className="flex items-center gap-2 cursor-pointer select-none">
      <button onClick={() => onChange(!value)}
        className="relative w-10 h-5 rounded-full transition-all flex-shrink-0"
        style={{ background: value ? "#e11d48" : "#374151" }}>
        <div className="absolute top-0.5 w-4 h-4 rounded-full bg-white transition-all shadow"
          style={{ left: value ? "calc(100% - 18px)" : "2px" }} />
      </button>
      {label && <span className="text-sm" style={{ color: "#9ca3af" }}>{label}</span>}
    </label>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <label className="block text-xs font-medium" style={{ color: "#6b7280" }}>{label}</label>
      {children}
    </div>
  );
}

function StepCard({
  step, index, total, onChange, onDelete, onMoveUp, onMoveDown
}: {
  step: ScriptStep; index: number; total: number;
  onChange: (s: ScriptStep) => void;
  onDelete: () => void;
  onMoveUp: () => void;
  onMoveDown: () => void;
}) {
  const [open, setOpen] = useState(true);
  const fileRef = useRef<HTMLInputElement>(null);

  const set = <K extends keyof ScriptStep>(k: K, v: ScriptStep[K]) => onChange({ ...step, [k]: v });

  const addPostMsg = () => {
    const pm: PostMediaMessage = { id: Date.now().toString(), message: "", delaySeconds: 60, mediaUrl: undefined };
    set("postMediaMessages", [...step.postMediaMessages, pm]);
  };

  const updatePm = (pmId: string, patch: Partial<PostMediaMessage>) => {
    set("postMediaMessages", step.postMediaMessages.map(p => p.id === pmId ? { ...p, ...patch } : p));
  };

  const removePm = (pmId: string) => {
    set("postMediaMessages", step.postMediaMessages.filter(p => p.id !== pmId));
  };

  return (
    <div className="rounded-xl border overflow-hidden" style={{ borderColor: "#1e1e2e", background: "#0f0f1a" }}>
      {/* Header */}
      <div className="flex items-center gap-3 px-4 py-3 cursor-pointer select-none"
        style={{ borderBottom: open ? "1px solid #1e1e2e" : "none" }}
        onClick={() => setOpen(o => !o)}>
        <GripVertical size={14} style={{ color: "#4b5563" }} className="cursor-grab" />
        <div className="flex items-center gap-2 flex-1 min-w-0">
          <span className="w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0"
            style={{ background: "#e11d48", color: "#fff" }}>{index + 1}</span>
          <span className="text-sm font-medium truncate" style={{ color: "#d1d5db" }}>
            {step.message ? step.message.slice(0, 50) + (step.message.length > 50 ? "…" : "") : `Étape ${index + 1}`}
          </span>
          {step.priceStars > 0 && (
            <span className="flex items-center gap-1 text-xs px-2 py-0.5 rounded-full flex-shrink-0"
              style={{ background: "rgba(245,158,11,0.15)", color: "#f59e0b" }}>
              <Star size={10} fill="#f59e0b" /> {step.priceStars} Stars
            </span>
          )}
        </div>
        <div className="flex items-center gap-1">
          <button onClick={e => { e.stopPropagation(); onMoveUp(); }} disabled={index === 0}
            className="p-1 rounded hover:bg-white/5 disabled:opacity-30">
            <ChevronUp size={13} style={{ color: "#6b7280" }} />
          </button>
          <button onClick={e => { e.stopPropagation(); onMoveDown(); }} disabled={index === total - 1}
            className="p-1 rounded hover:bg-white/5 disabled:opacity-30">
            <ChevronDown size={13} style={{ color: "#6b7280" }} />
          </button>
          <button onClick={e => { e.stopPropagation(); onDelete(); }}
            className="p-1 rounded hover:bg-white/5 ml-1" style={{ color: "#e11d48" }}>
            <Trash2 size={13} />
          </button>
          {open ? <ChevronUp size={14} style={{ color: "#4b5563" }} /> : <ChevronDown size={14} style={{ color: "#4b5563" }} />}
        </div>
      </div>

      {open && (
        <div className="p-4 space-y-4">
          {/* Message */}
          <Field label="Message">
            <textarea value={step.message} onChange={e => set("message", e.target.value)}
              rows={3} placeholder="Texte du message envoyé au fan..."
              className="w-full px-3 py-2.5 rounded-lg text-sm outline-none resize-none"
              style={{ background: "#0a0a0f", border: "1px solid #1e1e2e", color: "#d1d5db" }} />
          </Field>

          {/* Media */}
          <Field label="Médias">
            <div className="flex flex-wrap gap-2">
              {step.mediaUrls.map((url, i) => (
                <div key={i} className="relative group w-20 h-20 rounded-lg overflow-hidden border"
                  style={{ borderColor: "#1e1e2e" }}>
                  <img src={url} alt="" className="w-full h-full object-cover" />
                  <button onClick={() => set("mediaUrls", step.mediaUrls.filter((_, j) => j !== i))}
                    className="absolute top-1 right-1 w-5 h-5 rounded-full flex items-center justify-center opacity-0 group-hover:opacity-100 transition-all"
                    style={{ background: "#e11d48" }}>
                    <X size={10} color="#fff" />
                  </button>
                </div>
              ))}
              <button onClick={() => fileRef.current?.click()}
                className="w-20 h-20 rounded-lg border-2 border-dashed flex flex-col items-center justify-center gap-1 hover:bg-white/5 transition-all"
                style={{ borderColor: "#1e1e2e" }}>
                <Upload size={14} style={{ color: "#4b5563" }} />
                <span className="text-xs" style={{ color: "#4b5563" }}>Upload</span>
              </button>
              <input ref={fileRef} type="file" accept="image/*,video/*" multiple className="hidden"
                onChange={e => {
                  const files = Array.from(e.target.files ?? []);
                  const urls = files.map(f => URL.createObjectURL(f));
                  set("mediaUrls", [...step.mediaUrls, ...urls]);
                }} />
            </div>
          </Field>

          {/* Row: Stars + Discount */}
          <div className="grid grid-cols-2 gap-3">
            <Field label="Prix en Stars (0 = gratuit)">
              <input type="number" min={0} value={step.priceStars}
                onChange={e => set("priceStars", Number(e.target.value))}
                className="w-full px-3 py-2 rounded-lg text-sm outline-none"
                style={{ background: "#0a0a0f", border: "1px solid #1e1e2e", color: "#d1d5db" }} />
            </Field>
            <Field label="Prix réduit (si activé)">
              <div className="flex items-center gap-2">
                <input type="number" min={0} value={step.discountedPriceStars}
                  disabled={!step.discountEnabled}
                  onChange={e => set("discountedPriceStars", Number(e.target.value))}
                  className="flex-1 px-3 py-2 rounded-lg text-sm outline-none disabled:opacity-40"
                  style={{ background: "#0a0a0f", border: "1px solid #1e1e2e", color: "#d1d5db" }} />
                <Toggle value={step.discountEnabled} onChange={v => set("discountEnabled", v)} />
              </div>
            </Field>
          </div>

          {/* Pre-media teaser */}
          <Field label="Teaser avant média (envoyé avant le média payant)">
            <textarea value={step.preMediaTeaser} onChange={e => set("preMediaTeaser", e.target.value)}
              rows={2} placeholder="Ex: J'ai quelque chose de spécial pour toi… 🔥"
              className="w-full px-3 py-2.5 rounded-lg text-sm outline-none resize-none"
              style={{ background: "#0a0a0f", border: "1px solid #1e1e2e", color: "#d1d5db" }} />
          </Field>

          {/* Options row */}
          <div className="flex flex-wrap gap-4">
            <Toggle value={step.waitBeforeMedia} onChange={v => set("waitBeforeMedia", v)} label="Attendre avant le média" />
            <Toggle value={step.skipFollowupIfPaid} onChange={v => set("skipFollowupIfPaid", v)} label="Skip follow-up si déjà payé" />
          </div>

          {/* Messages between steps */}
          <Field label="Vitesse d'envoi des messages entre étapes">
            <div className="flex gap-2">
              {(["fast", "normal", "slow"] as const).map(v => (
                <button key={v} onClick={() => set("messagesBetweenSteps", v)}
                  className="flex-1 py-2 rounded-lg text-xs font-medium border transition-all"
                  style={{
                    borderColor: step.messagesBetweenSteps === v ? "#e11d48" : "#1e1e2e",
                    background: step.messagesBetweenSteps === v ? "rgba(225,29,72,0.1)" : "transparent",
                    color: step.messagesBetweenSteps === v ? "#e11d48" : "#6b7280",
                  }}>
                  {v === "fast" ? "Rapide (1-2s)" : v === "normal" ? "Normal (4-5s)" : "Lent (8-10s)"}
                </button>
              ))}
            </div>
          </Field>

          {/* Post-media messages */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="text-xs font-medium" style={{ color: "#6b7280" }}>Messages post-média</label>
              <button onClick={addPostMsg} className="flex items-center gap-1 text-xs px-2.5 py-1 rounded-lg"
                style={{ background: "rgba(225,29,72,0.1)", color: "#e11d48", border: "1px solid rgba(225,29,72,0.2)" }}>
                <Plus size={11} /> Ajouter
              </button>
            </div>
            <div className="space-y-2">
              {step.postMediaMessages.map(pm => (
                <div key={pm.id} className="flex items-start gap-2 p-3 rounded-lg border"
                  style={{ borderColor: "#1e1e2e", background: "#0a0a0f" }}>
                  <div className="flex-1 space-y-2">
                    <input value={pm.message} onChange={e => updatePm(pm.id, { message: e.target.value })}
                      placeholder="Message de suivi..."
                      className="w-full px-3 py-2 rounded-lg text-sm outline-none"
                      style={{ background: "#111118", border: "1px solid #1e1e2e", color: "#d1d5db" }} />
                    <div className="flex items-center gap-2">
                      <span className="text-xs" style={{ color: "#6b7280" }}>Délai:</span>
                      <input type="number" min={0} value={pm.delaySeconds}
                        onChange={e => updatePm(pm.id, { delaySeconds: Number(e.target.value) })}
                        className="w-24 px-2 py-1 rounded text-xs outline-none"
                        style={{ background: "#111118", border: "1px solid #1e1e2e", color: "#d1d5db" }} />
                      <span className="text-xs" style={{ color: "#6b7280" }}>secondes</span>
                    </div>
                  </div>
                  <button onClick={() => removePm(pm.id)} className="mt-1 flex-shrink-0" style={{ color: "#e11d48" }}>
                    <X size={13} />
                  </button>
                </div>
              ))}
              {step.postMediaMessages.length === 0 && (
                <p className="text-xs py-3 text-center" style={{ color: "#374151" }}>Aucun message post-média</p>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ── Main page ── */
export default function ScriptEditorPage() {
  const { id, scriptId } = useParams<{ id: string; scriptId: string }>();
  const router = useRouter();
  const [script, setScript] = useState<Script | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    (async () => {
      const res = await fetch(`/api/creators/${id}/scripts`);
      const d = await res.json();
      const found = (d.scripts as Script[]).find(s => s.id === scriptId) ?? null;
      setScript(found);
      setLoading(false);
    })();
  }, [id, scriptId]);

  const save = async () => {
    if (!script) return;
    setSaving(true);
    await fetch(`/api/creators/${id}/scripts`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ script }),
    });
    setSaving(false);
  };

  const setS = (patch: Partial<Script>) => setScript(s => s ? { ...s, ...patch } : s);

  const addStep = () => {
    if (!script) return;
    const newStep = {
      id: Date.now().toString() + Math.random().toString(36).slice(2, 5),
      order: script.steps.length + 1,
      message: "",
      mediaUrls: [],
      waitBeforeMedia: false,
      priceStars: 0,
      discountEnabled: false,
      discountedPriceStars: 0,
      messagesBetweenSteps: "normal" as const,
      skipFollowupIfPaid: false,
      preMediaTeaser: "",
      postMediaMessages: [],
    };
    setS({ steps: [...script.steps, newStep] });
  };

  const updateStep = (idx: number, s: ScriptStep) => {
    if (!script) return;
    const steps = [...script.steps];
    steps[idx] = s;
    setS({ steps });
  };

  const deleteStep = (idx: number) => {
    if (!script) return;
    setS({ steps: script.steps.filter((_, i) => i !== idx) });
  };

  const moveStep = (idx: number, dir: -1 | 1) => {
    if (!script) return;
    const steps = [...script.steps];
    const target = idx + dir;
    if (target < 0 || target >= steps.length) return;
    [steps[idx], steps[target]] = [steps[target], steps[idx]];
    setS({ steps: steps.map((s, i) => ({ ...s, order: i + 1 })) });
  };

  if (loading) return (
    <div className="flex items-center justify-center py-20" style={{ color: "#4b5563" }}>
      <RefreshCw size={18} className="animate-spin mr-2" /> Chargement...
    </div>
  );

  if (!script) return (
    <div className="p-8 text-center text-sm" style={{ color: "#4b5563" }}>Script introuvable.</div>
  );

  return (
    <div className="max-w-3xl mx-auto p-6 space-y-6" style={{ color: "#fff" }}>
      {/* Back + title */}
      <div className="flex items-center gap-3">
        <button onClick={() => router.push(`/dashboard/creators/${id}/scripts`)}
          className="p-1.5 rounded-lg hover:bg-white/5 transition-all" style={{ color: "#9ca3af" }}>
          <ChevronLeft size={18} />
        </button>
        <input value={script.name} onChange={e => setS({ name: e.target.value.toUpperCase() })}
          className="text-xl font-bold bg-transparent outline-none border-b border-transparent hover:border-white/10 focus:border-white/20 transition-all uppercase"
          style={{ color: "#fff" }} />
        <div className="flex-1" />
        <button onClick={save} disabled={saving}
          className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium disabled:opacity-60"
          style={{ background: "#e11d48", color: "#fff" }}>
          {saving ? <RefreshCw size={13} className="animate-spin" /> : <Save size={13} />}
          {saving ? "Sauvegarde…" : "Sauvegarder"}
        </button>
      </div>

      {/* Description */}
      <textarea value={script.description} onChange={e => setS({ description: e.target.value })}
        rows={2} placeholder="Description du script (optionnel)…"
        className="w-full px-4 py-3 rounded-xl text-sm outline-none resize-none"
        style={{ background: "#111118", border: "1px solid #1e1e2e", color: "#9ca3af" }} />

      {/* Global settings */}
      <div className="rounded-xl border p-5 space-y-5" style={{ borderColor: "#1e1e2e", background: "#0f0f1a" }}>
        <h3 className="text-sm font-semibold" style={{ color: "#d1d5db" }}>Paramètres généraux</h3>

        <div className="grid grid-cols-2 gap-4">
          <Toggle value={script.active} onChange={v => setS({ active: v })} label="Script actif" />
          <Toggle value={script.first} onChange={v => setS({ first: v })} label="Script prioritaire (⭐)" />
          <Toggle value={script.strictCooldown} onChange={v => setS({ strictCooldown: v })} label="Cooldown strict" />
        </div>

        <div className="grid grid-cols-2 gap-4">
          <Field label={`Timeout inactivité: ${script.inactivityTimeoutHours}h`}>
            <input type="range" min={1} max={72} value={script.inactivityTimeoutHours}
              onChange={e => setS({ inactivityTimeoutHours: Number(e.target.value) })}
              className="w-full accent-rose-600" />
            <div className="flex justify-between text-xs mt-1" style={{ color: "#4b5563" }}>
              <span>1h</span><span>72h</span>
            </div>
          </Field>
          <Field label="Groupe (tag optionnel)">
            <input value={script.group ?? ""} onChange={e => setS({ group: e.target.value || null })}
              placeholder="Ex: welcome, ppv, vip…"
              className="w-full px-3 py-2 rounded-lg text-sm outline-none"
              style={{ background: "#0a0a0f", border: "1px solid #1e1e2e", color: "#d1d5db" }} />
          </Field>
        </div>
      </div>

      {/* Steps */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold" style={{ color: "#d1d5db" }}>
            Étapes du script ({script.steps.length})
          </h3>
          <button onClick={addStep}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm"
            style={{ background: "rgba(225,29,72,0.1)", color: "#e11d48", border: "1px solid rgba(225,29,72,0.2)" }}>
            <Plus size={13} /> Ajouter une étape
          </button>
        </div>

        {script.steps.length === 0 ? (
          <div className="rounded-xl border border-dashed py-12 text-center text-sm"
            style={{ borderColor: "#1e1e2e", color: "#4b5563" }}>
            Aucune étape — clique &quot;Ajouter une étape&quot; pour commencer
          </div>
        ) : (
          script.steps.map((step, idx) => (
            <StepCard key={step.id} step={step} index={idx} total={script.steps.length}
              onChange={s => updateStep(idx, s)}
              onDelete={() => deleteStep(idx)}
              onMoveUp={() => moveStep(idx, -1)}
              onMoveDown={() => moveStep(idx, 1)} />
          ))
        )}
      </div>

      {/* Save bottom */}
      <div className="flex justify-end pt-2 pb-8">
        <button onClick={save} disabled={saving}
          className="flex items-center gap-2 px-6 py-2.5 rounded-xl text-sm font-medium disabled:opacity-60"
          style={{ background: "#e11d48", color: "#fff" }}>
          {saving ? <RefreshCw size={13} className="animate-spin" /> : <Save size={13} />}
          {saving ? "Sauvegarde…" : "Sauvegarder les changements"}
        </button>
      </div>
    </div>
  );
}
