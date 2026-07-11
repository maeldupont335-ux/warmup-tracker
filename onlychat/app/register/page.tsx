"use client";
import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { MessageCircle, Eye, EyeOff, CheckCircle } from "lucide-react";
import { createClient } from "@/lib/supabase-browser";

export default function RegisterPage() {
  const router = useRouter();
  const [showPwd, setShowPwd] = useState(false);
  const [step, setStep] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [form, setForm] = useState({ name: "", email: "", password: "", type: "creator" });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (step === 1) { setStep(2); return; }
    setLoading(true); setError("");
    const supabase = createClient();
    const { error: err } = await supabase.auth.signUp({
      email: form.email,
      password: form.password,
      options: { data: { name: form.name, type: form.type } },
    });
    if (err) { setError(err.message); setLoading(false); return; }
    window.location.href = "/dashboard";
  };

  return (
    <div className="min-h-screen flex items-center justify-center px-4" style={{ background: "#0a0a0f" }}>
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <Link href="/" className="inline-flex items-center gap-2 mb-6">
            <div className="w-9 h-9 rounded-xl flex items-center justify-center"
              style={{ background: "linear-gradient(135deg,#a855f7,#7c3aed)" }}>
              <MessageCircle size={18} className="text-white" />
            </div>
            <span className="font-bold text-xl">PulsChat<span style={{ color: "#a855f7" }}> AI</span></span>
          </Link>
          <h1 className="text-2xl font-black text-white mb-2">Crée ton compte</h1>
          <p className="text-sm" style={{ color: "#6b7280" }}>Gratuit • Pas de carte bancaire</p>
        </div>

        {/* Steps */}
        <div className="flex items-center gap-2 mb-6">
          {[1, 2].map((s) => (
            <div key={s} className="flex-1 h-1 rounded-full transition-all"
              style={{ background: step >= s ? "linear-gradient(135deg,#a855f7,#7c3aed)" : "#1e1e2e" }} />
          ))}
        </div>

        <div className="rounded-2xl border p-8" style={{ background: "#111118", borderColor: "#1e1e2e" }}>
          <form onSubmit={handleSubmit} className="space-y-5">
            {step === 1 ? (
              <>
                <div>
                  <label className="block text-sm font-medium mb-2 text-white">Ton prénom ou pseudo</label>
                  <input
                    type="text" required value={form.name} onChange={e => setForm({ ...form, name: e.target.value })}
                    placeholder="Alexya, Studio X..."
                    className="w-full px-4 py-3 rounded-xl text-sm outline-none transition-all"
                    style={{ background: "#0a0a0f", border: "1px solid #1e1e2e", color: "#fff" }}
                    onFocus={e => e.target.style.borderColor = "#a855f7"}
                    onBlur={e => e.target.style.borderColor = "#1e1e2e"}
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-2 text-white">Email</label>
                  <input
                    type="email" required value={form.email} onChange={e => setForm({ ...form, email: e.target.value })}
                    placeholder="toi@example.com"
                    className="w-full px-4 py-3 rounded-xl text-sm outline-none transition-all"
                    style={{ background: "#0a0a0f", border: "1px solid #1e1e2e", color: "#fff" }}
                    onFocus={e => e.target.style.borderColor = "#a855f7"}
                    onBlur={e => e.target.style.borderColor = "#1e1e2e"}
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-2 text-white">Mot de passe</label>
                  <div className="relative">
                    <input
                      type={showPwd ? "text" : "password"} required value={form.password}
                      onChange={e => setForm({ ...form, password: e.target.value })}
                      placeholder="Min. 8 caractères"
                      className="w-full px-4 py-3 rounded-xl text-sm outline-none transition-all pr-11"
                      style={{ background: "#0a0a0f", border: "1px solid #1e1e2e", color: "#fff" }}
                      onFocus={e => e.target.style.borderColor = "#a855f7"}
                      onBlur={e => e.target.style.borderColor = "#1e1e2e"}
                    />
                    <button type="button" onClick={() => setShowPwd(!showPwd)}
                      className="absolute right-3 top-1/2 -translate-y-1/2" style={{ color: "#6b7280" }}>
                      {showPwd ? <EyeOff size={16} /> : <Eye size={16} />}
                    </button>
                  </div>
                </div>
              </>
            ) : (
              <>
                <div>
                  <label className="block text-sm font-medium mb-3 text-white">Tu es...</label>
                  <div className="grid grid-cols-2 gap-3">
                    {[
                      { value: "creator", label: "Créatrice solo", emoji: "👤" },
                      { value: "agency", label: "Agence", emoji: "🏢" },
                    ].map((t) => (
                      <button key={t.value} type="button"
                        onClick={() => setForm({ ...form, type: t.value })}
                        className="p-4 rounded-xl border text-center transition-all"
                        style={{
                          background: form.type === t.value ? "rgba(168,85,247,0.1)" : "#0a0a0f",
                          borderColor: form.type === t.value ? "#a855f7" : "#1e1e2e",
                          color: form.type === t.value ? "#a855f7" : "#9ca3af",
                        }}>
                        <div className="text-2xl mb-1">{t.emoji}</div>
                        <div className="text-sm font-medium">{t.label}</div>
                      </button>
                    ))}
                  </div>
                </div>
                <div className="p-4 rounded-xl" style={{ background: "rgba(168,85,247,0.05)", border: "1px solid rgba(168,85,247,0.15)" }}>
                  <div className="text-sm font-medium mb-2 text-white">Inclus dans l&apos;essai gratuit :</div>
                  {["IA chat 24/7", "Vente PPV auto", "Analytics", "14 jours sans engagement"].map(f => (
                    <div key={f} className="flex items-center gap-2 text-sm mt-1.5" style={{ color: "#9ca3af" }}>
                      <CheckCircle size={12} style={{ color: "#a855f7" }} /> {f}
                    </div>
                  ))}
                </div>
              </>
            )}
            {error && <p className="text-xs px-3 py-2 rounded-lg" style={{ background: "rgba(239,68,68,0.1)", color: "#f87171" }}>{error}</p>}
            <button type="submit" disabled={loading}
              className="w-full py-3 rounded-xl font-bold text-sm transition-all hover:opacity-90 disabled:opacity-60"
              style={{ background: "linear-gradient(135deg,#a855f7,#7c3aed)", color: "#fff" }}>
              {loading ? "Création..." : step === 1 ? "Continuer →" : "Créer mon compte"}
            </button>
          </form>
        </div>

        <p className="text-center text-sm mt-6" style={{ color: "#6b7280" }}>
          Déjà un compte ?{" "}
          <Link href="/login" className="font-medium hover:underline" style={{ color: "#a855f7" }}>
            Se connecter
          </Link>
        </p>
      </div>
    </div>
  );
}
