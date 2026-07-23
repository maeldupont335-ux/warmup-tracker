"use client";
import { useEffect, useState } from "react";
import { CheckCircle, Crown, Zap, ChevronRight, ExternalLink, Sparkles } from "lucide-react";

const PLANS = [
  {
    key: "pro", label: "Pro", price: 20, icon: "⚡",
    color: "#a855f7",
    features: ["IA chat 24/7", "Vente PPV automatique", "1 créateur", "Analytics de base", "Support email"],
  },
  {
    key: "premium", label: "Premium", price: 70, icon: "🚀",
    color: "#f59e0b",
    features: ["Tout du Pro", "Welcome messages IA", "Smart nudges", "Alertes Telegram", "Créateurs illimités", "Dashboard agence", "Support prioritaire"],
  },
];

export default function SubscriptionPage() {
  const [currentPlan, setCurrentPlan] = useState<string | null>(null);
  const [loading, setLoading] = useState<string | null>(null);
  const [portalLoading, setPortalLoading] = useState(false);

  useEffect(() => {
    fetch("/api/billing").then(r => r.ok ? r.json() : null).then(d => {
      setCurrentPlan((d?.billing?.stripePlan as string) ?? null);
    });
  }, []);

  async function handleCheckout(plan: string) {
    setLoading(plan);
    const res = await fetch("/api/stripe/checkout", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ plan }),
    });
    const data = await res.json();
    if (data.url) window.location.href = data.url;
    else setLoading(null);
  }

  async function handlePortal() {
    setPortalLoading(true);
    const res = await fetch("/api/stripe/portal", { method: "POST" });
    const data = await res.json();
    if (data.url) window.location.href = data.url;
    else setPortalLoading(false);
  }

  const activePlan = PLANS.find(p => p.key === currentPlan);

  return (
    <div className="p-8" style={{ color: "#fff", maxWidth: "760px" }}>
      <div className="mb-8">
        <h1 className="text-2xl font-black mb-1">Mon abonnement</h1>
        <p className="text-sm" style={{ color: "#6b7280" }}>Gère ton plan et accède aux fonctionnalités avancées</p>
      </div>

      {/* Plan actuel */}
      <div className="rounded-2xl p-6 mb-8" style={{
        background: activePlan ? `rgba(${activePlan.color === "#f59e0b" ? "245,158,11" : "168,85,247"},0.06)` : "rgba(255,255,255,0.03)",
        border: `1px solid ${activePlan ? activePlan.color + "33" : "#1e1e2e"}`,
      }}>
        <div className="text-xs font-bold uppercase tracking-widest mb-4" style={{ color: "#6b7280" }}>Forfait actuel</div>
        {activePlan ? (
          <div className="flex items-center justify-between flex-wrap gap-4">
            <div className="flex items-center gap-4">
              <div className="w-12 h-12 rounded-2xl flex items-center justify-center text-2xl"
                style={{ background: activePlan.color + "18", border: `1px solid ${activePlan.color}33` }}>
                {activePlan.icon}
              </div>
              <div>
                <div className="text-xl font-black">{activePlan.label}</div>
                <div className="text-sm" style={{ color: "#6b7280" }}>${activePlan.price} / mois · + 10% commission IA</div>
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              {activePlan.features.slice(0, 3).map(f => (
                <span key={f} className="text-xs px-3 py-1 rounded-full font-medium"
                  style={{ background: activePlan.color + "15", color: activePlan.color, border: `1px solid ${activePlan.color}33` }}>
                  {f} ✓
                </span>
              ))}
            </div>
          </div>
        ) : (
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl flex items-center justify-center text-lg" style={{ background: "#1a1a2e" }}>🔒</div>
            <div>
              <div className="font-bold">Aucun abonnement actif</div>
              <div className="text-sm" style={{ color: "#6b7280" }}>Choisis un plan pour débloquer l&apos;IA</div>
            </div>
          </div>
        )}
      </div>

      {/* Gérer l'abonnement existant */}
      {currentPlan && (
        <div className="mb-8">
          <button onClick={handlePortal} disabled={portalLoading}
            className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-semibold transition-all"
            style={{ background: "rgba(255,255,255,0.06)", border: "1px solid #2a2a3e", color: "#9ca3af" }}>
            {portalLoading ? <span className="w-4 h-4 rounded-full border-2 border-white/20 border-t-white/80" style={{ animation: "lp-spin 0.7s linear infinite", display: "inline-block" }} /> : <ExternalLink size={14} />}
            Gérer mon abonnement (annuler, changer CB…)
          </button>
        </div>
      )}

      {/* Choisir / changer de plan */}
      <div className="text-xs font-bold uppercase tracking-widest mb-4" style={{ color: "#6b7280" }}>
        {currentPlan ? "Modifier le forfait" : "Choisir un forfait"}
      </div>

      <div className="grid grid-cols-1 gap-4 mb-4" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))" }}>
        {/* Aucun plan */}
        <button
          onClick={currentPlan ? handlePortal : undefined}
          disabled={!currentPlan}
          className="flex items-center gap-4 p-5 rounded-2xl text-left transition-all"
          style={{
            background: !currentPlan ? "rgba(255,255,255,0.03)" : "transparent",
            border: `2px solid ${!currentPlan ? "#374151" : "#1a1a2e"}`,
            opacity: currentPlan ? 0.5 : 1,
            cursor: currentPlan ? "pointer" : "default",
          }}>
          <div className="w-10 h-10 rounded-xl flex items-center justify-center text-lg" style={{ background: "#1a1a2e" }}>🔒</div>
          <div>
            <div className="font-bold text-sm">Aucun</div>
            <div className="text-xs" style={{ color: "#6b7280" }}>Gratuit · Fonctions de base</div>
          </div>
        </button>

        {PLANS.map(plan => {
          const isActive = currentPlan === plan.key;
          return (
            <button key={plan.key}
              onClick={() => !isActive && handleCheckout(plan.key)}
              disabled={isActive || loading !== null}
              className="flex items-center gap-4 p-5 rounded-2xl text-left transition-all"
              style={{
                background: isActive ? plan.color + "10" : "transparent",
                border: `2px solid ${isActive ? plan.color : "#1e1e2e"}`,
                cursor: isActive ? "default" : "pointer",
                boxShadow: isActive ? `0 0 24px ${plan.color}22` : "none",
              }}>
              <div className="w-10 h-10 rounded-xl flex items-center justify-center text-xl"
                style={{ background: plan.color + "15", border: `1px solid ${plan.color}33` }}>
                {plan.icon}
              </div>
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <span className="font-bold text-sm">{plan.label}</span>
                  {isActive && <span className="text-xs px-2 py-0.5 rounded-full font-bold" style={{ background: plan.color + "20", color: plan.color }}>Actif</span>}
                </div>
                <div className="text-xs" style={{ color: "#6b7280" }}>${plan.price} / mois · + 10% commission</div>
              </div>
              {!isActive && (
                loading === plan.key
                  ? <span className="w-4 h-4 rounded-full border-2 border-white/20 border-t-white/80 flex-shrink-0" style={{ animation: "lp-spin 0.7s linear infinite", display: "inline-block" }} />
                  : <ChevronRight size={16} style={{ color: "#4b5563", flexShrink: 0 }} />
              )}
            </button>
          );
        })}
      </div>

      {/* Features comparison */}
      <div className="rounded-2xl p-6 mt-8" style={{ background: "#0d0d14", border: "1px solid #1e1e2e" }}>
        <div className="flex items-center gap-2 mb-5">
          <Sparkles size={14} style={{ color: "#f59e0b" }} />
          <span className="text-sm font-bold">Ce qui est inclus</span>
        </div>
        <div className="grid gap-2">
          {[
            { f: "IA chat 24/7", pro: true, premium: true },
            { f: "Vente PPV automatique", pro: true, premium: true },
            { f: "Analytics de base", pro: true, premium: true },
            { f: "Support email", pro: true, premium: true },
            { f: "Welcome messages IA", pro: false, premium: true },
            { f: "Smart nudges & relances", pro: false, premium: true },
            { f: "Alertes Telegram", pro: false, premium: true },
            { f: "Créateurs illimités", pro: false, premium: true },
            { f: "Dashboard agence", pro: false, premium: true },
            { f: "Support prioritaire 7j/7", pro: false, premium: true },
          ].map(row => (
            <div key={row.f} className="flex items-center py-2.5 border-b last:border-0" style={{ borderColor: "#1a1a2e" }}>
              <span className="flex-1 text-sm" style={{ color: "#9ca3af" }}>{row.f}</span>
              <div className="flex gap-8">
                <div className="w-14 flex justify-center">
                  {row.pro ? <CheckCircle size={14} style={{ color: "#a855f7" }} /> : <span style={{ color: "#374151", fontSize: 14 }}>—</span>}
                </div>
                <div className="w-14 flex justify-center">
                  {row.premium ? <CheckCircle size={14} style={{ color: "#f59e0b" }} /> : <span style={{ color: "#374151", fontSize: 14 }}>—</span>}
                </div>
              </div>
            </div>
          ))}
          <div className="flex items-center pt-3">
            <span className="flex-1" />
            <div className="flex gap-8">
              <div className="w-14 flex justify-center">
                <div className="flex items-center gap-1"><Zap size={11} style={{ color: "#a855f7" }} /><span className="text-xs font-bold" style={{ color: "#a855f7" }}>Pro</span></div>
              </div>
              <div className="w-14 flex justify-center">
                <div className="flex items-center gap-1"><Crown size={11} style={{ color: "#f59e0b" }} /><span className="text-xs font-bold" style={{ color: "#f59e0b" }}>Premium</span></div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
