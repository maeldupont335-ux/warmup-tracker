"use client";
import { useState, useRef, useEffect } from "react";
import {
  Upload, CheckCircle, Trash2, Brain, Eye, Star, Plus, FileJson,
  Zap, Send, RadioTower
} from "lucide-react";

interface StyleProfileMeta {
  slug: string;
  name: string;
  totalMessages: number;
  examples: number;
  createdAt: string;
}

interface StyleIndex {
  active: string | null;
  profiles: StyleProfileMeta[];
}

interface ActiveProfile {
  realExamples: { fanMessage: string; yourReply: string }[];
  commonEmojis: string[];
  commonPhrases: string[];
  avgMessageLength: number;
  usesAbbreviations: boolean;
  commonGreetings: string[];
  totalMessagesAnalyzed: number;
  yourName: string;
}

interface Stats {
  totalMessages: number;
  examplesExtracted: number;
  topEmojis: string[];
  commonPhrases: string[];
  avgLength: number;
  usesAbbreviations: boolean;
  commonGreetings: string[];
}

type Tab = "profiles" | "import" | "preview" | "paid";

export default function TrainingPage() {
  const multiFileRef = useRef<HTMLInputElement>(null);
  const [tab, setTab] = useState<Tab>("profiles");

  // Créateurs
  const [creators, setCreators] = useState<{ id: string; name: string }[]>([]);
  const [selectedCreatorId, setSelectedCreatorId] = useState("");

  // Index multi-profils
  const [styleIndex, setStyleIndex] = useState<StyleIndex>({ active: null, profiles: [] });
  const [activeProfile, setActiveProfile] = useState<ActiveProfile | null>(null);

  // Import
  const [yourName, setYourName] = useState("");
  const [profileName, setProfileName] = useState("");
  const [pendingFiles, setPendingFiles] = useState<File[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [stats, setStats] = useState<Stats | null>(null);
  const [availableNames, setAvailableNames] = useState<string[]>([]);
  const [suggestedName, setSuggestedName] = useState("");

  // Paid media
  const [paidChatId, setPaidChatId] = useState("");
  const [paidStars, setPaidStars] = useState("50");
  const [paidType, setPaidType] = useState("photo");
  const [paidUrl, setPaidUrl] = useState("");
  const [paidCaption, setPaidCaption] = useState("");
  const [paidLoading, setPaidLoading] = useState(false);
  const [paidResult, setPaidResult] = useState("");

  useEffect(() => {
    fetch("/api/creators").then(r => r.json()).then(d => {
      if (d.creators?.length) {
        setCreators(d.creators.map((c: { id: string; name: string }) => ({ id: c.id, name: c.name })));
        setSelectedCreatorId(d.creators[0].id);
      }
    });
  }, []);

  const loadIndex = async (creatorId: string) => {
    if (!creatorId) return;
    const d = await fetch(`/api/training?creatorId=${creatorId}`).then(r => r.json());
    setStyleIndex(d.index ?? { active: null, profiles: [] });
    setActiveProfile(d.activeProfile ?? null);
    setStats(d.activeProfile ? {
      totalMessages: d.activeProfile.totalMessagesAnalyzed,
      examplesExtracted: d.activeProfile.realExamples?.length ?? 0,
      topEmojis: d.activeProfile.commonEmojis?.slice(0, 8) ?? [],
      commonPhrases: d.activeProfile.commonPhrases?.slice(0, 6) ?? [],
      avgLength: d.activeProfile.avgMessageLength ?? 0,
      usesAbbreviations: d.activeProfile.usesAbbreviations ?? false,
      commonGreetings: d.activeProfile.commonGreetings?.slice(0, 4) ?? [],
    } : null);
  };

  useEffect(() => {
    if (selectedCreatorId) loadIndex(selectedCreatorId);
  }, [selectedCreatorId]);

  const handleSetActive = async (slug: string) => {
    await fetch("/api/training", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ creatorId: selectedCreatorId, activeSlug: slug }),
    });
    loadIndex(selectedCreatorId);
  };

  const handleDeleteProfile = async (slug: string) => {
    await fetch(`/api/training?creatorId=${selectedCreatorId}&slug=${slug}`, { method: "DELETE" });
    loadIndex(selectedCreatorId);
  };

  const addFiles = (files: FileList | null) => {
    if (!files) return;
    const jsonFiles = Array.from(files).filter(f => f.name.endsWith(".json"));
    setPendingFiles(prev => {
      const existing = new Set(prev.map(f => f.name + f.size));
      return [...prev, ...jsonFiles.filter(f => !existing.has(f.name + f.size))];
    });
    setError("");
  };

  const analyzeFiles = async () => {
    if (pendingFiles.length === 0 || !selectedCreatorId) return;
    setLoading(true);
    setError("");
    setAvailableNames([]);
    setSuggestedName("");

    const nameHint = yourName.trim();
    let allMessages: { type: string; from?: string; text: string }[] = [];

    for (const file of pendingFiles) {
      let parsed: { messages?: unknown[]; realExamples?: unknown[]; yourName?: string; name?: string } | null = null;
      try {
        parsed = JSON.parse(await file.text());
      } catch {
        setError(`Fichier invalide : ${file.name}`);
        setLoading(false);
        return;
      }

      // Profil pré-analysé → upload direct
      if (parsed?.realExamples && Array.isArray(parsed.realExamples)) {
        const name = profileName.trim() || (parsed as { name?: string }).name || file.name.replace(".json", "");
        const res = await fetch("/api/training", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ preAnalyzed: parsed, creatorId: selectedCreatorId, profileName: name }),
        });
        const d = await res.json();
        if (res.ok) {
          setStats(d.stats);
          await loadIndex(selectedCreatorId);
          setPendingFiles([]);
          setProfileName("");
          setTab("profiles");
        } else {
          setError(d.error ?? "Erreur upload profil");
        }
        setLoading(false);
        return;
      }

      if (!parsed?.messages || !Array.isArray(parsed.messages)) continue;
      const msgs = (parsed.messages as { type?: string; from?: string; text?: string | unknown[] }[])
        .filter(m => m.from)
        .map(m => ({
          type: "message",
          from: m.from ?? "",
          text: typeof m.text === "string" ? m.text : Array.isArray(m.text)
            ? (m.text as { text?: string }[]).map(p => p?.text ?? "").join("") : "",
        }));
      allMessages = allMessages.concat(msgs);
    }

    if (allMessages.length === 0) {
      setError("Aucun message trouvé. Vérifie que le fichier est un export Telegram JSON.");
      setLoading(false);
      return;
    }

    const freq: Record<string, number> = {};
    for (const m of allMessages) if (m.from) freq[m.from] = (freq[m.from] ?? 0) + 1;
    const sortedNames = Object.entries(freq).sort((a, b) => b[1] - a[1]);
    const detectedN = nameHint
      ? (Object.keys(freq).find(n => n.toLowerCase().includes(nameHint.toLowerCase())) ?? sortedNames[0]?.[0] ?? "")
      : sortedNames[0]?.[0] ?? "";

    if (!detectedN || allMessages.filter(m => m.from === detectedN).length === 0) {
      setAvailableNames(sortedNames.slice(0, 15).map(([n]) => n));
      setSuggestedName(sortedNames[0]?.[0] ?? "");
      setError("Sélectionne ton prénom dans la liste ci-dessous.");
      setLoading(false);
      return;
    }

    const name = profileName.trim() || detectedN;
    const CHUNK = 8000;
    let lastStats: Stats | null = null;

    for (let c = 0; c * CHUNK < allMessages.length; c++) {
      const chunk = allMessages.slice(c * CHUNK, (c + 1) * CHUNK);
      try {
        const res = await fetch("/api/training", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            exportData: { messages: chunk },
            yourName: detectedN,
            profileName: name,
            accumulate: c > 0,
            creatorId: selectedCreatorId,
          }),
        });
        const d = await res.json();
        if (res.ok) lastStats = d.stats;
      } catch { /* continue */ }
    }

    await loadIndex(selectedCreatorId);
    if (lastStats) setStats(lastStats);
    setPendingFiles([]);
    setProfileName("");
    setTab("profiles");
    setLoading(false);
  };

  const handleSendPaid = async () => {
    setPaidLoading(true); setPaidResult("");
    try {
      const res = await fetch("/api/telegram/paid-media", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ chatId: paidChatId, starCount: parseInt(paidStars), mediaType: paidType, mediaUrl: paidUrl, caption: paidCaption }),
      });
      const d = await res.json();
      if (!res.ok) throw new Error(d.error);
      setPaidResult(`✅ Média payant envoyé ! Message ID : ${d.messageId}`);
    } catch (e: unknown) { setPaidResult(`❌ ${(e as Error).message}`); }
    finally { setPaidLoading(false); }
  };

  const tabs = [
    { key: "profiles" as Tab, label: "Mes styles IA", icon: Brain },
    { key: "import" as Tab, label: "Importer", icon: Upload },
    { key: "preview" as Tab, label: "Aperçu actif", icon: Eye },
    { key: "paid" as Tab, label: "Média payant ⭐", icon: Star },
  ];

  return (
    <div className="p-8" style={{ color: "#fff" }}>

      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-black flex items-center gap-2">
          <Brain size={24} style={{ color: "#a855f7" }} />
          Entraîner l&apos;IA sur ton style
        </h1>
        <p className="text-sm mt-1" style={{ color: "#6b7280" }}>
          Crée plusieurs styles IA et choisis lequel chaque créateur utilise
        </p>
      </div>

      {/* Sélecteur de créateur */}
      {creators.length > 0 && (
        <div className="mb-6 flex items-center gap-3 flex-wrap">
          <span className="text-sm font-medium" style={{ color: "#9ca3af" }}>Créateur :</span>
          {creators.map(c => (
            <button key={c.id} onClick={() => setSelectedCreatorId(c.id)}
              className="px-4 py-2 rounded-xl text-sm font-bold transition-all"
              style={{
                background: selectedCreatorId === c.id ? "linear-gradient(135deg,#a855f7,#7c3aed)" : "#111118",
                color: selectedCreatorId === c.id ? "#fff" : "#6b7280",
                border: `1px solid ${selectedCreatorId === c.id ? "transparent" : "#1e1e2e"}`,
              }}>
              {c.name}
            </button>
          ))}
          {selectedCreatorId && (
            <span className="text-xs px-2 py-1 rounded-full" style={{
              background: styleIndex.active ? "rgba(16,185,129,0.1)" : "rgba(239,68,68,0.1)",
              color: styleIndex.active ? "#10b981" : "#ef4444",
            }}>
              {styleIndex.active ? `✓ ${styleIndex.profiles.length} style(s)` : "aucun style"}
            </span>
          )}
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-2 mb-6 p-1 rounded-xl w-fit flex-wrap" style={{ background: "#111118", border: "1px solid #1e1e2e" }}>
        {tabs.map(t => (
          <button key={t.key} onClick={() => setTab(t.key)}
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all"
            style={tab === t.key ? { background: "linear-gradient(135deg,#a855f7,#7c3aed)", color: "#fff" } : { color: "#6b7280" }}>
            <t.icon size={14} />{t.label}
          </button>
        ))}
      </div>

      {/* ─── TAB PROFILS ─── */}
      {tab === "profiles" && (
        <div className="max-w-2xl space-y-4">

          {styleIndex.profiles.length === 0 ? (
            <div className="rounded-2xl border p-8 text-center" style={{ background: "#111118", borderColor: "#1e1e2e" }}>
              <Brain size={40} style={{ color: "#4b5563", margin: "0 auto 12px" }} />
              <p className="font-medium" style={{ color: "#6b7280" }}>Aucun style IA créé pour ce créateur</p>
              <p className="text-sm mt-1 mb-4" style={{ color: "#4b5563" }}>Importe des conversations Telegram pour entraîner l&apos;IA à parler comme toi</p>
              <button onClick={() => setTab("import")}
                className="px-6 py-3 rounded-xl font-bold text-sm"
                style={{ background: "linear-gradient(135deg,#a855f7,#7c3aed)", color: "#fff" }}>
                + Créer mon premier style
              </button>
            </div>
          ) : (
            <>
              <div className="text-sm font-medium mb-4" style={{ color: "#9ca3af" }}>
                {styleIndex.profiles.length} style(s) disponible(s) — clique <strong style={{ color: "#a855f7" }}>Activer</strong> pour choisir lequel le bot utilise
              </div>
              {styleIndex.profiles.map(p => {
                const isActive = styleIndex.active === p.slug;
                return (
                  <div key={p.slug} className="rounded-2xl border p-5 transition-all"
                    style={{
                      background: isActive ? "rgba(168,85,247,0.05)" : "#111118",
                      borderColor: isActive ? "rgba(168,85,247,0.4)" : "#1e1e2e",
                    }}>
                    <div className="flex items-center justify-between">
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="font-bold">{p.name}</span>
                          {isActive && (
                            <span className="px-2 py-0.5 rounded-full text-xs font-bold"
                              style={{ background: "rgba(168,85,247,0.2)", color: "#a855f7" }}>
                              ✓ ACTIF
                            </span>
                          )}
                        </div>
                        <div className="text-xs mt-1 flex gap-3" style={{ color: "#6b7280" }}>
                          <span>{p.totalMessages.toLocaleString()} messages</span>
                          <span>{p.examples} exemples</span>
                          <span>{new Date(p.createdAt).toLocaleDateString("fr-FR")}</span>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        {!isActive && (
                          <button onClick={() => handleSetActive(p.slug)}
                            className="px-4 py-2 rounded-xl text-sm font-bold transition-all"
                            style={{ background: "linear-gradient(135deg,#a855f7,#7c3aed)", color: "#fff" }}>
                            <RadioTower size={12} className="inline mr-1" />
                            Activer
                          </button>
                        )}
                        <button onClick={() => handleDeleteProfile(p.slug)}
                          className="p-2 rounded-xl transition-all hover:bg-red-500/10"
                          style={{ color: "#4b5563" }}>
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </div>
                  </div>
                );
              })}
              <button onClick={() => setTab("import")}
                className="flex items-center gap-2 px-5 py-3 rounded-xl text-sm font-bold border transition-all hover:bg-purple-500/10 mt-2"
                style={{ borderColor: "rgba(168,85,247,0.3)", color: "#a855f7" }}>
                <Plus size={16} />
                Ajouter un nouveau style
              </button>
            </>
          )}
        </div>
      )}

      {/* ─── TAB IMPORT ─── */}
      {tab === "import" && (
        <div className="max-w-2xl space-y-6">

          <div className="rounded-2xl border p-5" style={{ background: "#111118", borderColor: "#1e1e2e" }}>
            <h2 className="font-bold mb-3 flex items-center gap-2">
              <FileJson size={16} style={{ color: "#a855f7" }} />
              Comment exporter depuis Telegram Desktop
            </h2>
            <div className="space-y-2">
              {[
                "Ouvre Telegram Desktop sur PC",
                "Va dans Paramètres → Avancé → Exporter les données Telegram",
                "Coche uniquement « Messages privés » → Format JSON",
                "Décochez les médias (mets taille limite à 0 MB)",
                "Clique Exporter et attends la fin",
                "Importe les fichiers result.json ci-dessous",
              ].map((step, i) => (
                <div key={i} className="flex items-start gap-3 text-sm">
                  <span className="w-5 h-5 rounded-full flex-shrink-0 flex items-center justify-center text-xs font-bold mt-0.5"
                    style={{ background: "rgba(168,85,247,0.2)", color: "#a855f7" }}>
                    {i + 1}
                  </span>
                  <span style={{ color: "#d1d5db" }}>{step}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Nom du profil */}
          <div className="rounded-2xl border p-5" style={{ background: "#111118", borderColor: "#1e1e2e" }}>
            <label className="block text-sm font-medium mb-2">
              Nom du style IA <span className="ml-2 text-xs font-normal" style={{ color: "#6b7280" }}>(ex: Pauline V2, Lisa naturelle...)</span>
            </label>
            <input value={profileName} onChange={e => setProfileName(e.target.value)}
              placeholder="Ex: Pauline V2"
              className="w-full px-4 py-3 rounded-xl text-sm outline-none"
              style={{ background: "#0a0a0f", border: "1px solid #1e1e2e", color: "#fff" }} />

            <label className="block text-sm font-medium mt-4 mb-2">
              Ton prénom dans Telegram
              <span className="ml-2 text-xs font-normal" style={{ color: "#6b7280" }}>(facultatif — détection auto)</span>
            </label>
            <input value={yourName} onChange={e => setYourName(e.target.value)}
              placeholder="Ex: Paulinee💞, Lisa, MANAGER..."
              className="w-full px-4 py-3 rounded-xl text-sm outline-none"
              style={{ background: "#0a0a0f", border: "1px solid #1e1e2e", color: "#fff" }} />

            {availableNames.length > 0 && (
              <div className="mt-3 p-3 rounded-xl text-sm" style={{ background: "rgba(245,158,11,0.08)", border: "1px solid rgba(245,158,11,0.2)" }}>
                <div className="text-xs mb-2" style={{ color: "#fbbf24" }}>Clique sur ton prénom :</div>
                <div className="flex flex-wrap gap-2">
                  {availableNames.map(n => (
                    <button key={n} onClick={() => { setYourName(n); setAvailableNames([]); setSuggestedName(""); setError(""); }}
                      className="px-3 py-1 rounded-lg text-sm font-medium transition-all"
                      style={{
                        background: n === suggestedName ? "rgba(168,85,247,0.2)" : "rgba(255,255,255,0.05)",
                        color: n === suggestedName ? "#a855f7" : "#d1d5db",
                        border: `1px solid ${n === suggestedName ? "rgba(168,85,247,0.4)" : "#2a2a3e"}`,
                      }}>
                      {n} {n === suggestedName && "← suggéré"}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Upload zone */}
          <div className="rounded-2xl border p-5" style={{ background: "#111118", borderColor: "#1e1e2e" }}>
            <div className="flex items-center justify-between mb-3">
              <h2 className="font-bold text-sm">Fichiers JSON</h2>
              {pendingFiles.length > 0 && (
                <span className="text-xs px-2 py-0.5 rounded-full" style={{ background: "rgba(168,85,247,0.15)", color: "#a855f7" }}>
                  {pendingFiles.length} fichier{pendingFiles.length > 1 ? "s" : ""}
                </span>
              )}
            </div>

            <div onClick={() => multiFileRef.current?.click()}
              onDragOver={e => e.preventDefault()}
              onDrop={e => { e.preventDefault(); addFiles(e.dataTransfer.files); }}
              className="border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-all hover:border-purple-500/50"
              style={{ borderColor: "#2a2a3e" }}>
              <Upload size={32} style={{ color: "#4b5563", margin: "0 auto 8px" }} />
              <p className="text-sm font-medium" style={{ color: "#9ca3af" }}>Glisse tes fichiers ici ou clique pour choisir</p>
              <p className="text-xs mt-1" style={{ color: "#4b5563" }}>result.json, profils pré-analysés (.json)</p>
              <input ref={multiFileRef} type="file" multiple accept=".json" className="hidden"
                onChange={e => addFiles(e.target.files)} />
            </div>

            {pendingFiles.length > 0 && (
              <div className="mt-3 space-y-1">
                {pendingFiles.map((f, i) => (
                  <div key={i} className="flex items-center justify-between px-3 py-2 rounded-lg text-sm"
                    style={{ background: "#0a0a0f" }}>
                    <span style={{ color: "#d1d5db" }}>{f.name}</span>
                    <div className="flex items-center gap-2">
                      <span style={{ color: "#6b7280" }}>{(f.size / 1024 / 1024).toFixed(1)} MB</span>
                      <button onClick={() => setPendingFiles(prev => prev.filter((_, j) => j !== i))}
                        style={{ color: "#4b5563" }}>×</button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {error && (
            <div className="p-4 rounded-xl text-sm" style={{ background: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.2)", color: "#fca5a5" }}>
              {error}
            </div>
          )}

          <button onClick={analyzeFiles} disabled={loading || pendingFiles.length === 0 || !selectedCreatorId}
            className="w-full py-4 rounded-xl font-bold text-sm transition-all flex items-center justify-center gap-2"
            style={{
              background: loading || pendingFiles.length === 0 ? "#1e1e2e" : "linear-gradient(135deg,#a855f7,#7c3aed)",
              color: loading || pendingFiles.length === 0 ? "#4b5563" : "#fff",
            }}>
            {loading ? (
              <><div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />Analyse en cours...</>
            ) : (
              <><Zap size={16} />Analyser et créer le style IA</>
            )}
          </button>
        </div>
      )}

      {/* ─── TAB APERÇU ─── */}
      {tab === "preview" && (
        <div className="max-w-2xl space-y-6">
          {!activeProfile ? (
            <div className="rounded-2xl border p-8 text-center" style={{ background: "#111118", borderColor: "#1e1e2e" }}>
              <p style={{ color: "#6b7280" }}>Aucun profil actif — active un style dans l&apos;onglet <strong>Mes styles IA</strong></p>
            </div>
          ) : (
            <>
              <div className="p-4 rounded-2xl border" style={{ background: "rgba(16,185,129,0.05)", borderColor: "rgba(16,185,129,0.25)" }}>
                <div className="flex items-center gap-2 mb-2">
                  <CheckCircle size={16} style={{ color: "#10b981" }} />
                  <span className="font-bold text-sm" style={{ color: "#10b981" }}>
                    Style actif — {activeProfile.yourName}
                  </span>
                </div>
                <div className="flex gap-4 text-xs" style={{ color: "#9ca3af" }}>
                  <span><strong style={{ color: "#fff" }}>{activeProfile.totalMessagesAnalyzed?.toLocaleString()}</strong> messages</span>
                  <span><strong style={{ color: "#fff" }}>{activeProfile.realExamples?.length}</strong> exemples</span>
                  <span>moy. <strong style={{ color: "#fff" }}>{activeProfile.avgMessageLength}</strong> car.</span>
                </div>
                <div className="mt-2 flex flex-wrap gap-1">
                  {activeProfile.commonEmojis?.map((e, i) => <span key={i} className="text-lg">{e}</span>)}
                  {activeProfile.usesAbbreviations && (
                    <span className="px-2 py-0.5 rounded-full text-xs ml-2" style={{ background: "rgba(168,85,247,0.15)", color: "#a855f7" }}>
                      abréviations SMS
                    </span>
                  )}
                </div>
              </div>

              {activeProfile.commonGreetings?.length > 0 && (
                <div className="rounded-2xl border p-5" style={{ background: "#111118", borderColor: "#1e1e2e" }}>
                  <h3 className="font-bold text-sm mb-3" style={{ color: "#a855f7" }}>Salutations typiques</h3>
                  <div className="space-y-2">
                    {activeProfile.commonGreetings.map((g, i) => (
                      <div key={i} className="px-3 py-2 rounded-xl text-sm" style={{ background: "#0a0a0f", color: "#d1d5db" }}>
                        &ldquo;{g}&rdquo;
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {activeProfile.commonPhrases?.length > 0 && (
                <div className="rounded-2xl border p-5" style={{ background: "#111118", borderColor: "#1e1e2e" }}>
                  <h3 className="font-bold text-sm mb-3" style={{ color: "#a855f7" }}>Phrases caractéristiques</h3>
                  <div className="flex flex-wrap gap-2">
                    {activeProfile.commonPhrases.map((p, i) => (
                      <span key={i} className="px-3 py-1 rounded-full text-xs" style={{ background: "rgba(168,85,247,0.1)", color: "#c084fc", border: "1px solid rgba(168,85,247,0.2)" }}>
                        {p}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {activeProfile.realExamples?.length > 0 && (
                <div className="rounded-2xl border p-5" style={{ background: "#111118", borderColor: "#1e1e2e" }}>
                  <h3 className="font-bold text-sm mb-3" style={{ color: "#a855f7" }}>
                    Exemples de conversations injectés ({activeProfile.realExamples.length})
                  </h3>
                  <div className="space-y-3 max-h-96 overflow-y-auto">
                    {activeProfile.realExamples.slice(0, 10).map((ex, i) => (
                      <div key={i} className="space-y-1">
                        <div className="px-3 py-2 rounded-xl text-sm" style={{ background: "#0a0a0f", color: "#9ca3af" }}>
                          Fan : {ex.fanMessage}
                        </div>
                        <div className="px-3 py-2 rounded-xl text-sm ml-4" style={{ background: "rgba(168,85,247,0.1)", color: "#d1d5db" }}>
                          Toi : {ex.yourReply}
                        </div>
                      </div>
                    ))}
                    {activeProfile.realExamples.length > 10 && (
                      <p className="text-xs text-center" style={{ color: "#4b5563" }}>
                        + {activeProfile.realExamples.length - 10} autres exemples injectés dans l&apos;IA
                      </p>
                    )}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* ─── TAB PAID ─── */}
      {tab === "paid" && (
        <div className="max-w-lg space-y-5">
          <div className="rounded-2xl border p-5" style={{ background: "#111118", borderColor: "#1e1e2e" }}>
            <h2 className="font-bold mb-4 flex items-center gap-2">
              <Star size={16} style={{ color: "#f59e0b" }} />
              Envoyer un média payant manuellement
            </h2>
            <div className="space-y-3">
              {[
                { label: "Chat ID du fan", value: paidChatId, set: setPaidChatId, placeholder: "ex: 123456789" },
                { label: "Prix (Stars)", value: paidStars, set: setPaidStars, placeholder: "50" },
                { label: "URL du média", value: paidUrl, set: setPaidUrl, placeholder: "https://..." },
                { label: "Légende (optionnel)", value: paidCaption, set: setPaidCaption, placeholder: "Texte accompagnant le média..." },
              ].map(f => (
                <div key={f.label}>
                  <label className="block text-xs font-medium mb-1" style={{ color: "#6b7280" }}>{f.label}</label>
                  <input value={f.value} onChange={e => f.set(e.target.value)} placeholder={f.placeholder}
                    className="w-full px-4 py-3 rounded-xl text-sm outline-none"
                    style={{ background: "#0a0a0f", border: "1px solid #1e1e2e", color: "#fff" }} />
                </div>
              ))}
              <div>
                <label className="block text-xs font-medium mb-1" style={{ color: "#6b7280" }}>Type de média</label>
                <select value={paidType} onChange={e => setPaidType(e.target.value)}
                  className="w-full px-4 py-3 rounded-xl text-sm outline-none"
                  style={{ background: "#0a0a0f", border: "1px solid #1e1e2e", color: "#fff" }}>
                  <option value="photo">Photo</option>
                  <option value="video">Vidéo</option>
                </select>
              </div>
            </div>
            <button onClick={handleSendPaid} disabled={paidLoading}
              className="w-full mt-4 py-3 rounded-xl font-bold text-sm flex items-center justify-center gap-2"
              style={{ background: "linear-gradient(135deg,#f59e0b,#d97706)", color: "#fff" }}>
              {paidLoading ? <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" /> : <Send size={14} />}
              Envoyer le média payant
            </button>
            {paidResult && <p className="mt-3 text-sm" style={{ color: paidResult.startsWith("✅") ? "#10b981" : "#ef4444" }}>{paidResult}</p>}
          </div>
        </div>
      )}
    </div>
  );
}
