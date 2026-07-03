"use client";
import { useState, useEffect, useRef } from "react";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, Plus, Trash2, GripVertical, ChevronUp, ChevronDown, RefreshCw, X } from "lucide-react";
import type { Script, ScriptStep, PostMediaMessage } from "@/lib/scripts-store";

function Toggle({ value, onChange }: { value: boolean; onChange: (v: boolean) => void }) {
  return (
    <button type="button" onClick={() => onChange(!value)}
      className="relative w-11 h-6 rounded-full transition-all flex-shrink-0"
      style={{ background: value ? "#e11d48" : "#374151" }}>
      <div className="absolute top-0.5 w-5 h-5 rounded-full bg-white transition-all shadow"
        style={{ left: value ? "calc(100% - 22px)" : "2px" }} />
    </button>
  );
}

function MediaUpload({ urls, onAdd, onRemove, folder }: {
  urls: string[]; onAdd: (url: string) => void; onRemove: (url: string) => void; folder: string;
}) {
  const { id } = useParams<{ id: string }>();
  const ref = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState("");

  const upload = async (files: FileList) => {
    setUploading(true);
    setUploadError("");
    for (const file of Array.from(files)) {
      try {
        const form = new FormData();
        form.append("file", file);
        const res = await fetch(`/api/creators/${id}/media?folder=${encodeURIComponent(folder)}`, { method: "POST", body: form });
        const d = await res.json();
        if (d.url) onAdd(d.url);
        else setUploadError(d.error ?? `Erreur upload (${res.status})`);
      } catch (e) {
        setUploadError("Erreur réseau lors de l'upload");
      }
    }
    setUploading(false);
  };

  return (
    <div className="flex flex-col gap-2 w-full">
      <div className="flex flex-wrap gap-2">
        {urls.map(url => (
          <div key={url} className="relative group w-20 h-20 rounded-lg overflow-hidden border flex-shrink-0"
            style={{ borderColor: "#1e1e2e" }}>
            {/\.(mp4|mov|webm)/i.test(url)
              ? <video src={url} className="w-full h-full object-cover" />
              : <img src={url} alt="" className="w-full h-full object-cover" onError={e => { (e.target as HTMLImageElement).src = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='80' height='80'%3E%3Crect fill='%231e1e2e' width='80' height='80'/%3E%3Ctext x='50%25' y='50%25' dominant-baseline='middle' text-anchor='middle' fill='%236b7280' font-size='10'%3E?%3C/text%3E%3C/svg%3E"; }} />}
            <button type="button" onClick={() => onRemove(url)}
              className="absolute top-0.5 right-0.5 w-5 h-5 rounded-full flex items-center justify-center opacity-0 group-hover:opacity-100"
              style={{ background: "#e11d48" }}>
              <X size={10} color="#fff" />
            </button>
          </div>
        ))}
        <button type="button" onClick={() => ref.current?.click()} disabled={uploading}
          className="w-20 h-20 rounded-lg border-2 border-dashed flex flex-col items-center justify-center gap-1 hover:border-red-500/40 transition-all disabled:opacity-50"
          style={{ borderColor: "#374151" }}>
          {uploading
            ? <RefreshCw size={14} className="animate-spin" style={{ color: "#6b7280" }} />
            : <><Plus size={18} style={{ color: "#6b7280" }} /><span className="text-xs" style={{ color: "#4b5563" }}>Upload</span></>}
        </button>
      </div>
      {uploadError && <p className="text-xs" style={{ color: "#f87171" }}>{uploadError}</p>}
      <input ref={ref} type="file" accept="image/*,video/*" multiple className="hidden"
        onChange={e => e.target.files && upload(e.target.files)} />
    </div>
  );
}

function StepCard({ step, index, total, scriptId, onChange, onDelete, onMoveUp, onMoveDown }: {
  step: ScriptStep; index: number; total: number; scriptId: string;
  onChange: (s: ScriptStep) => void; onDelete: () => void;
  onMoveUp: () => void; onMoveDown: () => void;
}) {
  const set = <K extends keyof ScriptStep>(k: K, v: ScriptStep[K]) => onChange({ ...step, [k]: v });

  const addPostMsg = () => {
    const pm: PostMediaMessage = { id: Date.now().toString(), message: "", delaySeconds: 5 };
    set("postMediaMessages", [...step.postMediaMessages, pm]);
  };
  const updatePm = (pmId: string, patch: Partial<PostMediaMessage>) =>
    set("postMediaMessages", step.postMediaMessages.map(p => p.id === pmId ? { ...p, ...patch } : p));
  const removePm = (pmId: string) =>
    set("postMediaMessages", step.postMediaMessages.filter(p => p.id !== pmId));

  return (
    <div className="rounded-xl border overflow-hidden" style={{ borderColor: "#2a2a3e", background: "#0d0d1a" }}>
      {/* Step header */}
      <div className="flex items-center gap-2 px-4 py-2 border-b" style={{ borderColor: "#1e1e2e", background: "#111118" }}>
        <GripVertical size={14} style={{ color: "#4b5563" }} className="cursor-grab" />
        <span className="w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0"
          style={{ background: "#e11d48", color: "#fff" }}>{index + 1}</span>
        <span className="text-sm font-semibold flex-1" style={{ color: "#d1d5db" }}>Step {index + 1}</span>
        <div className="flex items-center gap-1">
          <button onClick={onMoveUp} disabled={index === 0} className="p-1 rounded hover:bg-white/5 disabled:opacity-30"><ChevronUp size={13} style={{ color: "#6b7280" }} /></button>
          <button onClick={onMoveDown} disabled={index === total - 1} className="p-1 rounded hover:bg-white/5 disabled:opacity-30"><ChevronDown size={13} style={{ color: "#6b7280" }} /></button>
          <button onClick={onDelete} className="p-1 rounded hover:bg-red-500/10" style={{ color: "#e11d48" }}><X size={13} /></button>
        </div>
      </div>

      <div className="p-4 space-y-4">
        {/* Message + Media row */}
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-xs font-medium mb-1.5" style={{ color: "#9ca3af" }}>Message</label>
            <textarea value={step.message} onChange={e => set("message", e.target.value)}
              rows={4} placeholder="Tu préfères lequel? 🙈"
              className="w-full px-3 py-2.5 rounded-lg text-sm outline-none resize-none"
              style={{ background: "#0a0a0f", border: "1px solid #1e1e2e", color: "#d1d5db" }} />
          </div>
          <div>
            <label className="block text-xs font-medium mb-1.5" style={{ color: "#9ca3af" }}>Medias</label>
            <div className="rounded-lg p-2 min-h-[100px] flex flex-wrap gap-2 items-start"
              style={{ background: "#0a0a0f", border: "1px solid #1e1e2e" }}>
              <MediaUpload urls={step.mediaUrls} folder={scriptId}
                onAdd={url => set("mediaUrls", [...step.mediaUrls, url])}
                onRemove={url => set("mediaUrls", step.mediaUrls.filter(u => u !== url))} />
            </div>
          </div>
        </div>

        {/* Wait before sending */}
        <div className="flex items-center justify-between p-3 rounded-lg" style={{ background: "#111118" }}>
          <div>
            <p className="text-sm font-medium" style={{ color: "#d1d5db" }}>Wait before sending video/audio</p>
            <p className="text-xs mt-0.5" style={{ color: "#6b7280" }}>Only available for steps with video or audio media.</p>
          </div>
          <Toggle value={step.waitBeforeMedia} onChange={v => set("waitBeforeMedia", v)} />
        </div>

        {/* Price + Discount */}
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-xs font-medium mb-1.5" style={{ color: "#9ca3af" }}>Price (+ Stars)</label>
            <input type="number" min={0} value={step.priceStars} onChange={e => set("priceStars", Number(e.target.value))}
              className="w-full px-3 py-2 rounded-lg text-sm outline-none"
              style={{ background: "#0a0a0f", border: "1px solid #1e1e2e", color: "#d1d5db" }} />
          </div>
          <div>
            <div className="flex items-center gap-2 mb-1.5">
              <label className="text-xs font-medium" style={{ color: "#9ca3af" }}>Discounted Price (+ Stars)</label>
              <div className="flex items-center gap-1.5 ml-auto">
                <span className="text-xs" style={{ color: "#6b7280" }}>Enable discount</span>
                <Toggle value={step.discountEnabled} onChange={v => set("discountEnabled", v)} />
              </div>
            </div>
            <input type="number" min={0} value={step.discountedPriceStars} disabled={!step.discountEnabled}
              onChange={e => set("discountedPriceStars", Number(e.target.value))}
              className="w-full px-3 py-2 rounded-lg text-sm outline-none disabled:opacity-40"
              style={{ background: "#0a0a0f", border: "1px solid #1e1e2e", color: "#d1d5db" }} />
          </div>
        </div>

        {/* Messages between steps */}
        <div className="grid grid-cols-2 gap-4 items-start">
          <div>
            <label className="block text-xs font-medium mb-1.5" style={{ color: "#9ca3af" }}>Approx. Messages Between This Step And The Next One</label>
            <select value={step.messagesBetweenSteps} onChange={e => set("messagesBetweenSteps", e.target.value as "fast" | "normal" | "slow")}
              className="w-full px-3 py-2 rounded-lg text-sm outline-none"
              style={{ background: "#0a0a0f", border: "1px solid #1e1e2e", color: "#d1d5db" }}>
              <option value="fast">Fast (1–2)</option>
              <option value="normal">Normal (4–5)</option>
              <option value="slow">Slow (8–10)</option>
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium mb-1.5" style={{ color: "#9ca3af" }}>Skip media followup if paid (send next step)</label>
            <label className="flex items-center gap-2 mt-2 cursor-pointer">
              <input type="checkbox" checked={step.skipFollowupIfPaid} onChange={e => set("skipFollowupIfPaid", e.target.checked)}
                className="w-4 h-4 rounded accent-red-600" />
              <span className="text-xs" style={{ color: "#6b7280" }}>Available only for paid steps</span>
            </label>
          </div>
        </div>

        {/* Pre-media teaser */}
        <div>
          <label className="block text-xs font-medium mb-1.5" style={{ color: "#9ca3af" }}>
            Pre-Media Teaser <span style={{ color: "#4b5563" }}>(Optional)</span>
          </label>
          <textarea value={step.preMediaTeaser} onChange={e => set("preMediaTeaser", e.target.value)}
            rows={2} placeholder="Add video or audio media to enable pre-media teaser"
            className="w-full px-3 py-2 rounded-lg text-sm outline-none resize-none"
            style={{ background: "#0a0a0f", border: "1px solid #1e1e2e", color: "#d1d5db" }} />
          <p className="text-xs mt-1" style={{ color: "#4b5563" }}>Pre-media teaser is only available for steps with video or audio media.</p>
        </div>

        {/* Post-media messages */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <div>
              <label className="text-xs font-medium" style={{ color: "#9ca3af" }}>
                Post-Media Messages <span style={{ color: "#4b5563" }}>(Optional)</span>
              </label>
              <p className="text-xs mt-0.5" style={{ color: "#4b5563" }}>Add multiple follow up messages after the main media, each with its own delay and optional media.</p>
            </div>
            <button onClick={addPostMsg}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs border"
              style={{ borderColor: "#1e1e2e", color: "#9ca3af" }}>
              <Plus size={11} /> Add Post-Media Message
            </button>
          </div>
          {step.postMediaMessages.length > 0 && (
            <div className="rounded-lg border overflow-hidden" style={{ borderColor: "#1e1e2e" }}>
              <div className="grid text-xs px-3 py-2 border-b" style={{ gridTemplateColumns: "1fr 160px 80px 32px", borderColor: "#1e1e2e", color: "#6b7280" }}>
                <span>Message Post Media</span><span>Delay (in seconds)</span><span>Medias</span><span></span>
              </div>
              {step.postMediaMessages.map(pm => (
                <div key={pm.id} className="grid items-center px-3 py-2 gap-2 border-b last:border-b-0"
                  style={{ gridTemplateColumns: "1fr 160px 80px 32px", borderColor: "#111118" }}>
                  <input value={pm.message} onChange={e => updatePm(pm.id, { message: e.target.value })}
                    placeholder="Jsp lequel mettre pour ce soir"
                    className="px-2 py-1.5 rounded text-xs outline-none"
                    style={{ background: "#0a0a0f", border: "1px solid #1e1e2e", color: "#d1d5db" }} />
                  <div>
                    <input type="number" min={0} value={pm.delaySeconds}
                      onChange={e => updatePm(pm.id, { delaySeconds: Number(e.target.value) })}
                      className="w-full px-2 py-1.5 rounded text-xs outline-none"
                      style={{ background: "#0a0a0f", border: "1px solid #1e1e2e", color: "#d1d5db" }} />
                    <p className="text-xs mt-0.5" style={{ color: "#4b5563" }}>Relative to previous</p>
                  </div>
                  <button onClick={() => { /* media upload for pm */ }}
                    className="w-8 h-8 rounded border-2 border-dashed flex items-center justify-center"
                    style={{ borderColor: "#374151" }}>
                    <Plus size={12} style={{ color: "#6b7280" }} />
                  </button>
                  <button onClick={() => removePm(pm.id)} style={{ color: "#e11d48" }}><Trash2 size={13} /></button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function ScriptEditorPage() {
  const { id, scriptId } = useParams<{ id: string; scriptId: string }>();
  const router = useRouter();
  const [script, setScript] = useState<Script | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    fetch(`/api/creators/${id}/scripts`).then(r => r.json()).then(d => {
      setScript((d.scripts as Script[]).find(s => s.id === scriptId) ?? null);
      setLoading(false);
    });
  }, [id, scriptId]);

  const setS = (patch: Partial<Script>) => setScript(s => s ? { ...s, ...patch } : s);

  const save = async () => {
    if (!script) return;
    setSaving(true);
    await fetch(`/api/creators/${id}/scripts`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ script }),
    });
    setSaving(false);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  const addStep = () => {
    if (!script) return;
    const newStep: ScriptStep = {
      id: Date.now().toString() + Math.random().toString(36).slice(2, 5),
      order: script.steps.length + 1,
      message: "", mediaUrls: [], waitBeforeMedia: false,
      priceStars: 0, discountEnabled: false, discountedPriceStars: 0,
      messagesBetweenSteps: "normal", skipFollowupIfPaid: false,
      preMediaTeaser: "", postMediaMessages: [],
    };
    setS({ steps: [...script.steps, newStep] });
  };

  const updateStep = (idx: number, s: ScriptStep) => {
    if (!script) return;
    const steps = [...script.steps]; steps[idx] = s; setS({ steps });
  };

  const deleteStep = (idx: number) => {
    if (!script) return;
    setS({ steps: script.steps.filter((_, i) => i !== idx) });
  };

  const moveStep = (idx: number, dir: -1 | 1) => {
    if (!script) return;
    const steps = [...script.steps];
    const t = idx + dir;
    if (t < 0 || t >= steps.length) return;
    [steps[idx], steps[t]] = [steps[t], steps[idx]];
    setS({ steps: steps.map((s, i) => ({ ...s, order: i + 1 })) });
  };

  if (loading) return <div className="flex items-center justify-center py-20" style={{ color: "#4b5563" }}><RefreshCw size={16} className="animate-spin mr-2" /></div>;
  if (!script) return <div className="p-8 text-center text-sm" style={{ color: "#4b5563" }}>Script introuvable.</div>;

  return (
    <div className="p-6 max-w-4xl" style={{ color: "#fff" }}>
      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        <button onClick={() => router.push(`/dashboard/creators/${id}/scripts`)}
          className="flex items-center gap-1.5 text-sm hover:text-white transition-all" style={{ color: "#6b7280" }}>
          <ArrowLeft size={15} /> Back
        </button>
        <div className="w-8 h-8 rounded-full flex items-center justify-center text-sm" style={{ background: "#e11d48" }}>✦</div>
        <div>
          <h1 className="text-base font-bold">Edit Script</h1>
          <p className="text-xs" style={{ color: "#6b7280" }}>Modify {script.name}</p>
        </div>
        <div className="flex-1" />
        <button onClick={save} disabled={saving}
          className="flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-semibold"
          style={{ background: saved ? "#10b981" : "#e11d48", color: "#fff" }}>
          {saving ? <RefreshCw size={13} className="animate-spin" /> : null}
          {saved ? "Saved ✓" : saving ? "Saving..." : "Update Script"}
        </button>
      </div>

      <div className="space-y-5">
        {/* Name */}
        <div>
          <label className="block text-xs font-medium mb-1.5" style={{ color: "#9ca3af" }}>Name</label>
          <input value={script.name} onChange={e => setS({ name: e.target.value.toUpperCase() })}
            className="w-full px-4 py-2.5 rounded-xl text-sm outline-none uppercase font-semibold"
            style={{ background: "#111118", border: "1px solid #1e1e2e", color: "#fff" }} />
        </div>

        {/* Description */}
        <div>
          <label className="block text-xs font-medium mb-1.5" style={{ color: "#9ca3af" }}>Description</label>
          <textarea value={script.description} onChange={e => setS({ description: e.target.value })}
            rows={3} className="w-full px-4 py-2.5 rounded-xl text-sm outline-none resize-none"
            style={{ background: "#111118", border: "1px solid #1e1e2e", color: "#d1d5db" }} />
        </div>

        {/* Strict cooldown */}
        <div className="flex items-start justify-between p-4 rounded-xl border" style={{ borderColor: "#1e1e2e", background: "#0f0f1a" }}>
          <div>
            <p className="text-sm font-medium">Apply strict cooldown even after full script purchase</p>
            <p className="text-xs mt-1" style={{ color: "#6b7280" }}>If enabled, the script will enter strict cooldown even when fully purchased.</p>
          </div>
          <Toggle value={script.strictCooldown} onChange={v => setS({ strictCooldown: v })} />
        </div>

        {/* Inactivity timeout */}
        <div className="p-4 rounded-xl border" style={{ borderColor: "#1e1e2e", background: "#0f0f1a" }}>
          <div className="flex items-center justify-between mb-2">
            <label className="text-sm font-medium">Script Inactivity timeout (hours): {script.inactivityTimeoutHours}h</label>
          </div>
          <input type="range" min={1} max={72} value={script.inactivityTimeoutHours}
            onChange={e => setS({ inactivityTimeoutHours: Number(e.target.value) })}
            className="w-full" style={{ accentColor: "#e11d48" }} />
          <p className="text-xs mt-2" style={{ color: "#6b7280" }}>After this delay without interaction, the bot exits the script.</p>
        </div>

        {/* Script Steps */}
        <div>
          <h3 className="font-semibold text-base mb-1">Script Steps</h3>
          <p className="text-xs mb-4" style={{ color: "#6b7280" }}>Define the conversation flow and actions for this script</p>
          <div className="space-y-4">
            {script.steps.map((step, idx) => (
              <StepCard key={step.id} step={step} index={idx} total={script.steps.length}
                scriptId={script.id}
                onChange={s => updateStep(idx, s)}
                onDelete={() => deleteStep(idx)}
                onMoveUp={() => moveStep(idx, -1)}
                onMoveDown={() => moveStep(idx, 1)} />
            ))}
            <button onClick={addStep}
              className="w-full py-3 rounded-xl border-2 border-dashed flex items-center justify-center gap-2 text-sm hover:border-red-500/40 transition-all"
              style={{ borderColor: "#1e1e2e", color: "#6b7280" }}>
              <Plus size={15} /> Add Step
            </button>
          </div>
        </div>

        {/* Update button bottom */}
        <div className="flex justify-end pb-8">
          <button onClick={save} disabled={saving}
            className="px-8 py-3 rounded-xl text-sm font-semibold"
            style={{ background: saved ? "#10b981" : "#e11d48", color: "#fff" }}>
            {saved ? "Saved ✓" : saving ? "Saving..." : "Update Script"}
          </button>
        </div>
      </div>
    </div>
  );
}
