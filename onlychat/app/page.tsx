"use client";
import Link from "next/link";
import {
  Zap, TrendingUp, Clock, Globe, Shield, BarChart3,
  MessageCircle, DollarSign, Users, Star, ChevronRight, CheckCircle
} from "lucide-react";

export default function LandingPage() {
  return (
    <div className="min-h-screen" style={{ background: "#0a0a0f", color: "#fff" }}>
      {/* NAV */}
      <nav className="border-b border-white/5 px-6 py-4 flex items-center justify-between sticky top-0 z-50"
        style={{ background: "rgba(10,10,15,0.9)", backdropFilter: "blur(12px)" }}>
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg flex items-center justify-center"
            style={{ background: "linear-gradient(135deg,#a855f7,#7c3aed)" }}>
            <MessageCircle size={16} className="text-white" />
          </div>
          <span className="font-bold text-lg">OnlyChat<span style={{ color: "#a855f7" }}> AI</span></span>
        </div>
        <div className="hidden md:flex items-center gap-8 text-sm" style={{ color: "#9ca3af" }}>
          <a href="#features" className="hover:text-white transition-colors">Fonctionnalités</a>
          <a href="#pricing" className="hover:text-white transition-colors">Tarifs</a>
          <a href="#testimonials" className="hover:text-white transition-colors">Avis</a>
        </div>
        <div className="flex items-center gap-3">
          <Link href="/login" className="text-sm px-4 py-2 rounded-lg hover:bg-white/5 transition-colors"
            style={{ color: "#9ca3af" }}>
            Connexion
          </Link>
          <Link href="/register" className="text-sm px-4 py-2 rounded-lg font-medium transition-all hover:opacity-90"
            style={{ background: "linear-gradient(135deg,#a855f7,#7c3aed)", color: "#fff" }}>
            Essai gratuit
          </Link>
        </div>
      </nav>

      {/* HERO */}
      <section className="relative px-6 py-28 text-center overflow-hidden">
        <div className="absolute inset-0 pointer-events-none"
          style={{ background: "radial-gradient(ellipse 80% 50% at 50% -10%, rgba(168,85,247,0.25) 0%, transparent 70%)" }} />
        <div className="relative max-w-4xl mx-auto">
          <div className="inline-flex items-center gap-2 text-xs px-3 py-1.5 rounded-full mb-6 border"
            style={{ background: "rgba(168,85,247,0.1)", borderColor: "rgba(168,85,247,0.3)", color: "#a855f7" }}>
            <Zap size={12} />
            Réponse IA en moins de 60 secondes
          </div>
          <h1 className="text-5xl md:text-7xl font-black mb-6 leading-tight">
            Ton IA qui chat<br />
            <span style={{ background: "linear-gradient(135deg,#a855f7,#ec4899)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>
              à ta place 24/7
            </span>
          </h1>
          <p className="text-xl mb-10 max-w-2xl mx-auto leading-relaxed" style={{ color: "#9ca3af" }}>
            OnlyChat AI répond à tes fans, vend ton PPV automatiquement et multiplie tes revenus — pendant que tu dors.
          </p>
          <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
            <Link href="/register"
              className="flex items-center gap-2 px-8 py-4 rounded-xl font-bold text-lg transition-all hover:scale-105"
              style={{ background: "linear-gradient(135deg,#a855f7,#7c3aed)", color: "#fff" }}>
              Commencer gratuitement
              <ChevronRight size={20} />
            </Link>
            <a href="#features"
              className="flex items-center gap-2 px-8 py-4 rounded-xl font-medium text-lg border transition-all hover:bg-white/5"
              style={{ borderColor: "rgba(255,255,255,0.1)", color: "#d1d5db" }}>
              Voir comment ça marche
            </a>
          </div>
          <div className="flex items-center justify-center gap-8 mt-12 text-sm" style={{ color: "#6b7280" }}>
            <div className="flex items-center gap-1.5"><CheckCircle size={14} style={{ color: "#a855f7" }} />Sans carte bancaire</div>
            <div className="flex items-center gap-1.5"><CheckCircle size={14} style={{ color: "#a855f7" }} />Setup en 5 minutes</div>
            <div className="flex items-center gap-1.5"><CheckCircle size={14} style={{ color: "#a855f7" }} />99.9% uptime</div>
          </div>
        </div>
      </section>

      {/* STATS */}
      <section className="px-6 py-16 border-y" style={{ borderColor: "rgba(255,255,255,0.05)", background: "rgba(255,255,255,0.01)" }}>
        <div className="max-w-5xl mx-auto grid grid-cols-2 md:grid-cols-4 gap-8 text-center">
          {[
            { value: "+340%", label: "Revenus moyens en +", icon: TrendingUp },
            { value: "< 60s", label: "Temps de réponse", icon: Clock },
            { value: "12+", label: "Langues supportées", icon: Globe },
            { value: "2,400+", label: "Créateurs actifs", icon: Users },
          ].map((s) => (
            <div key={s.label}>
              <s.icon size={20} className="mx-auto mb-2" style={{ color: "#a855f7" }} />
              <div className="text-3xl font-black mb-1">{s.value}</div>
              <div className="text-sm" style={{ color: "#6b7280" }}>{s.label}</div>
            </div>
          ))}
        </div>
      </section>

      {/* FEATURES */}
      <section id="features" className="px-6 py-24">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-16">
            <h2 className="text-4xl font-black mb-4">Tout ce qu&apos;il te faut pour <span style={{ color: "#a855f7" }}>scaler</span></h2>
            <p className="text-lg" style={{ color: "#6b7280" }}>Une IA entraînée pour vendre, engager et fidéliser tes fans.</p>
          </div>
          <div className="grid md:grid-cols-3 gap-6">
            {[
              { icon: MessageCircle, title: "Chat ultra-humain", desc: "Réponses personnalisées qui imitent ta façon de parler. Tes fans ne savent pas que c'est une IA.", color: "#a855f7" },
              { icon: DollarSign, title: "Vente PPV automatique", desc: "L'IA propose et vend tes contenus PPV au bon moment, sans que tu aies à lever le petit doigt.", color: "#ec4899" },
              { icon: Zap, title: "Welcome message", desc: "Chaque nouvel abonné reçoit un message de bienvenue personnalisé pour démarrer la relation.", color: "#f59e0b" },
              { icon: TrendingUp, title: "Relances intelligentes", desc: "L'IA identifie les fans inactifs et les relance automatiquement pour récupérer des revenus perdus.", color: "#10b981" },
              { icon: BarChart3, title: "Analytics en temps réel", desc: "Dashboard complet : revenus générés, taux de conversion, messages envoyés, fans les plus chauds.", color: "#3b82f6" },
              { icon: Shield, title: "Alertes Telegram", desc: "Reçois une notif instantanée quand un fan pose une question que l'IA ne sait pas gérer seule.", color: "#6366f1" },
            ].map((f) => (
              <div key={f.title} className="p-6 rounded-2xl border transition-all hover:border-purple-500/30"
                style={{ background: "#111118", borderColor: "#1e1e2e" }}>
                <div className="w-10 h-10 rounded-xl flex items-center justify-center mb-4"
                  style={{ background: `${f.color}18` }}>
                  <f.icon size={20} style={{ color: f.color }} />
                </div>
                <h3 className="font-bold text-lg mb-2">{f.title}</h3>
                <p className="text-sm leading-relaxed" style={{ color: "#6b7280" }}>{f.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* HOW IT WORKS */}
      <section className="px-6 py-24" style={{ background: "rgba(255,255,255,0.01)" }}>
        <div className="max-w-4xl mx-auto text-center">
          <h2 className="text-4xl font-black mb-4">En place en <span style={{ color: "#a855f7" }}>5 minutes</span></h2>
          <p className="text-lg mb-16" style={{ color: "#6b7280" }}>Pas besoin de compétences techniques.</p>
          <div className="grid md:grid-cols-3 gap-8">
            {[
              { step: "01", title: "Crée ton compte", desc: "Inscris-toi gratuitement et configure ton profil créateur en quelques clics." },
              { step: "02", title: "Configure ton IA", desc: "Choisis la personnalité, le ton, les horaires d'activation et les templates de messages." },
              { step: "03", title: "Active et encaisse", desc: "Lance l'IA et regarde tes revenus grimper pendant que tu profites de ta vie." },
            ].map((s) => (
              <div key={s.step}>
                <div className="text-6xl font-black mb-4" style={{ color: "rgba(168,85,247,0.15)" }}>{s.step}</div>
                <h3 className="font-bold text-xl mb-2">{s.title}</h3>
                <p className="text-sm leading-relaxed" style={{ color: "#6b7280" }}>{s.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* TESTIMONIALS */}
      <section id="testimonials" className="px-6 py-24">
        <div className="max-w-6xl mx-auto">
          <h2 className="text-4xl font-black text-center mb-16">Ce qu&apos;ils en <span style={{ color: "#a855f7" }}>disent</span></h2>
          <div className="grid md:grid-cols-3 gap-6">
            {[
              { name: "Léa M.", role: "Créatrice solo — 4.2k fans", quote: "En 2 semaines j'ai fait +280% de revenus PPV. L'IA parle exactement comme moi, personne a rien vu.", stars: 5 },
              { name: "Studio X Agency", role: "Agence — 23 créatrices", quote: "On gère toutes nos créatrices depuis un seul dashboard. Le gain de temps est dingue, on a pu scaler sans recruter.", stars: 5 },
              { name: "Sophie R.", role: "Créatrice — 1.8k fans", quote: "Les relances automatiques m'ont récupéré des fans que je pensais perdus. +€1,200 le premier mois.", stars: 5 },
            ].map((t) => (
              <div key={t.name} className="p-6 rounded-2xl border" style={{ background: "#111118", borderColor: "#1e1e2e" }}>
                <div className="flex gap-1 mb-4">
                  {Array(t.stars).fill(0).map((_, i) => <Star key={i} size={14} fill="#f59e0b" style={{ color: "#f59e0b" }} />)}
                </div>
                <p className="text-sm leading-relaxed mb-4" style={{ color: "#d1d5db" }}>&ldquo;{t.quote}&rdquo;</p>
                <div className="font-semibold text-sm">{t.name}</div>
                <div className="text-xs" style={{ color: "#6b7280" }}>{t.role}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* PRICING */}
      <section id="pricing" className="px-6 py-24" style={{ background: "rgba(255,255,255,0.01)" }}>
        <div className="max-w-4xl mx-auto text-center">
          <h2 className="text-4xl font-black mb-4">Tarifs <span style={{ color: "#a855f7" }}>transparents</span></h2>
          <p className="text-lg mb-16" style={{ color: "#6b7280" }}>Tu paies seulement quand l&apos;IA performe.</p>
          <div className="grid md:grid-cols-2 gap-6 max-w-2xl mx-auto">
            {[
              { name: "Pro", price: "20", popular: false, features: ["IA chat 24/7", "Vente PPV automatique", "1 créateur", "Analytics de base", "Support email"] },
              { name: "Premium", price: "70", popular: true, features: ["Tout du Pro", "Welcome messages", "Smart nudges", "Alertes Telegram", "Créateurs illimités", "Dashboard agence", "Support prioritaire"] },
            ].map((p) => (
              <div key={p.name} className="p-8 rounded-2xl border relative text-left"
                style={{ background: "#111118", borderColor: p.popular ? "#a855f7" : "#1e1e2e" }}>
                {p.popular && (
                  <div className="absolute -top-3 left-1/2 -translate-x-1/2 text-xs px-3 py-1 rounded-full font-bold"
                    style={{ background: "linear-gradient(135deg,#a855f7,#7c3aed)", color: "#fff" }}>
                    LE PLUS POPULAIRE
                  </div>
                )}
                <div className="font-bold text-lg mb-2">{p.name}</div>
                <div className="mb-1"><span className="text-4xl font-black">${p.price}</span><span className="text-sm" style={{ color: "#6b7280" }}>/mois</span></div>
                <div className="text-sm mb-6" style={{ color: "#6b7280" }}>+ 10% commission sur revenus IA</div>
                <ul className="space-y-3 mb-8">
                  {p.features.map((f) => (
                    <li key={f} className="flex items-center gap-2 text-sm"><CheckCircle size={14} style={{ color: "#a855f7" }} />{f}</li>
                  ))}
                </ul>
                <Link href="/register" className="block text-center py-3 rounded-xl font-semibold transition-all hover:opacity-90"
                  style={p.popular ? { background: "linear-gradient(135deg,#a855f7,#7c3aed)", color: "#fff" } : { background: "#1e1e2e", color: "#d1d5db" }}>
                  Commencer
                </Link>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="px-6 py-24 text-center">
        <div className="max-w-2xl mx-auto">
          <h2 className="text-4xl font-black mb-6">
            Prêt à laisser l&apos;IA<br /><span style={{ color: "#a855f7" }}>travailler pour toi ?</span>
          </h2>
          <p className="text-lg mb-8" style={{ color: "#6b7280" }}>Rejoins 2,400+ créateurs qui automatisent leurs revenus dès aujourd&apos;hui.</p>
          <Link href="/register"
            className="inline-flex items-center gap-2 px-10 py-4 rounded-xl font-bold text-lg transition-all hover:scale-105"
            style={{ background: "linear-gradient(135deg,#a855f7,#7c3aed)", color: "#fff" }}>
            Créer mon compte gratuit <ChevronRight size={20} />
          </Link>
        </div>
      </section>

      {/* FOOTER */}
      <footer className="border-t px-6 py-10" style={{ borderColor: "rgba(255,255,255,0.05)" }}>
        <div className="max-w-6xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 rounded flex items-center justify-center" style={{ background: "linear-gradient(135deg,#a855f7,#7c3aed)" }}>
              <MessageCircle size={12} className="text-white" />
            </div>
            <span className="font-bold text-sm">OnlyChat AI</span>
          </div>
          <div className="text-xs" style={{ color: "#4b5563" }}>© 2025 OnlyChat AI. Tous droits réservés.</div>
          <div className="flex gap-6 text-xs" style={{ color: "#4b5563" }}>
            <a href="#" className="hover:text-white transition-colors">Confidentialité</a>
            <a href="#" className="hover:text-white transition-colors">CGU</a>
            <a href="#" className="hover:text-white transition-colors">Contact</a>
          </div>
        </div>
      </footer>
    </div>
  );
}
