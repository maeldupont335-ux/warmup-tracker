"use client";
import { useState } from "react";
import { Settings, X } from "lucide-react";

export function SettingsPanel({
  tokenSavedAt,
  organizationId,
  onSaved,
}: {
  tokenSavedAt: string | null;
  organizationId: string | null;
  onSaved: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [accessToken, setAccessToken] = useState("");
  const [orgId, setOrgId] = useState(organizationId ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    setSaving(true);
    setError(null);
    try {
      const res = await fetch("/api/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ accessToken, organizationId: orgId }),
      });
      if (!res.ok) throw new Error("Échec de l'enregistrement");
      setAccessToken("");
      onSaved();
      setOpen(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur inconnue");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className="p-2 rounded-xl border transition-all"
        style={{ background: "#111118", borderColor: "#1e1e2e", color: "#9ca3af" }}
        title="Réglages"
      >
        <Settings size={16} />
      </button>
      {open && (
        <div
          className="absolute right-0 top-12 w-80 p-4 rounded-2xl border z-10"
          style={{ background: "#111118", borderColor: "#1e1e2e" }}
        >
          <div className="flex items-center justify-between mb-3">
            <h3 className="font-bold text-sm">Réglages OnlyChat</h3>
            <button onClick={() => setOpen(false)} style={{ color: "#6b7280" }}>
              <X size={16} />
            </button>
          </div>
          <p className="text-xs mb-3" style={{ color: "#6b7280" }}>
            Dernier token enregistré : {tokenSavedAt ? new Date(tokenSavedAt).toLocaleString("fr-FR") : "aucun"}
          </p>
          <label className="text-xs" style={{ color: "#9ca3af" }}>Organization ID</label>
          <input
            value={orgId}
            onChange={(e) => setOrgId(e.target.value)}
            className="w-full mt-1 mb-3 px-3 py-2 rounded-lg text-sm outline-none"
            style={{ background: "#0a0a0f", border: "1px solid #1e1e2e", color: "#fff" }}
          />
          <label className="text-xs" style={{ color: "#9ca3af" }}>Nouveau token d&apos;accès</label>
          <input
            type="password"
            value={accessToken}
            onChange={(e) => setAccessToken(e.target.value)}
            placeholder="Coller le token ici"
            className="w-full mt-1 mb-3 px-3 py-2 rounded-lg text-sm outline-none"
            style={{ background: "#0a0a0f", border: "1px solid #1e1e2e", color: "#fff" }}
          />
          {error && <p className="text-xs mb-2" style={{ color: "#ef4444" }}>{error}</p>}
          <button
            onClick={save}
            disabled={saving || !accessToken || !orgId}
            className="w-full py-2 rounded-lg text-sm font-medium disabled:opacity-50"
            style={{ background: "linear-gradient(135deg,#a855f7,#7c3aed)", color: "#fff" }}
          >
            {saving ? "Enregistrement..." : "Enregistrer"}
          </button>
        </div>
      )}
    </div>
  );
}
