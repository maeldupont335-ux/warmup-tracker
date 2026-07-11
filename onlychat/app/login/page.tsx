"use client";
import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Eye, EyeOff, ArrowLeft } from "lucide-react";
import { createClient } from "@/lib/supabase-browser";

export default function LoginPage() {
  const router = useRouter();
  const [showPwd, setShowPwd] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true); setError("");
    const supabase = createClient();
    const { error: err } = await supabase.auth.signInWithPassword({ email, password });
    if (err) { setError(err.message); setLoading(false); return; }
    window.location.href = "/dashboard";
  };

  return (
    <div className="min-h-screen flex items-center justify-center px-4" style={{ background: "#0a0a0f", position: "relative" }}>
      {/* Bouton retour page présentation */}
      <Link href="/" style={{ position: "absolute", top: "20px", left: "20px", display: "flex", alignItems: "center", gap: "6px", color: "#9ca3af", fontSize: "14px", fontWeight: 500, padding: "8px 14px", borderRadius: "10px", background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.08)", textDecoration: "none", transition: "all 0.2s" }}
        onMouseEnter={e => (e.currentTarget.style.background = "rgba(255,255,255,0.1)")}
        onMouseLeave={e => (e.currentTarget.style.background = "rgba(255,255,255,0.05)")}>
        <ArrowLeft size={15} />
        Retour
      </Link>
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <Link href="/" className="inline-flex items-center gap-2 mb-6">
            <svg width="40" height="40" viewBox="0 0 88 88" style={{ flexShrink: 0 }}>
              <path d="M8,44 C8,32 18,22 30,26 C24,32 22,38 24,44 C22,50 24,56 30,62 C18,66 8,56 8,44 Z" fill="#f59e0b" opacity="0.6"/>
              <path d="M80,44 C80,32 70,22 58,26 C64,32 66,38 64,44 C66,50 64,56 58,62 C70,66 80,56 80,44 Z" fill="#f59e0b" opacity="0.6"/>
              <circle cx="44" cy="44" r="22" fill="#0a0a0f" stroke="#f59e0b" strokeWidth="2.5"/>
              <text x="33" y="56" fontSize="30" fill="#f59e0b" fontFamily="monospace" fontWeight="900">$</text>
            </svg>
            <span style={{ fontSize: "20px", fontWeight: 800, letterSpacing: "-0.5px", color: "#fff" }}>
              Puls<span style={{ color: "#f59e0b" }}>Chat</span>
              <span style={{ background: "#f59e0b", color: "#0a0a0f", fontSize: "8px", fontWeight: 900, padding: "2px 5px", borderRadius: "4px", marginLeft: "5px", verticalAlign: "middle", position: "relative", top: "-1px" }}>AI</span>
            </span>
          </Link>
          <h1 className="text-2xl font-black text-white mb-2">Bon retour 👋</h1>
          <p className="text-sm" style={{ color: "#6b7280" }}>Connecte-toi à ton espace</p>
        </div>

        <div className="rounded-2xl border p-8" style={{ background: "#111118", borderColor: "#1e1e2e" }}>
          <form onSubmit={handleSubmit} className="space-y-5">
            <div>
              <label className="block text-sm font-medium mb-2 text-white">Email</label>
              <input
                type="email" required value={email} onChange={e => setEmail(e.target.value)}
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
                  type={showPwd ? "text" : "password"} required value={password} onChange={e => setPassword(e.target.value)}
                  placeholder="••••••••"
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
            {error && <p className="text-xs px-3 py-2 rounded-lg" style={{ background: "rgba(239,68,68,0.1)", color: "#f87171" }}>{error}</p>}
            <div className="flex justify-end">
              <a href="#" className="text-xs hover:underline" style={{ color: "#a855f7" }}>Mot de passe oublié ?</a>
            </div>
            <button type="submit" disabled={loading}
              className="w-full py-3 rounded-xl font-bold text-sm transition-all hover:opacity-90 disabled:opacity-60"
              style={{ background: "linear-gradient(135deg,#a855f7,#7c3aed)", color: "#fff" }}>
              {loading ? "Connexion..." : "Se connecter"}
            </button>
          </form>
        </div>

        <p className="text-center text-sm mt-6" style={{ color: "#6b7280" }}>
          Pas encore de compte ?{" "}
          <Link href="/register" className="font-medium hover:underline" style={{ color: "#a855f7" }}>
            Créer un compte
          </Link>
        </p>
      </div>
    </div>
  );
}
