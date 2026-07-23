"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import {
  Zap, TrendingUp, Clock, Globe, Shield, BarChart3,
  MessageCircle, DollarSign, Users, Star, ChevronRight, CheckCircle, Bot, Sparkles, ArrowRight,
} from "lucide-react";

/* ── Animated counter ── */
function Counter({ target, suffix = "" }: { target: number; suffix?: string }) {
  const [count, setCount] = useState(0);
  const ref = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const obs = new IntersectionObserver(([e]) => {
      if (!e.isIntersecting) return;
      obs.disconnect();
      let start = 0;
      const step = target / 60;
      const t = setInterval(() => {
        start += step;
        if (start >= target) { setCount(target); clearInterval(t); } else setCount(Math.floor(start));
      }, 16);
    }, { threshold: 0.5 });
    obs.observe(el);
    return () => obs.disconnect();
  }, [target]);
  return <span ref={ref}>{count}{suffix}</span>;
}

/* ── Fade-in on scroll ── */
function Reveal({ children, delay = 0, className = "" }: { children: React.ReactNode; delay?: number; className?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const [vis, setVis] = useState(false);
  useEffect(() => {
    const el = ref.current; if (!el) return;
    const obs = new IntersectionObserver(([e]) => { if (e.isIntersecting) { setVis(true); obs.disconnect(); } }, { threshold: 0.1 });
    obs.observe(el);
    return () => obs.disconnect();
  }, []);
  return (
    <div ref={ref} className={className} style={{ opacity: vis ? 1 : 0, transform: vis ? "translateY(0)" : "translateY(32px)", transition: `opacity 0.7s ease ${delay}ms, transform 0.7s ease ${delay}ms` }}>
      {children}
    </div>
  );
}

/* ── Floating orbs background ── */
function Orbs() {
  return (
    <div style={{ position: "absolute", inset: 0, overflow: "hidden", pointerEvents: "none" }}>
      <div style={{ position: "absolute", top: "-20%", left: "50%", transform: "translateX(-50%)", width: "800px", height: "800px", borderRadius: "50%", background: "radial-gradient(circle, rgba(245,158,11,0.12) 0%, transparent 70%)", animation: "lp-pulse6s ease-in-out infinite" }} />
      <div style={{ position: "absolute", top: "20%", right: "-10%", width: "400px", height: "400px", borderRadius: "50%", background: "radial-gradient(circle, rgba(168,85,247,0.08) 0%, transparent 70%)", animation: "lp-pulse8s ease-in-out infinite 2s" }} />
      <div style={{ position: "absolute", bottom: "10%", left: "-5%", width: "300px", height: "300px", borderRadius: "50%", background: "radial-gradient(circle, rgba(236,72,153,0.07) 0%, transparent 70%)", animation: "lp-pulse7s ease-in-out infinite 4s" }} />
    </div>
  );
}

/* ── Chat bubble simulation ── */
function ChatDemo() {
  const messages = [
    { side: "fan", text: "Salut, t'as du nouveau contenu ? 🔥" },
    { side: "bot", text: "Ohhh oui... tu arrives au bon moment 😏" },
    { side: "bot", text: "J'ai quelque chose de très spécial pour toi ✨" },
    { side: "fan", text: "C'est combien ?" },
    { side: "bot", text: "Pour toi je fais un prix spécial 💛" },
  ];
  const [shown, setShown] = useState(0);
  useEffect(() => {
    if (shown >= messages.length) return;
    const t = setTimeout(() => setShown(s => s + 1), shown === 0 ? 800 : 1400);
    return () => clearTimeout(t);
  }, [shown, messages.length]);
  return (
    <div style={{ background: "#0e0e1a", border: "1px solid #1e1e35", borderRadius: "20px", padding: "20px", maxWidth: "340px", margin: "0 auto" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "16px", paddingBottom: "12px", borderBottom: "1px solid #1e1e35" }}>
        <div style={{ width: "32px", height: "32px", borderRadius: "50%", background: "linear-gradient(135deg,#f59e0b,#d97706)", display: "flex", alignItems: "center", justifyContent: "center" }}>
          <Bot size={16} color="#0e0e1a" />
        </div>
        <div>
          <div style={{ fontSize: "13px", fontWeight: 700, color: "#fff" }}>PulsChat AI</div>
          <div style={{ fontSize: "11px", color: "#10b981", display: "flex", alignItems: "center", gap: "4px" }}>
            <span style={{ width: "6px", height: "6px", borderRadius: "50%", background: "#10b981", display: "inline-block", animation: "lp-pulse2s infinite" }} />
            En ligne • répond en 8s
          </div>
        </div>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: "8px", minHeight: "160px" }}>
        {messages.slice(0, shown).map((m, i) => (
          <div key={i} style={{ display: "flex", justifyContent: m.side === "bot" ? "flex-start" : "flex-end", animation: "lp-slideUp 0.4s ease" }}>
            <div style={{
              maxWidth: "75%", padding: "9px 13px", borderRadius: m.side === "bot" ? "4px 16px 16px 16px" : "16px 4px 16px 16px",
              background: m.side === "bot" ? "linear-gradient(135deg,#f59e0b22,#d97706aa)" : "#1e1e35",
              border: m.side === "bot" ? "1px solid #f59e0b44" : "1px solid #2e2e4e",
              fontSize: "13px", color: "#fff", lineHeight: 1.4,
            }}>{m.text}</div>
          </div>
        ))}
        {shown < messages.length && (
          <div style={{ display: "flex", gap: "4px", padding: "10px 14px", background: "#f59e0b18", border: "1px solid #f59e0b33", borderRadius: "4px 16px 16px 16px", width: "fit-content" }}>
            {[0,1,2].map(i => <span key={i} style={{ width: "6px", height: "6px", borderRadius: "50%", background: "#f59e0b", display: "inline-block", animation: `lp-bounce 1s ease ${i * 0.2}s infinite` }} />)}
          </div>
        )}
      </div>
      <div style={{ marginTop: "12px", paddingTop: "12px", borderTop: "1px solid #1e1e35", display: "flex", alignItems: "center", gap: "8px" }}>
        <div style={{ flex: 1, background: "#1a1a2e", border: "1px solid #2e2e4e", borderRadius: "10px", padding: "8px 12px", fontSize: "12px", color: "#4b5563" }}>Écrire un message…</div>
        <div style={{ width: "32px", height: "32px", background: "linear-gradient(135deg,#f59e0b,#d97706)", borderRadius: "10px", display: "flex", alignItems: "center", justifyContent: "center", cursor: "pointer" }}>
          <ArrowRight size={14} color="#0e0e1a" />
        </div>
      </div>
    </div>
  );
}

/* ─────────────────────────────── PAGE ─────────────────────────────── */
export default function LandingPage() {
  const [checkoutLoading, setCheckoutLoading] = useState<string | null>(null);

  async function handleCheckout(plan: string) {
    setCheckoutLoading(plan);
    try {
      const res = await fetch("/api/stripe/checkout", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ plan }),
      });
      const data = await res.json();
      if (data.url) window.location.href = data.url;
    } catch {
      alert("Erreur lors du paiement. Réessaie.");
    }
    setCheckoutLoading(null);
  }

  return (
    <div style={{ minHeight: "100vh", background: "#080810", color: "#fff", fontFamily: "system-ui,-apple-system,sans-serif" }}>

      {/* ── NAV ── */}
      <nav style={{ position: "sticky", top: 0, zIndex: 50, background: "rgba(8,8,16,0.85)", backdropFilter: "blur(20px)", borderBottom: "1px solid rgba(255,255,255,0.06)", padding: "0 24px", display: "flex", alignItems: "center", justifyContent: "space-between", height: "64px" }}>
        <Link href="/" style={{ display: "flex", alignItems: "center", gap: "10px", textDecoration: "none" }}>
          <svg width="34" height="34" viewBox="0 0 88 88" style={{ flexShrink: 0 }}>
            <path d="M8,44 C8,32 18,22 30,26 C24,32 22,38 24,44 C22,50 24,56 30,62 C18,66 8,56 8,44 Z" fill="#f59e0b" opacity="0.7"/>
            <path d="M80,44 C80,32 70,22 58,26 C64,32 66,38 64,44 C66,50 64,56 58,62 C70,66 80,56 80,44 Z" fill="#f59e0b" opacity="0.7"/>
            <circle cx="44" cy="44" r="22" fill="#080810" stroke="#f59e0b" strokeWidth="2.5"/>
            <text x="33" y="56" fontSize="30" fill="#f59e0b" fontFamily="monospace" fontWeight="900">$</text>
          </svg>
          <span style={{ fontWeight: 800, fontSize: "18px", color: "#fff", letterSpacing: "-0.5px" }}>
            Puls<span style={{ color: "#f59e0b" }}>Chat</span>
            <span style={{ background: "#f59e0b", color: "#080810", fontSize: "8px", fontWeight: 900, padding: "2px 5px", borderRadius: "4px", marginLeft: "5px", verticalAlign: "middle" }}>AI</span>
          </span>
        </Link>
        <div style={{ display: "flex", gap: "32px", fontSize: "14px" }}>
          {[["#features","Fonctionnalités"],["#pricing","Tarifs"],["#testimonials","Avis"]].map(([h,l]) => (
            <a key={h} href={h} className="lp-nav-link" style={{ color: "#6b7280", textDecoration: "none", transition: "color 0.2s" }}>{l}</a>
          ))}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
          <Link href="/login" style={{ fontSize: "14px", padding: "8px 16px", borderRadius: "10px", color: "#9ca3af", textDecoration: "none", border: "1px solid rgba(255,255,255,0.08)", transition: "all 0.2s" }}>Connexion</Link>
          <Link href="/register" className="lp-btn-primary" style={{ fontSize: "14px", padding: "8px 18px", borderRadius: "10px", fontWeight: 700, background: "linear-gradient(135deg,#f59e0b,#d97706)", color: "#080810", textDecoration: "none", display: "flex", alignItems: "center", gap: "6px" }}>
            Essai gratuit <ChevronRight size={15} />
          </Link>
        </div>
      </nav>

      {/* ── HERO ── */}
      <section style={{ position: "relative", padding: "100px 24px 80px", textAlign: "center", overflow: "hidden" }}>
        <Orbs />
        {/* Grille déco */}
        <div style={{ position: "absolute", inset: 0, backgroundImage: "linear-gradient(rgba(245,158,11,0.03) 1px, transparent 1px), linear-gradient(90deg, rgba(245,158,11,0.03) 1px, transparent 1px)", backgroundSize: "60px 60px", pointerEvents: "none" }} />

        <div style={{ position: "relative", maxWidth: "900px", margin: "0 auto" }}>
          <Reveal>
            <div style={{ display: "inline-flex", alignItems: "center", gap: "8px", fontSize: "12px", padding: "6px 16px", borderRadius: "99px", marginBottom: "28px", background: "rgba(245,158,11,0.1)", border: "1px solid rgba(245,158,11,0.3)", color: "#f59e0b", fontWeight: 600 }}>
              <Sparkles size={12} />
              IA ultra-humaine — répond en moins de 60s
              <Sparkles size={12} />
            </div>
          </Reveal>

          <Reveal delay={100}>
            <h1 style={{ fontSize: "clamp(42px,8vw,88px)", fontWeight: 900, lineHeight: 1.05, letterSpacing: "-2px", marginBottom: "24px" }}>
              Ton IA qui chat<br />
              <span style={{ background: "linear-gradient(135deg,#f59e0b,#fbbf24,#f59e0b)", backgroundSize: "200% auto", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent", animation: "lp-shimmer 3s linear infinite" }}>
                à ta place 24/7
              </span>
            </h1>
          </Reveal>

          <Reveal delay={200}>
            <p style={{ fontSize: "20px", color: "#9ca3af", maxWidth: "560px", margin: "0 auto 40px", lineHeight: 1.6 }}>
              PulsChat AI répond à tes fans, vend ton PPV automatiquement et <strong style={{ color: "#fff" }}>multiplie tes revenus</strong> — pendant que tu dors.
            </p>
          </Reveal>

          <Reveal delay={300}>
            <div style={{ display: "flex", flexWrap: "wrap", gap: "14px", justifyContent: "center", marginBottom: "50px" }}>
              <Link href="/register" className="lp-btn-primary" style={{ display: "flex", alignItems: "center", gap: "8px", padding: "16px 32px", borderRadius: "14px", fontWeight: 800, fontSize: "17px", background: "linear-gradient(135deg,#f59e0b,#d97706)", color: "#080810", textDecoration: "none" }}>
                Commencer gratuitement <ChevronRight size={20} />
              </Link>
              <a href="#features" style={{ display: "flex", alignItems: "center", gap: "8px", padding: "16px 28px", borderRadius: "14px", fontWeight: 600, fontSize: "16px", border: "1px solid rgba(255,255,255,0.12)", color: "#d1d5db", textDecoration: "none", background: "rgba(255,255,255,0.03)" }}>
                Voir comment ça marche
              </a>
            </div>
          </Reveal>

          <Reveal delay={400}>
            <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "center", gap: "24px", fontSize: "13px", color: "#6b7280", marginBottom: "70px" }}>
              {["Sans carte bancaire","Setup en 5 minutes","99.9% uptime"].map(t => (
                <div key={t} style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                  <CheckCircle size={14} style={{ color: "#f59e0b" }} />{t}
                </div>
              ))}
            </div>
          </Reveal>

          {/* Chat demo flottant */}
          <Reveal delay={500}>
            <div style={{ animation: "lp-float 5s ease-in-out infinite", position: "relative" }}>
              {/* Badge IA active */}
              <div style={{ position: "absolute", top: "-16px", right: "calc(50% - 180px)", background: "#10b981", color: "#fff", fontSize: "11px", fontWeight: 700, padding: "5px 12px", borderRadius: "99px", display: "flex", alignItems: "center", gap: "5px", zIndex: 10, boxShadow: "0 0 20px rgba(16,185,129,0.4)" }}>
                <span style={{ width: "6px", height: "6px", borderRadius: "50%", background: "#fff", display: "inline-block", animation: "lp-pulse1.5s infinite" }} />
                IA active — génère des €
              </div>
              <ChatDemo />
            </div>
          </Reveal>
        </div>
      </section>

      {/* ── STATS ── */}
      <section style={{ padding: "60px 24px", borderTop: "1px solid rgba(255,255,255,0.05)", borderBottom: "1px solid rgba(255,255,255,0.05)", background: "rgba(245,158,11,0.02)" }}>
        <div style={{ maxWidth: "900px", margin: "0 auto", display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: "32px", textAlign: "center" }}>
          {[
            { val: 340, suf: "%+", label: "Revenus en plus", icon: TrendingUp },
            { val: 60, suf: "s", label: "Temps de réponse", icon: Clock },
            { val: 12, suf: "+", label: "Langues", icon: Globe },
            { val: 2400, suf: "+", label: "Créateurs actifs", icon: Users },
          ].map((s, i) => (
            <Reveal key={s.label} delay={i * 80}>
              <div>
                <s.icon size={18} style={{ color: "#f59e0b", margin: "0 auto 8px" }} />
                <div style={{ fontSize: "40px", fontWeight: 900, letterSpacing: "-1px", background: "linear-gradient(135deg,#f59e0b,#fbbf24)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>
                  <Counter target={s.val} suffix={s.suf} />
                </div>
                <div style={{ fontSize: "13px", color: "#6b7280", marginTop: "4px" }}>{s.label}</div>
              </div>
            </Reveal>
          ))}
        </div>
      </section>

      {/* ── FEATURES ── */}
      <section id="features" style={{ padding: "100px 24px" }}>
        <div style={{ maxWidth: "1100px", margin: "0 auto" }}>
          <Reveal>
            <div style={{ textAlign: "center", marginBottom: "64px" }}>
              <div style={{ fontSize: "12px", letterSpacing: "2px", color: "#f59e0b", fontWeight: 700, marginBottom: "12px" }}>FONCTIONNALITÉS</div>
              <h2 style={{ fontSize: "clamp(32px,5vw,52px)", fontWeight: 900, letterSpacing: "-1.5px", marginBottom: "16px" }}>
                Tout ce qu&apos;il te faut pour <span style={{ color: "#f59e0b" }}>scaler</span>
              </h2>
              <p style={{ color: "#6b7280", fontSize: "18px" }}>Une IA entraînée pour vendre, engager et fidéliser tes fans.</p>
            </div>
          </Reveal>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: "20px" }}>
            {[
              { icon: MessageCircle, title: "Chat ultra-humain", desc: "Réponses personnalisées qui imitent ta façon de parler. Tes fans ne savent pas que c'est une IA.", color: "#f59e0b" },
              { icon: DollarSign, title: "Vente PPV automatique", desc: "L'IA propose et vend tes contenus PPV au bon moment, sans que tu aies à lever le petit doigt.", color: "#10b981" },
              { icon: Zap, title: "Welcome message", desc: "Chaque nouvel abonné reçoit un message de bienvenue personnalisé pour démarrer la relation.", color: "#a855f7" },
              { icon: TrendingUp, title: "Relances intelligentes", desc: "L'IA identifie les fans inactifs et les relance automatiquement pour récupérer des revenus perdus.", color: "#ec4899" },
              { icon: BarChart3, title: "Analytics temps réel", desc: "Dashboard complet : revenus générés, taux de conversion, messages envoyés, fans les plus chauds.", color: "#3b82f6" },
              { icon: Shield, title: "Alertes Telegram", desc: "Reçois une notif instantanée quand un fan pose une question que l'IA ne sait pas gérer seule.", color: "#f59e0b" },
            ].map((f, i) => (
              <Reveal key={f.title} delay={i * 80}>
                <div className="lp-card-hover" style={{ padding: "28px", borderRadius: "20px", background: "#0e0e1a", border: "1px solid #1a1a2e", position: "relative", overflow: "hidden" }}>
                  <div style={{ position: "absolute", top: 0, right: 0, width: "80px", height: "80px", background: `radial-gradient(circle at 80% 20%, ${f.color}18, transparent 70%)` }} />
                  <div style={{ width: "44px", height: "44px", borderRadius: "12px", display: "flex", alignItems: "center", justifyContent: "center", marginBottom: "20px", background: `${f.color}15`, border: `1px solid ${f.color}30` }}>
                    <f.icon size={22} style={{ color: f.color }} />
                  </div>
                  <h3 style={{ fontWeight: 800, fontSize: "17px", marginBottom: "10px" }}>{f.title}</h3>
                  <p style={{ fontSize: "14px", color: "#6b7280", lineHeight: 1.6 }}>{f.desc}</p>
                </div>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* ── HOW IT WORKS ── */}
      <section style={{ padding: "100px 24px", background: "rgba(245,158,11,0.02)", borderTop: "1px solid rgba(255,255,255,0.04)" }}>
        <div style={{ maxWidth: "800px", margin: "0 auto", textAlign: "center" }}>
          <Reveal>
            <div style={{ fontSize: "12px", letterSpacing: "2px", color: "#f59e0b", fontWeight: 700, marginBottom: "12px" }}>COMMENT ÇA MARCHE</div>
            <h2 style={{ fontSize: "clamp(30px,5vw,50px)", fontWeight: 900, letterSpacing: "-1.5px", marginBottom: "12px" }}>En place en <span style={{ color: "#f59e0b" }}>5 minutes</span></h2>
            <p style={{ color: "#6b7280", fontSize: "17px", marginBottom: "70px" }}>Pas besoin de compétences techniques.</p>
          </Reveal>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: "48px", position: "relative" }}>
            <div style={{ position: "absolute", top: "28px", left: "20%", right: "20%", height: "1px", background: "linear-gradient(90deg,transparent,#f59e0b55,transparent)", pointerEvents: "none" }} />
            {[
              { step: "01", title: "Crée ton compte", desc: "Inscris-toi gratuitement et configure ton profil créateur en quelques clics." },
              { step: "02", title: "Configure ton IA", desc: "Choisis la personnalité, le ton, les horaires et les templates de messages." },
              { step: "03", title: "Active et encaisse", desc: "Lance l'IA et regarde tes revenus grimper pendant que tu profites de ta vie." },
            ].map((s, i) => (
              <Reveal key={s.step} delay={i * 150}>
                <div>
                  <div style={{ width: "56px", height: "56px", borderRadius: "50%", background: "linear-gradient(135deg,#f59e0b,#d97706)", display: "flex", alignItems: "center", justifyContent: "center", margin: "0 auto 20px", fontSize: "18px", fontWeight: 900, color: "#080810", animation: "lp-glow 3s ease-in-out infinite", animationDelay: `${i}s` }}>
                    {s.step}
                  </div>
                  <h3 style={{ fontWeight: 800, fontSize: "18px", marginBottom: "10px" }}>{s.title}</h3>
                  <p style={{ fontSize: "14px", color: "#6b7280", lineHeight: 1.6 }}>{s.desc}</p>
                </div>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* ── TESTIMONIALS ── */}
      <section id="testimonials" style={{ padding: "100px 24px" }}>
        <div style={{ maxWidth: "1100px", margin: "0 auto" }}>
          <Reveal>
            <div style={{ textAlign: "center", marginBottom: "64px" }}>
              <div style={{ fontSize: "12px", letterSpacing: "2px", color: "#f59e0b", fontWeight: 700, marginBottom: "12px" }}>TÉMOIGNAGES</div>
              <h2 style={{ fontSize: "clamp(30px,5vw,50px)", fontWeight: 900, letterSpacing: "-1.5px" }}>Ce qu&apos;ils en <span style={{ color: "#f59e0b" }}>disent</span></h2>
            </div>
          </Reveal>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: "20px" }}>
            {[
              { name: "Léa M.", role: "Créatrice solo — 4.2k fans", quote: "En 2 semaines j'ai fait +280% de revenus PPV. L'IA parle exactement comme moi, personne a rien vu.", stars: 5, gain: "+280% revenus" },
              { name: "Studio X Agency", role: "Agence — 23 créatrices", quote: "On gère toutes nos créatrices depuis un seul dashboard. Le gain de temps est dingue, on a pu scaler sans recruter.", stars: 5, gain: "×23 créatrices" },
              { name: "Sophie R.", role: "Créatrice — 1.8k fans", quote: "Les relances automatiques m'ont récupéré des fans que je pensais perdus. +€1,200 le premier mois.", stars: 5, gain: "+€1,200 / mois" },
            ].map((t, i) => (
              <Reveal key={t.name} delay={i * 100}>
                <div className="lp-card-hover" style={{ padding: "28px", borderRadius: "20px", background: "#0e0e1a", border: "1px solid #1a1a2e", display: "flex", flexDirection: "column", gap: "16px" }}>
                  <div style={{ display: "inline-flex", alignItems: "center", gap: "6px", background: "rgba(245,158,11,0.1)", border: "1px solid rgba(245,158,11,0.25)", borderRadius: "99px", padding: "4px 12px", fontSize: "12px", fontWeight: 700, color: "#f59e0b", width: "fit-content" }}>
                    <TrendingUp size={11} /> {t.gain}
                  </div>
                  <div style={{ display: "flex", gap: "3px" }}>
                    {Array(t.stars).fill(0).map((_, i) => <Star key={i} size={14} fill="#f59e0b" style={{ color: "#f59e0b" }} />)}
                  </div>
                  <p style={{ fontSize: "14px", color: "#d1d5db", lineHeight: 1.7, flexGrow: 1 }}>&ldquo;{t.quote}&rdquo;</p>
                  <div>
                    <div style={{ fontWeight: 700, fontSize: "14px" }}>{t.name}</div>
                    <div style={{ fontSize: "12px", color: "#6b7280" }}>{t.role}</div>
                  </div>
                </div>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* ── PRICING ── */}
      <section id="pricing" style={{ padding: "120px 24px", position: "relative", overflow: "hidden" }}>
        {/* Grid background */}
        <div style={{ position: "absolute", inset: 0, backgroundImage: "linear-gradient(rgba(245,158,11,0.04) 1px,transparent 1px),linear-gradient(90deg,rgba(245,158,11,0.04) 1px,transparent 1px)", backgroundSize: "40px 40px", pointerEvents: "none" }} />
        <div style={{ position: "absolute", inset: 0, background: "radial-gradient(ellipse 80% 50% at 50% 100%, rgba(245,158,11,0.08) 0%, transparent 70%)", pointerEvents: "none" }} />

        <div style={{ maxWidth: "820px", margin: "0 auto", position: "relative" }}>
          <Reveal>
            <div style={{ textAlign: "center", marginBottom: "70px" }}>
              <div style={{ display: "inline-flex", alignItems: "center", gap: "8px", background: "rgba(245,158,11,0.08)", border: "1px solid rgba(245,158,11,0.2)", borderRadius: "99px", padding: "6px 16px", marginBottom: "20px" }}>
                <span style={{ width: "6px", height: "6px", borderRadius: "50%", background: "#f59e0b", display: "inline-block", animation: "lp-bounce 1s ease infinite" }} />
                <span style={{ fontSize: "11px", letterSpacing: "2px", color: "#f59e0b", fontWeight: 700 }}>TARIFS</span>
              </div>
              <h2 style={{ fontSize: "clamp(32px,5vw,54px)", fontWeight: 900, letterSpacing: "-1.5px", marginBottom: "14px" }}>
                Simple. <span style={{ color: "#f59e0b" }}>Transparent.</span>
              </h2>
              <p style={{ color: "#6b7280", fontSize: "17px" }}>Tu paies seulement quand l&apos;IA performe. Annule à tout moment.</p>
            </div>
          </Reveal>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "24px" }}>
            {[
              {
                name: "Pro", plan: "pro", price: "20", popular: false,
                desc: "Parfait pour démarrer",
                features: [
                  { t: "IA chat 24/7", sub: "Répond à ta place non-stop" },
                  { t: "Vente PPV automatique", sub: "Propose le contenu au bon moment" },
                  { t: "1 créateur inclus", sub: "Extensible avec des licences" },
                  { t: "Analytics de base", sub: "Revenus, fans actifs, taux de réponse" },
                  { t: "Support email", sub: "Réponse sous 24h" },
                ]
              },
              {
                name: "Premium", plan: "premium", price: "70", popular: true,
                desc: "Pour les agences & scalers",
                features: [
                  { t: "Tout du plan Pro", sub: "Base complète incluse" },
                  { t: "Welcome messages IA", sub: "Convertit les nouveaux fans instantly" },
                  { t: "Smart nudges", sub: "Relances intelligentes ciblées" },
                  { t: "Alertes Telegram", sub: "Notifs temps réel sur ton phone" },
                  { t: "Créateurs illimités", sub: "Scale ton agence sans limite" },
                  { t: "Dashboard agence", sub: "Vue multi-compte centralisée" },
                  { t: "Support prioritaire", sub: "Réponse sous 2h, 7j/7" },
                ]
              },
            ].map((p, i) => (
              <Reveal key={p.name} delay={i * 120}>
                <div style={{ position: "relative", borderRadius: "28px", padding: p.popular ? "2px" : "1px", background: p.popular ? "linear-gradient(135deg,#f59e0b,#d97706,#f59e0b)" : "linear-gradient(135deg,#1e1e2e,#2a2a3e)", backgroundSize: "200% 200%", animation: p.popular ? "lp-grad-shift 4s ease infinite" : "none" }}>
                  {p.popular && (
                    <div style={{ position: "absolute", top: "-16px", left: "50%", transform: "translateX(-50%)", zIndex: 2, background: "linear-gradient(135deg,#f59e0b,#d97706)", color: "#080810", fontSize: "10px", fontWeight: 900, letterSpacing: "1.5px", padding: "6px 18px", borderRadius: "99px", whiteSpace: "nowrap", boxShadow: "0 0 24px rgba(245,158,11,0.5)" }}>
                      ✦ LE PLUS POPULAIRE ✦
                    </div>
                  )}
                  <div style={{ borderRadius: p.popular ? "26px" : "27px", background: p.popular ? "#0a0a18" : "#0e0e1a", padding: "36px 32px", height: "100%", boxSizing: "border-box", position: "relative", overflow: "hidden" }}>
                    {/* Glow orb top right */}
                    {p.popular && <div style={{ position: "absolute", top: "-40px", right: "-40px", width: "200px", height: "200px", background: "radial-gradient(circle,rgba(245,158,11,0.12),transparent 70%)", borderRadius: "50%", pointerEvents: "none" }} />}

                    <div style={{ fontSize: "11px", color: p.popular ? "#f59e0b" : "#6b7280", fontWeight: 600, letterSpacing: "1px", marginBottom: "8px", textTransform: "uppercase" }}>{p.desc}</div>
                    <div style={{ fontWeight: 900, fontSize: "26px", marginBottom: "16px", letterSpacing: "-0.5px" }}>{p.name}</div>

                    <div style={{ display: "flex", alignItems: "flex-end", gap: "4px", marginBottom: "4px" }}>
                      <span style={{ fontSize: "20px", fontWeight: 600, color: "#6b7280", lineHeight: "60px" }}>$</span>
                      <span style={{ fontSize: "64px", fontWeight: 900, letterSpacing: "-3px", lineHeight: 1, color: p.popular ? "#f59e0b" : "#fff" }}>{p.price}</span>
                      <span style={{ fontSize: "14px", color: "#6b7280", paddingBottom: "10px" }}>/mois</span>
                    </div>
                    <div style={{ fontSize: "12px", color: "#4b5563", marginBottom: "32px", display: "flex", alignItems: "center", gap: "6px" }}>
                      <span style={{ display: "inline-block", width: "4px", height: "4px", borderRadius: "50%", background: "#f59e0b", opacity: 0.6 }} />
                      + 10% commission sur revenus IA uniquement
                    </div>

                    <ul style={{ listStyle: "none", padding: 0, marginBottom: "32px", display: "flex", flexDirection: "column", gap: "16px" }}>
                      {p.features.map(f => (
                        <li key={f.t} style={{ display: "flex", alignItems: "flex-start", gap: "12px" }}>
                          <div style={{ width: "20px", height: "20px", borderRadius: "6px", background: p.popular ? "rgba(245,158,11,0.15)" : "rgba(255,255,255,0.06)", border: `1px solid ${p.popular ? "rgba(245,158,11,0.3)" : "rgba(255,255,255,0.08)"}`, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, marginTop: "1px" }}>
                            <CheckCircle size={11} style={{ color: p.popular ? "#f59e0b" : "#6b7280" }} />
                          </div>
                          <div>
                            <div style={{ fontSize: "14px", fontWeight: 600, color: "#e5e7eb" }}>{f.t}</div>
                            <div style={{ fontSize: "12px", color: "#4b5563", marginTop: "1px" }}>{f.sub}</div>
                          </div>
                        </li>
                      ))}
                    </ul>

                    <button
                      onClick={() => handleCheckout(p.plan)}
                      disabled={checkoutLoading !== null}
                      style={{
                        width: "100%", padding: "15px", borderRadius: "14px",
                        fontWeight: 800, fontSize: "15px", border: "none", cursor: checkoutLoading ? "wait" : "pointer",
                        background: p.popular
                          ? "linear-gradient(135deg,#f59e0b,#d97706)"
                          : "rgba(255,255,255,0.06)",
                        color: p.popular ? "#080810" : "#d1d5db",
                        boxShadow: p.popular ? "0 0 32px rgba(245,158,11,0.3)" : "none",
                        transition: "all 0.2s",
                        opacity: checkoutLoading && checkoutLoading !== p.plan ? 0.5 : 1,
                        display: "flex", alignItems: "center", justifyContent: "center", gap: "8px",
                      }}>
                      {checkoutLoading === p.plan ? (
                        <><span style={{ width: "14px", height: "14px", borderRadius: "50%", border: "2px solid currentColor", borderTopColor: "transparent", display: "inline-block", animation: "lp-spin 0.7s linear infinite" }} /> Redirection…</>
                      ) : (
                        <>{p.popular ? "🚀 " : ""}Commencer {p.name} <ChevronRight size={16} /></>
                      )}
                    </button>

                    <p style={{ textAlign: "center", fontSize: "11px", color: "#4b5563", marginTop: "14px" }}>
                      Sans engagement · Annule à tout moment
                    </p>
                  </div>
                </div>
              </Reveal>
            ))}
          </div>

          {/* Garantie */}
          <Reveal>
            <div style={{ marginTop: "40px", display: "flex", alignItems: "center", justifyContent: "center", gap: "10px", padding: "16px 24px", borderRadius: "14px", background: "rgba(245,158,11,0.04)", border: "1px solid rgba(245,158,11,0.1)" }}>
              <Shield size={16} style={{ color: "#f59e0b" }} />
              <span style={{ fontSize: "13px", color: "#9ca3af" }}>Paiement 100% sécurisé via <strong style={{ color: "#e5e7eb" }}>Stripe</strong> · Données chiffrées · Aucune carte stockée chez nous</span>
            </div>
          </Reveal>
        </div>
      </section>

      {/* ── CTA FINAL ── */}
      <section style={{ padding: "120px 24px", textAlign: "center", position: "relative", overflow: "hidden" }}>
        <div style={{ position: "absolute", inset: 0, background: "radial-gradient(ellipse 70% 60% at 50% 50%, rgba(245,158,11,0.1) 0%, transparent 70%)", pointerEvents: "none" }} />
        <Reveal>
          <div style={{ maxWidth: "600px", margin: "0 auto", position: "relative" }}>
            <div style={{ fontSize: "12px", letterSpacing: "2px", color: "#f59e0b", fontWeight: 700, marginBottom: "16px" }}>REJOINS 2,400+ CRÉATEURS</div>
            <h2 style={{ fontSize: "clamp(36px,6vw,64px)", fontWeight: 900, letterSpacing: "-2px", lineHeight: 1.05, marginBottom: "20px" }}>
              Prêt à laisser l&apos;IA<br /><span style={{ color: "#f59e0b" }}>travailler pour toi ?</span>
            </h2>
            <p style={{ color: "#9ca3af", fontSize: "18px", marginBottom: "40px" }}>Démarre gratuitement. Sans carte. Setup en 5 min.</p>
            <Link href="/register" className="lp-btn-primary" style={{ display: "inline-flex", alignItems: "center", gap: "10px", padding: "18px 40px", borderRadius: "16px", fontWeight: 800, fontSize: "18px", background: "linear-gradient(135deg,#f59e0b,#d97706)", color: "#080810", textDecoration: "none" }}>
              Créer mon compte gratuit <ChevronRight size={22} />
            </Link>
          </div>
        </Reveal>
      </section>

      {/* ── FOOTER ── */}
      <footer style={{ borderTop: "1px solid rgba(255,255,255,0.05)", padding: "32px 24px" }}>
        <div style={{ maxWidth: "1100px", margin: "0 auto", display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "16px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <svg width="24" height="24" viewBox="0 0 88 88">
              <path d="M8,44 C8,32 18,22 30,26 C24,32 22,38 24,44 C22,50 24,56 30,62 C18,66 8,56 8,44 Z" fill="#f59e0b" opacity="0.7"/>
              <path d="M80,44 C80,32 70,22 58,26 C64,32 66,38 64,44 C66,50 64,56 58,62 C70,66 80,56 80,44 Z" fill="#f59e0b" opacity="0.7"/>
              <circle cx="44" cy="44" r="22" fill="#080810" stroke="#f59e0b" strokeWidth="3"/>
              <text x="33" y="56" fontSize="30" fill="#f59e0b" fontFamily="monospace" fontWeight="900">$</text>
            </svg>
            <span style={{ fontWeight: 800, fontSize: "15px" }}>Puls<span style={{ color: "#f59e0b" }}>Chat</span> AI</span>
          </div>
          <div style={{ fontSize: "12px", color: "#374151" }}>© 2025 PulsChat AI. Tous droits réservés.</div>
          <div style={{ display: "flex", gap: "24px", fontSize: "12px", color: "#374151" }}>
            {["Confidentialité","CGU","Contact"].map(l => <a key={l} href="#" style={{ color: "inherit", textDecoration: "none", transition: "color 0.2s" }}>{l}</a>)}
          </div>
        </div>
      </footer>
    </div>
  );
}
