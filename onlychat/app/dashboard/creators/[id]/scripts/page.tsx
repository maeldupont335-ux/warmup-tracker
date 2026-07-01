"use client";
import { useState, useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import { Plus, Search, Star, Pencil, Copy, Trash2, Download, RefreshCw } from "lucide-react";
import type { Script } from "@/lib/scripts-store";

function Toggle({ value, onChange }: { value: boolean; onChange: (v: boolean) => void }) {
  return (
    <button onClick={() => onChange(!value)}
      className="relative w-10 h-5 rounded-full transition-all flex-shrink-0"
      style={{ background: value ? "#e11d48" : "#374151" }}>
      <div className="absolute top-0.5 w-4 h-4 rounded-full bg-white transition-all shadow"
        style={{ left: value ? "calc(100% - 18px)" : "2px" }} />
    </button>
  );
}

export default function ScriptsPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [scripts, setScripts] = useState<Script[]>([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [newName, setNewName] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [adding, setAdding] = useState(false);

  const fetch_ = async () => {
    setLoading(true);
    const res = await fetch(`/api/creators/${id}/scripts`);
    const d = await res.json();
    setScripts(d.scripts ?? []);
    setLoading(false);
  };

  useEffect(() => { fetch_(); }, [id]);

  const patch = async (scriptId: string, patch: Partial<Script>) => {
    await fetch(`/api/creators/${id}/scripts`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scriptId, patch }),
    });
    fetch_();
  };

  const handleAdd = async () => {
    if (!newName.trim()) return;
    setAdding(true);
    const res = await fetch(`/api/creators/${id}/scripts`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: newName.toUpperCase(), description: newDesc }),
    });
    const d = await res.json();
    setAdding(false);
    setShowModal(false);
    setNewName(""); setNewDesc("");
    router.push(`/dashboard/creators/${id}/scripts/${d.script.id}`);
  };

  const handleDuplicate = async (s: Script) => {
    const copy: Script = { ...s, id: Date.now().toString(), name: s.name + " (copie)", active: false, createdAt: new Date().toISOString(), updatedAt: new Date().toISOString() };
    await fetch(`/api/creators/${id}/scripts`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ script: copy }),
    });
    fetch_();
  };

  const handleDelete = async (scriptId: string) => {
    if (!confirm("Supprimer ce script ?")) return;
    await fetch(`/api/creators/${id}/scripts`, {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scriptId }),
    });
    fetch_();
  };

  const formatDate = (d: string) => new Date(d).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric", hour: "2-digit", minute: "2-digit" });

  const filtered = scripts.filter(s =>
    s.name.toLowerCase().includes(search.toLowerCase()) ||
    s.description.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="p-6" style={{ color: "#fff" }}>
      {/* Toolbar */}
      <div className="flex items-center gap-3 mb-5">
        <div className="relative flex-1 max-w-xs">
          <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: "#6b7280" }} />
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Filter by name..."
            className="w-full pl-9 pr-4 py-2 rounded-lg text-sm outline-none"
            style={{ background: "#111118", border: "1px solid #1e1e2e", color: "#d1d5db" }} />
        </div>
        <div className="flex-1" />
        <button className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm border transition-all hover:bg-white/5"
          style={{ borderColor: "#1e1e2e", color: "#9ca3af" }}>
          <Download size={13} /> Import Script
        </button>
        <button onClick={() => { setShowModal(true); setNewName(""); setNewDesc(""); }}
          className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium"
          style={{ background: "#e11d48", color: "#fff" }}>
          <Plus size={13} /> Add Script
        </button>
      </div>

      {/* Table */}
      <div className="rounded-xl border overflow-hidden" style={{ borderColor: "#1e1e2e" }}>
        <table className="w-full text-sm">
          <thead>
            <tr style={{ borderBottom: "1px solid #1e1e2e" }}>
              {["Active", "First", "Name", "Description", "Created at ↓", "Group", ""].map(h => (
                <th key={h} className="text-left px-4 py-3 font-medium text-xs" style={{ color: "#6b7280" }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={7} className="text-center py-10" style={{ color: "#4b5563" }}>
                <RefreshCw size={16} className="animate-spin mx-auto mb-2" />
              </td></tr>
            ) : filtered.length === 0 ? (
              <tr><td colSpan={7} className="text-center py-12 text-sm" style={{ color: "#4b5563" }}>
                Aucun script — clique &quot;Add Script&quot; pour créer le premier
              </td></tr>
            ) : filtered.map((s, i) => (
              <tr key={s.id} style={{ borderBottom: i < filtered.length - 1 ? "1px solid #1a1a28" : "none", background: "#0f0f1a" }}>
                {/* Active */}
                <td className="px-4 py-3">
                  <Toggle value={s.active} onChange={v => patch(s.id, { active: v })} />
                </td>

                {/* First (étoile) */}
                <td className="px-4 py-3">
                  <button onClick={() => patch(s.id, { first: !s.first })}>
                    <Star size={15} fill={s.first ? "#f59e0b" : "none"} style={{ color: s.first ? "#f59e0b" : "#4b5563" }} />
                  </button>
                </td>

                {/* Name */}
                <td className="px-4 py-3">
                  <button onClick={() => router.push(`/dashboard/creators/${id}/scripts/${s.id}`)}
                    className="text-left hover:underline font-medium" style={{ color: "#d1d5db" }}>
                    {s.name}
                  </button>
                </td>

                {/* Description */}
                <td className="px-4 py-3 max-w-md">
                  <p className="text-xs line-clamp-2" style={{ color: "#9ca3af" }}>
                    {s.description || <span style={{ color: "#4b5563" }}>—</span>}
                  </p>
                </td>

                {/* Created at */}
                <td className="px-4 py-3 text-xs whitespace-nowrap" style={{ color: "#6b7280" }}>
                  {formatDate(s.createdAt)}
                </td>

                {/* Group */}
                <td className="px-4 py-3 text-xs" style={{ color: "#6b7280" }}>{s.group ?? "—"}</td>

                {/* Actions */}
                <td className="px-4 py-3">
                  <div className="flex items-center gap-1">
                    <button onClick={() => router.push(`/dashboard/creators/${id}/scripts/${s.id}`)}
                      className="p-1.5 rounded hover:bg-white/5 transition-all"
                      style={{ color: "#e11d48", border: "1px solid rgba(225,29,72,0.2)" }}>
                      <Pencil size={12} />
                    </button>
                    <button onClick={() => handleDuplicate(s)}
                      className="p-1.5 rounded hover:bg-white/5 transition-all"
                      style={{ color: "#e11d48", border: "1px solid rgba(225,29,72,0.2)" }}>
                      <Copy size={12} />
                    </button>
                    <button onClick={() => handleDelete(s.id)}
                      className="p-1.5 rounded hover:bg-white/5 transition-all"
                      style={{ color: "#e11d48", border: "1px solid rgba(225,29,72,0.2)" }}>
                      <Trash2 size={12} />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Modal nouveau script */}
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center px-4"
          style={{ background: "rgba(0,0,0,0.8)" }} onClick={() => setShowModal(false)}>
          <div className="w-full max-w-md rounded-2xl border p-6" style={{ background: "#111118", borderColor: "#1e1e2e" }}
            onClick={e => e.stopPropagation()}>
            <h2 className="font-bold text-lg mb-4">Nouveau script</h2>
            <div className="space-y-4">
              <div>
                <label className="block text-xs mb-1.5" style={{ color: "#6b7280" }}>Nom du script</label>
                <input value={newName} onChange={e => setNewName(e.target.value.toUpperCase())}
                  placeholder="SCRIPT 1 // NOM"
                  className="w-full px-4 py-2.5 rounded-xl text-sm outline-none uppercase"
                  style={{ background: "#0a0a0f", border: "1px solid #1e1e2e", color: "#fff" }} />
              </div>
              <div>
                <label className="block text-xs mb-1.5" style={{ color: "#6b7280" }}>Description (optionnel)</label>
                <textarea value={newDesc} onChange={e => setNewDesc(e.target.value)} rows={3}
                  placeholder="Décris le scénario de ce script..."
                  className="w-full px-4 py-2.5 rounded-xl text-sm outline-none resize-none"
                  style={{ background: "#0a0a0f", border: "1px solid #1e1e2e", color: "#d1d5db" }} />
              </div>
              <div className="flex gap-3">
                <button onClick={() => setShowModal(false)} className="flex-1 py-2.5 rounded-xl text-sm border" style={{ borderColor: "#1e1e2e", color: "#9ca3af" }}>Annuler</button>
                <button onClick={handleAdd} disabled={adding || !newName.trim()}
                  className="flex-1 py-2.5 rounded-xl text-sm font-medium disabled:opacity-40 flex items-center justify-center gap-2"
                  style={{ background: "#e11d48", color: "#fff" }}>
                  {adding ? <RefreshCw size={13} className="animate-spin" /> : <Plus size={13} />}
                  {adding ? "Création..." : "Créer & éditer"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
