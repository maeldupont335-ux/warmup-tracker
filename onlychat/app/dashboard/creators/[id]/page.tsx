"use client";
import { useState, useEffect } from "react";
import { useParams } from "next/navigation";
import { Search, MessageSquare, FileText, Tag, RefreshCw, Star, X } from "lucide-react";

interface Fan {
  id: string;
  name: string;
  username: string | null;
  telegramId: string;
  lastInteraction: string;
  scriptsUsed: string;
  totalStars: number | null;
  totalUsd: number | null;
  enableIA: boolean;
  tags: string[];
  fanProfile?: string;
}

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

function NoteModal({ fan, creatorId, onClose }: { fan: Fan; creatorId: string; onClose: () => void }) {
  const [note, setNote] = useState(fan.fanProfile ?? "");
  const [saving, setSaving] = useState(false);

  const save = async () => {
    setSaving(true);
    await fetch(`/api/creators/${creatorId}/fans`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ fanId: fan.id, fanProfile: note }),
    });
    setSaving(false);
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: "rgba(0,0,0,0.7)" }}
      onClick={e => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="rounded-2xl border p-6 w-full max-w-lg"
        style={{ background: "#111118", borderColor: "#1e1e2e" }}>
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-bold text-base" style={{ color: "#fff" }}>
            Note for {fan.name || fan.telegramId}
          </h2>
          <button onClick={onClose} className="p-1 rounded hover:bg-white/10" style={{ color: "#6b7280" }}>
            <X size={16} />
          </button>
        </div>
        <p className="text-xs mb-3" style={{ color: "#6b7280" }}>Personal Info</p>
        <textarea
          value={note}
          onChange={e => setNote(e.target.value)}
          rows={8}
          className="w-full rounded-lg p-3 text-sm outline-none resize-none"
          style={{ background: "#0d0d14", border: "1px solid #e11d48", color: "#d1d5db" }}
          placeholder="Notes sur ce fan (extraites automatiquement par l'IA ou saisies manuellement)..."
        />
        <div className="flex gap-3 mt-4">
          <button onClick={onClose}
            className="flex-1 py-2 rounded-lg text-sm border transition-all"
            style={{ borderColor: "#1e1e2e", color: "#6b7280" }}>
            Cancel
          </button>
          <button onClick={save} disabled={saving}
            className="flex-1 py-2 rounded-lg text-sm font-bold transition-all"
            style={{ background: "#e11d48", color: "#fff" }}>
            {saving ? "Saving..." : "Save"}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function CreatorFansPage() {
  const { id } = useParams<{ id: string }>();
  const [fans, setFans] = useState<Fan[]>([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [enableAllLoading, setEnableAllLoading] = useState(false);
  const [noteFan, setNoteFan] = useState<Fan | null>(null);

  const fetchFans = async () => {
    setLoading(true);
    try {
      const res = await fetch(`/api/creators/${id}/fans`);
      if (res.ok) {
        const d = await res.json();
        setFans(d.fans ?? []);
      }
    } catch { /* ignore */ }
    setLoading(false);
  };

  useEffect(() => { fetchFans(); }, [id]);

  const toggleFanIA = async (fanId: string, value: boolean) => {
    setFans(fs => fs.map(f => f.id === fanId ? { ...f, enableIA: value } : f));
    await fetch(`/api/creators/${id}/fans`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ fanId, enableIA: value }),
    });
  };

  const setAllIA = async (value: boolean) => {
    setEnableAllLoading(true);
    setFans(fs => fs.map(f => ({ ...f, enableIA: value })));
    await fetch(`/api/creators/${id}/fans`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ all: true, enableIA: value }),
    });
    setEnableAllLoading(false);
  };

  const formatDate = (d: string) =>
    new Date(d).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric", hour: "2-digit", minute: "2-digit" });

  const filtered = fans.filter(f =>
    (f.name ?? "").toLowerCase().includes(search.toLowerCase()) ||
    (f.username ?? "").toLowerCase().includes(search.toLowerCase()) ||
    f.telegramId.includes(search)
  );

  return (
    <div className="p-6" style={{ color: "#fff" }}>
      {noteFan && (
        <NoteModal
          fan={noteFan}
          creatorId={id}
          onClose={() => { setNoteFan(null); fetchFans(); }}
        />
      )}

      {/* Toolbar */}
      <div className="flex items-center gap-3 mb-5">
        <div className="relative max-w-xs flex-1">
          <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: "#6b7280" }} />
          <input value={search} onChange={e => setSearch(e.target.value)}
            placeholder="Filter by name or username..."
            className="w-full pl-9 pr-4 py-2 rounded-lg text-sm outline-none"
            style={{ background: "#111118", border: "1px solid #1e1e2e", color: "#d1d5db" }} />
        </div>
        <div className="flex-1" />
        <button onClick={() => setAllIA(true)} disabled={enableAllLoading}
          className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm border transition-all"
          style={{ borderColor: "rgba(16,185,129,0.3)", color: "#10b981", background: "rgba(16,185,129,0.06)" }}>
          ✓ Enable AI for all
        </button>
        <button onClick={() => setAllIA(false)} disabled={enableAllLoading}
          className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm border transition-all"
          style={{ borderColor: "rgba(225,29,72,0.3)", color: "#e11d48", background: "rgba(225,29,72,0.06)" }}>
          ✗ Disable AI for all
        </button>
      </div>

      {/* Table */}
      <div className="rounded-xl border overflow-hidden" style={{ borderColor: "#1e1e2e" }}>
        <table className="w-full text-sm">
          <thead>
            <tr style={{ background: "#0d0d14", borderBottom: "1px solid #1e1e2e" }}>
              <th className="text-left px-4 py-3 text-xs font-medium" style={{ color: "#6b7280" }}>Fan</th>
              <th className="text-left px-4 py-3 text-xs font-medium" style={{ color: "#6b7280" }}>Username</th>
              <th className="text-left px-4 py-3 text-xs font-medium" style={{ color: "#6b7280" }}>Telegram ID</th>
              <th className="text-left px-4 py-3 text-xs font-medium cursor-pointer" style={{ color: "#6b7280" }}>Last interaction ↕</th>
              <th className="text-left px-4 py-3 text-xs font-medium cursor-pointer" style={{ color: "#6b7280" }}>Scripts used ↕</th>
              <th className="text-left px-4 py-3 text-xs font-medium cursor-pointer" style={{ color: "#6b7280" }}>Total spent ↕</th>
              <th className="text-left px-4 py-3 text-xs font-medium cursor-pointer" style={{ color: "#6b7280" }}>Enable IA ↕</th>
              <th className="text-left px-4 py-3 text-xs font-medium" style={{ color: "#6b7280" }}>Tags</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={8} className="text-center py-12" style={{ color: "#4b5563" }}>
                <RefreshCw size={16} className="animate-spin mx-auto mb-2" />
              </td></tr>
            ) : filtered.length === 0 ? (
              <tr><td colSpan={8} className="text-center py-12 text-sm" style={{ color: "#4b5563" }}>
                Aucun fan pour le moment — les fans apparaîtront ici dès qu&apos;ils enverront un message
              </td></tr>
            ) : filtered.map((f, i) => (
              <tr key={f.id}
                style={{ borderBottom: i < filtered.length - 1 ? "1px solid #1a1a28" : "none", background: "#0f0f1a" }}>
                {/* Fan name */}
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2">
                    <span className="font-medium" style={{ color: "#d1d5db" }}>{f.name || "—"}</span>
                    <button className="flex items-center gap-1 px-2 py-0.5 rounded text-xs border"
                      style={{ borderColor: "#1e1e2e", color: "#6b7280" }}>
                      <MessageSquare size={10} /> Messages
                    </button>
                    <button
                      onClick={() => setNoteFan(f)}
                      className="flex items-center gap-1 px-2 py-0.5 rounded text-xs border transition-all hover:border-red-500/40 hover:text-red-400"
                      style={{ borderColor: f.fanProfile ? "rgba(225,29,72,0.4)" : "#1e1e2e", color: f.fanProfile ? "#e11d48" : "#6b7280" }}>
                      <FileText size={10} /> Note{f.fanProfile ? " ●" : ""}
                    </button>
                  </div>
                </td>

                {/* Username */}
                <td className="px-4 py-3 text-xs" style={{ color: "#9ca3af" }}>
                  {f.username ? `@${f.username}` : "—"}
                </td>

                {/* Telegram ID */}
                <td className="px-4 py-3 text-xs" style={{ color: "#6b7280" }}>{f.telegramId}</td>

                {/* Last interaction */}
                <td className="px-4 py-3 text-xs" style={{ color: "#6b7280" }}>
                  {f.lastInteraction ? formatDate(f.lastInteraction) : "—"}
                </td>

                {/* Scripts used */}
                <td className="px-4 py-3 text-xs" style={{ color: "#6b7280" }}>
                  {f.scriptsUsed || "—"}
                </td>

                {/* Total spent */}
                <td className="px-4 py-3">
                  {f.totalStars ? (
                    <span className="flex items-center gap-1 text-xs"
                      style={{ color: "#f59e0b" }}>
                      <Star size={11} fill="#f59e0b" /> {f.totalStars}
                      {f.totalUsd && <span style={{ color: "#6b7280" }}>(${f.totalUsd.toFixed(2)})</span>}
                    </span>
                  ) : <span style={{ color: "#4b5563" }}>—</span>}
                </td>

                {/* Enable IA */}
                <td className="px-4 py-3">
                  <Toggle value={f.enableIA} onChange={v => toggleFanIA(f.id, v)} />
                </td>

                {/* Tags */}
                <td className="px-4 py-3">
                  <button className="p-1 rounded hover:bg-white/5" style={{ color: "#4b5563" }}>
                    <Tag size={13} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
