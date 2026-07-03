"use client";
import { useState, useEffect, useRef, useCallback } from "react";
import { useParams } from "next/navigation";
import { FolderOpen, Trash2, Plus, X, ChevronRight, Upload, RefreshCw, ArrowLeft } from "lucide-react";
import type { Script } from "@/lib/scripts-store";

interface MediaItem { name: string; isDir: boolean; url: string | null; size: number; }

export default function MediasPage() {
  const { id } = useParams<{ id: string }>();
  const [scripts, setScripts] = useState<Script[]>([]);
  const [customFolders, setCustomFolders] = useState<string[]>([]);
  const [openFolder, setOpenFolder] = useState<string | null>(null);
  const [items, setItems] = useState<MediaItem[]>([]);
  const [uploadsToday, setUploadsToday] = useState(0);
  const [loading, setLoading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [newFolderName, setNewFolderName] = useState("");
  const [showNewFolder, setShowNewFolder] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  // Charge les scripts
  useEffect(() => {
    fetch(`/api/creators/${id}/scripts`)
      .then(r => r.json())
      .then(d => setScripts(d.scripts ?? []));
  }, [id]);

  // Charge les dossiers custom (dossiers qui ne sont pas des scripts)
  const refreshFolders = useCallback(() => {
    fetch(`/api/creators/${id}/media`)
      .then(r => r.json())
      .then(d => {
        const dirs = (d.items ?? [])
          .filter((i: MediaItem) => i.isDir)
          .map((i: MediaItem) => i.name);
        setCustomFolders(dirs);
      })
      .catch(() => {});
  }, [id]);

  useEffect(() => { refreshFolders(); }, [refreshFolders]);

  // Tous les dossiers : scripts + custom (sans doublons)
  const scriptNames = scripts.map(s => s.name);
  const allFolders = [
    ...scriptNames,
    ...customFolders.filter(f => !scriptNames.includes(f)),
  ];

  const loadFolder = async (folder: string) => {
    setLoading(true);
    setOpenFolder(folder);
    try {
      const res = await fetch(`/api/creators/${id}/media?folder=${encodeURIComponent(folder)}`);
      const d = await res.json();
      setItems((d.items ?? []).filter((i: MediaItem) => !i.isDir));
    } catch { setItems([]); }
    setLoading(false);
  };

  const handleUpload = async (files: FileList | File[]) => {
    if (!openFolder) return;
    const arr = Array.from(files);
    for (const file of arr) {
      const form = new FormData();
      form.append("file", file);
      await fetch(`/api/creators/${id}/media?folder=${encodeURIComponent(openFolder)}`, {
        method: "POST", body: form,
      });
      setUploadsToday(n => n + 1);
    }
    loadFolder(openFolder);
  };

  const deleteFile = async (fileName: string) => {
    await fetch(`/api/creators/${id}/media`, {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ folder: openFolder, fileName }),
    });
    setItems(prev => prev.filter(i => i.name !== fileName));
  };

  const deleteFolder = async (folder: string) => {
    if (!confirm(`Supprimer le dossier "${folder}" ?`)) return;
    await fetch(`/api/creators/${id}/media`, {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ folder }),
    });
    setCustomFolders(prev => prev.filter(f => f !== folder));
    if (openFolder === folder) setOpenFolder(null);
  };

  const createFolder = async () => {
    const name = newFolderName.trim().toUpperCase();
    if (!name) return;
    // Upload un fichier .keep pour créer le dossier
    const form = new FormData();
    form.append("file", new Blob([""], { type: "text/plain" }), ".keep");
    await fetch(`/api/creators/${id}/media?folder=${encodeURIComponent(name)}`, {
      method: "POST", body: form,
    });
    setCustomFolders(prev => prev.includes(name) ? prev : [...prev, name]);
    setShowNewFolder(false);
    setNewFolderName("");
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    if (e.dataTransfer.files.length) handleUpload(e.dataTransfer.files);
  };

  const formatSize = (b: number) =>
    b < 1024 ? `${b}B` : b < 1024 * 1024 ? `${(b / 1024).toFixed(0)}KB` : `${(b / 1024 / 1024).toFixed(1)}MB`;
  const isVideo = (name: string) => /\.(mp4|mov|avi|webm|mkv)$/i.test(name);
  const isImage = (name: string) => /\.(jpg|jpeg|png|gif|webp|heic)$/i.test(name);

  return (
    <div className="p-6" style={{ color: "#fff" }}>
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-lg font-bold">Media</h2>
          {openFolder ? (
            <button onClick={() => setOpenFolder(null)}
              className="flex items-center gap-1 text-xs mt-1 hover:text-white transition-all"
              style={{ color: "#6b7280" }}>
              <ArrowLeft size={12} /> Retour aux dossiers
            </button>
          ) : (
            <p className="text-xs mt-1" style={{ color: "#6b7280" }}>
              Ouvre un dossier pour uploader et gérer tes médias.
            </p>
          )}
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs px-3 py-1.5 rounded-lg border"
            style={{ borderColor: "#1e1e2e", color: "#6b7280" }}>
            Uploads aujourd&apos;hui : {uploadsToday} / 500
          </span>
          <button onClick={() => setShowNewFolder(true)}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm border transition-all hover:bg-white/5"
            style={{ borderColor: "#1e1e2e", color: "#9ca3af" }}>
            <Plus size={13} /> Nouveau dossier
          </button>
        </div>
      </div>

      {/* Folder grid */}
      {!openFolder && (
        <div className="grid grid-cols-3 gap-3">
          {allFolders.map(folder => {
            const isScript = scriptNames.includes(folder);
            return (
              <div key={folder}
                className="flex items-center justify-between px-4 py-3 rounded-xl border cursor-pointer hover:border-red-500/30 transition-all group"
                style={{ borderColor: "#1e1e2e", background: "#0f0f1a" }}>
                <button onClick={() => loadFolder(folder)} className="flex items-center gap-3 flex-1 min-w-0">
                  <FolderOpen size={16} style={{ color: "#e11d48", flexShrink: 0 }} />
                  <span className="text-sm font-medium truncate uppercase">{folder}</span>
                </button>
                <div className="flex items-center gap-1">
                  <ChevronRight size={14} style={{ color: "#4b5563" }} />
                  {!isScript && (
                    <button onClick={e => { e.stopPropagation(); deleteFolder(folder); }}
                      className="p-1 rounded hover:bg-white/5 opacity-0 group-hover:opacity-100 transition-all"
                      style={{ color: "#e11d48" }}>
                      <Trash2 size={13} />
                    </button>
                  )}
                </div>
              </div>
            );
          })}
          {allFolders.length === 0 && (
            <div className="col-span-3 flex flex-col items-center justify-center py-20 gap-3">
              <FolderOpen size={32} style={{ color: "#2a2a3e" }} />
              <p className="text-sm" style={{ color: "#4b5563" }}>
                Aucun dossier — crée un dossier ou ajoute des scripts
              </p>
              <button onClick={() => setShowNewFolder(true)}
                className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm"
                style={{ background: "#e11d48", color: "#fff" }}>
                <Plus size={13} /> Créer un dossier
              </button>
            </div>
          )}
        </div>
      )}

      {/* Folder content */}
      {openFolder && (
        <div>
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-semibold uppercase text-sm tracking-wide" style={{ color: "#d1d5db" }}>
              {openFolder}
            </h3>
            <button onClick={() => fileRef.current?.click()}
              className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium"
              style={{ background: "#e11d48", color: "#fff" }}>
              <Upload size={13} /> Upload
            </button>
            <input ref={fileRef} type="file" multiple accept="image/*,video/*" className="hidden"
              onChange={e => e.target.files && handleUpload(e.target.files)} />
          </div>

          {loading ? (
            <div className="flex items-center justify-center py-20" style={{ color: "#4b5563" }}>
              <RefreshCw size={16} className="animate-spin mr-2" /> Chargement...
            </div>
          ) : items.length === 0 ? (
            <div
              onDragOver={e => { e.preventDefault(); setDragOver(true); }}
              onDragLeave={() => setDragOver(false)}
              onDrop={onDrop}
              onClick={() => fileRef.current?.click()}
              className="border-2 border-dashed rounded-xl py-24 flex flex-col items-center justify-center gap-3 cursor-pointer transition-all"
              style={{ borderColor: dragOver ? "#e11d48" : "#1e1e2e", background: dragOver ? "rgba(225,29,72,0.04)" : "transparent" }}>
              <Upload size={28} style={{ color: dragOver ? "#e11d48" : "#4b5563" }} />
              <p className="text-sm font-medium" style={{ color: dragOver ? "#e11d48" : "#4b5563" }}>
                Glisse des fichiers ici ou clique pour uploader
              </p>
              <p className="text-xs" style={{ color: "#374151" }}>Images et vidéos acceptées</p>
            </div>
          ) : (
            <div
              onDragOver={e => { e.preventDefault(); setDragOver(true); }}
              onDragLeave={() => setDragOver(false)}
              onDrop={onDrop}
              className="grid grid-cols-4 gap-3"
              style={{ outline: dragOver ? "2px dashed #e11d48" : "none", borderRadius: 12 }}>
              {items.map(item => (
                <div key={item.name} className="relative group rounded-xl overflow-hidden border"
                  style={{ borderColor: "#1e1e2e", background: "#0f0f1a" }}>
                  {isImage(item.name) && item.url ? (
                    <img src={item.url} alt={item.name} className="w-full h-32 object-cover" />
                  ) : isVideo(item.name) && item.url ? (
                    <video src={item.url} className="w-full h-32 object-cover" />
                  ) : (
                    <div className="w-full h-32 flex items-center justify-center"
                      style={{ background: "#111118" }}>
                      <span className="text-xs font-mono" style={{ color: "#4b5563" }}>
                        {item.name.split(".").pop()?.toUpperCase()}
                      </span>
                    </div>
                  )}
                  <div className="p-2">
                    <p className="text-xs truncate" style={{ color: "#9ca3af" }}>{item.name}</p>
                    <p className="text-xs" style={{ color: "#4b5563" }}>{formatSize(item.size)}</p>
                  </div>
                  <button onClick={() => deleteFile(item.name)}
                    className="absolute top-1.5 right-1.5 w-6 h-6 rounded-full flex items-center justify-center opacity-0 group-hover:opacity-100 transition-all"
                    style={{ background: "#e11d48" }}>
                    <X size={11} color="#fff" />
                  </button>
                </div>
              ))}
              {/* Ajouter plus */}
              <button onClick={() => fileRef.current?.click()}
                className="h-32 rounded-xl border-2 border-dashed flex flex-col items-center justify-center gap-2 hover:border-red-500/40 transition-all"
                style={{ borderColor: "#1e1e2e" }}>
                <Plus size={20} style={{ color: "#4b5563" }} />
                <span className="text-xs" style={{ color: "#4b5563" }}>Ajouter</span>
              </button>
            </div>
          )}
        </div>
      )}

      {/* Modal nouveau dossier */}
      {showNewFolder && (
        <div className="fixed inset-0 z-50 flex items-center justify-center"
          style={{ background: "rgba(0,0,0,0.8)" }}
          onClick={() => setShowNewFolder(false)}>
          <div className="w-full max-w-sm rounded-2xl border p-6"
            style={{ background: "#111118", borderColor: "#1e1e2e" }}
            onClick={e => e.stopPropagation()}>
            <h3 className="font-bold mb-4">Nouveau dossier</h3>
            <input
              value={newFolderName}
              onChange={e => setNewFolderName(e.target.value.toUpperCase())}
              onKeyDown={e => { if (e.key === "Enter") createFolder(); }}
              placeholder="NOM DU DOSSIER"
              autoFocus
              className="w-full px-4 py-2.5 rounded-xl text-sm outline-none uppercase mb-4"
              style={{ background: "#0a0a0f", border: "1px solid #1e1e2e", color: "#fff" }}
            />
            <div className="flex gap-3">
              <button onClick={() => setShowNewFolder(false)}
                className="flex-1 py-2.5 rounded-xl text-sm border"
                style={{ borderColor: "#1e1e2e", color: "#9ca3af" }}>
                Annuler
              </button>
              <button onClick={createFolder}
                className="flex-1 py-2.5 rounded-xl text-sm font-medium"
                style={{ background: "#e11d48", color: "#fff" }}>
                Créer
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
