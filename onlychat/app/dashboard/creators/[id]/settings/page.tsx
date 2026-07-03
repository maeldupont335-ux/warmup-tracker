"use client";
import { useState, useEffect } from "react";
import { useParams } from "next/navigation";
import { Save, RefreshCw, Plus, X } from "lucide-react";
import type { CreatorSettings } from "@/app/api/creators/[id]/settings/route";

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

function Field({ label, children, span = 1 }: { label: string; children: React.ReactNode; span?: number }) {
  return (
    <div className={span === 2 ? "col-span-2" : ""}>
      <label className="block text-xs font-medium mb-1.5" style={{ color: "#9ca3af" }}>{label}</label>
      {children}
    </div>
  );
}

const inputCls = "w-full px-3 py-2 rounded-lg text-sm outline-none";
const inputStyle = { background: "#0a0a0f", border: "1px solid #1e1e2e", color: "#d1d5db" };

function SelectInput({ value, onChange, options }: { value: string; onChange: (v: string) => void; options: string[] }) {
  return (
    <select value={value} onChange={e => onChange(e.target.value)}
      className={inputCls} style={{ ...inputStyle, cursor: "pointer" }}>
      {options.map(o => <option key={o} value={o}>{o}</option>)}
    </select>
  );
}

function TagInput({ tags, onChange, placeholder }: { tags: string[]; onChange: (t: string[]) => void; placeholder?: string }) {
  const [input, setInput] = useState("");
  const add = () => {
    const v = input.trim();
    if (v && !tags.includes(v)) onChange([...tags, v]);
    setInput("");
  };
  return (
    <div className="rounded-lg p-2 flex flex-wrap gap-1.5 min-h-[42px]"
      style={{ background: "#0a0a0f", border: "1px solid #1e1e2e" }}>
      {tags.map(t => (
        <span key={t} className="flex items-center gap-1 px-2 py-0.5 rounded-full text-xs"
          style={{ background: "#1e1e2e", color: "#d1d5db" }}>
          {t}
          <button onClick={() => onChange(tags.filter(x => x !== t))} className="hover:text-red-400">
            <X size={10} />
          </button>
        </span>
      ))}
      <div className="flex items-center gap-1 flex-1 min-w-[120px]">
        <input value={input} onChange={e => setInput(e.target.value)}
          onKeyDown={e => { if (e.key === "Enter") { e.preventDefault(); add(); } }}
          placeholder={placeholder ?? "Add an item"}
          className="flex-1 bg-transparent outline-none text-xs"
          style={{ color: "#d1d5db" }} />
        <button onClick={add} style={{ color: "#6b7280" }}><Plus size={12} /></button>
      </div>
    </div>
  );
}

function Slider({ value, onChange, min, max, unit, label }: {
  value: number; onChange: (v: number) => void; min: number; max: number; unit: string; label: string;
}) {
  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <label className="text-sm" style={{ color: "#d1d5db" }}>{label}</label>
      </div>
      <input type="range" min={min} max={max} value={value} onChange={e => onChange(Number(e.target.value))}
        className="w-full h-1.5 rounded-full appearance-none cursor-pointer"
        style={{ accentColor: "#e11d48" }} />
      <p className="text-xs mt-1" style={{ color: "#6b7280" }}>{value} {unit}</p>
    </div>
  );
}

const HAIR_COLORS = ["Blonde", "Brown", "Black", "Red", "Auburn", "Gray", "White", "Other"];
const EYE_COLORS = ["Brown", "Blue", "Green", "Hazel", "Gray", "Black", "Other"];
const GENDERS = ["Female", "Male", "Non-binary", "Other"];
const ETHNICITIES = ["White", "Black", "Asian", "Latino", "Middle Eastern", "Mixed", "Other"];
const TIMEZONES = ["UTC-8 — LA", "UTC-5 — New York", "UTC+0 — London", "UTC+1 — Berlin", "UTC+2 — Paris", "UTC+3 — Moscow", "UTC+8 — Shanghai", "UTC+9 — Tokyo"];
const BAND_SIZES = ["65","70","75","80","85","90","95","100","105"];
const CUP_SIZES = ["A","B","C","D","E","F","G"];

export default function CreatorSettingsPage() {
  const { id } = useParams<{ id: string }>();
  const [settings, setSettings] = useState<CreatorSettings | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    fetch(`/api/creators/${id}/settings`)
      .then(r => r.json())
      .then(d => setSettings(d.settings));
  }, [id]);

  const set = (patch: Partial<CreatorSettings>) => setSettings(s => s ? { ...s, ...patch } : s);

  const save = async () => {
    if (!settings) return;
    setSaving(true);
    await fetch(`/api/creators/${id}/settings`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(settings),
    });
    setSaving(false);
    setSaved(true);
    setTimeout(() => setSaved(false), 2500);
  };

  if (!settings) return (
    <div className="flex items-center justify-center py-20" style={{ color: "#4b5563" }}>
      <RefreshCw size={16} className="animate-spin mr-2" />
    </div>
  );

  return (
    <div className="p-6 max-w-3xl" style={{ color: "#fff" }}>
      {/* Save button */}
      <div className="flex justify-end mb-6">
        <button onClick={save} disabled={saving}
          className="flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-medium disabled:opacity-60"
          style={{ background: saved ? "#10b981" : "#e11d48", color: "#fff" }}>
          {saving ? <RefreshCw size={13} className="animate-spin" /> : <Save size={13} />}
          {saved ? "Sauvegardé ✓" : saving ? "Sauvegarde..." : "Save settings"}
        </button>
      </div>

      <div className="space-y-6">
        {/* Identity */}
        <div className="grid grid-cols-4 gap-4">
          <Field label="First Name">
            <input value={settings.firstName} onChange={e => set({ firstName: e.target.value })}
              placeholder="Pauline" className={inputCls} style={inputStyle} />
          </Field>
          <Field label="Age">
            <input value={settings.age} onChange={e => set({ age: e.target.value })}
              placeholder="20" className={inputCls} style={inputStyle} />
          </Field>
          <Field label="Date of Birth">
            <input value={settings.dateOfBirth} onChange={e => set({ dateOfBirth: e.target.value })}
              placeholder="21/10/2005" className={inputCls} style={inputStyle} />
          </Field>
          <Field label="Gender">
            <SelectInput value={settings.gender} onChange={v => set({ gender: v })} options={GENDERS} />
          </Field>
        </div>

        {/* Physical */}
        <div className="grid grid-cols-4 gap-4">
          <Field label="Weight (in kg)">
            <input value={settings.weight} onChange={e => set({ weight: e.target.value })}
              placeholder="66" className={inputCls} style={inputStyle} />
          </Field>
          <Field label="Height (in cm)">
            <input value={settings.height} onChange={e => set({ height: e.target.value })}
              placeholder="165" className={inputCls} style={inputStyle} />
          </Field>
          <Field label="Hair color">
            <SelectInput value={settings.hairColor} onChange={v => set({ hairColor: v })} options={["", ...HAIR_COLORS]} />
          </Field>
          <Field label="Eye color">
            <SelectInput value={settings.eyeColor} onChange={v => set({ eyeColor: v })} options={["", ...EYE_COLORS]} />
          </Field>
        </div>

        {/* Bra + Ethnicity + Shoe + Timezone */}
        <div className="grid grid-cols-4 gap-4">
          <Field label="Bra size — Band size">
            <SelectInput value={settings.braBandSize} onChange={v => set({ braBandSize: v })} options={["", ...BAND_SIZES]} />
          </Field>
          <Field label="Cup size">
            <SelectInput value={settings.braCupSize} onChange={v => set({ braCupSize: v })} options={["", ...CUP_SIZES]} />
          </Field>
          <Field label="Ethnicity">
            <SelectInput value={settings.ethnicity} onChange={v => set({ ethnicity: v })} options={["", ...ETHNICITIES]} />
          </Field>
          <Field label="Shoe size (EU)">
            <input value={settings.shoeSize} onChange={e => set({ shoeSize: e.target.value })}
              placeholder="39" className={inputCls} style={inputStyle} />
          </Field>
        </div>

        {/* Timezone */}
        <div className="grid grid-cols-2 gap-4">
          <Field label="Timezone">
            <SelectInput value={settings.timezone} onChange={v => set({ timezone: v })} options={TIMEZONES} />
          </Field>
        </div>

        {/* Languages */}
        <Field label="Languages">
          <TagInput tags={settings.languages} onChange={v => set({ languages: v })} placeholder="Add Language" />
        </Field>

        {/* Hobbies */}
        <Field label="Hobbies">
          <TagInput tags={settings.hobbies} onChange={v => set({ hobbies: v })} placeholder="Add an item" />
        </Field>

        {/* Personality Traits */}
        <Field label="Personality Traits">
          <TagInput tags={settings.personalityTraits} onChange={v => set({ personalityTraits: v })} placeholder="Add an item" />
        </Field>

        {/* Additional info */}
        <Field label="Additional info">
          <textarea value={settings.additionalInfo} onChange={e => set({ additionalInfo: e.target.value })}
            rows={6} maxLength={6000} placeholder="Nom: Pauline&#10;Décris ta personnalité, tes habitudes, ton style..."
            className="w-full px-3 py-2.5 rounded-lg text-sm outline-none resize-none"
            style={{ background: "#0a0a0f", border: "1px solid #1e1e2e", color: "#d1d5db" }} />
          <p className="text-xs mt-1" style={{ color: "#4b5563" }}>
            {settings.additionalInfo.length} / 6000 characters
          </p>
        </Field>

        {/* Sliders */}
        <div className="space-y-6 pt-2">
          <Slider label="Minimum Sexualization Cooldown (days)"
            value={settings.sexualizationCooldownDays} min={0} max={30} unit="day(s)"
            onChange={v => set({ sexualizationCooldownDays: v })} />
          <Slider label="Strict Script Cooldown (hours)"
            value={settings.strictScriptCooldownHours} min={0} max={72} unit="hour(s)"
            onChange={v => set({ strictScriptCooldownHours: v })} />
          <Slider label="Follow-Up Delay (minutes)"
            value={settings.followUpDelayMinutes} min={1} max={120} unit="minute(s)"
            onChange={v => set({ followUpDelayMinutes: v })} />
          <Slider label="Response Delay (minutes)"
            value={settings.responseDelayMinutes} min={0} max={30} unit="minute(s)"
            onChange={v => set({ responseDelayMinutes: v })} />
        </div>

        {/* Split messages toggle */}
        <div className="flex items-start justify-between gap-4 p-4 rounded-xl border"
          style={{ borderColor: "#1e1e2e", background: "#0f0f1a" }}>
          <div>
            <p className="text-sm font-medium">Split long AI messages into multiple bubbles</p>
            <p className="text-xs mt-1" style={{ color: "#6b7280" }}>
              When enabled, long AI replies are split into short messages (more natural). Disable if you&apos;re seeing slowdowns or missed replies during high traffic.
            </p>
          </div>
          <Toggle value={settings.splitLongMessages} onChange={v => set({ splitLongMessages: v })} />
        </div>
      </div>

      {/* Save bottom */}
      <div className="flex justify-end mt-8 pb-8">
        <button onClick={save} disabled={saving}
          className="flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-medium disabled:opacity-60"
          style={{ background: saved ? "#10b981" : "#e11d48", color: "#fff" }}>
          {saving ? <RefreshCw size={13} className="animate-spin" /> : <Save size={13} />}
          {saved ? "Sauvegardé ✓" : saving ? "Sauvegarde..." : "Save settings"}
        </button>
      </div>
    </div>
  );
}
