"use client";
import React, { useState } from "react";

const SECTIONS = [
  { id: "flux", label: "Flux du bot" },
  { id: "warmup", label: "Prompt warmup" },
  { id: "interstep", label: "Prompt inter-étape" },
  { id: "waitingpayment", label: "Prompt attente paiement" },
  { id: "discount", label: "Prompt réduction" },
  { id: "salepush", label: "Prompt relance vente" },
  { id: "fanprofile", label: "Prompt profil fan" },
  { id: "scriptpicker", label: "Prompt choix script" },
  { id: "keywords", label: "Mots-clés" },
  { id: "params", label: "Paramètres clés" },
];

function PromptBlock({ children, label, color = "#7c3aed" }: { children: string; label?: string; color?: string }) {
  const [open, setOpen] = useState(true);
  return (
    <div style={{ border: `1px solid #1e1e2e`, borderRadius: 10, overflow: "hidden", marginBottom: 16 }}>
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          width: "100%", display: "flex", alignItems: "center", justifyContent: "space-between",
          padding: "10px 16px", background: "#13131f", border: "none", cursor: "pointer",
          color: "#a0a0c0", fontSize: 13, fontFamily: "inherit",
        }}
      >
        <span style={{ color, fontWeight: 600, letterSpacing: "0.04em", fontSize: 11, textTransform: "uppercase" }}>
          {label ?? "SYSTEM PROMPT"}
        </span>
        <span style={{ fontSize: 18, lineHeight: 1 }}>{open ? "−" : "+"}</span>
      </button>
      {open && (
        <pre style={{
          margin: 0, padding: "16px 20px", background: "#0d0d18",
          color: "#c9c9e8", fontSize: 13, lineHeight: 1.65,
          fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
          whiteSpace: "pre-wrap", wordBreak: "break-word", overflowX: "auto",
          borderTop: `1px solid #1e1e2e`,
        }}>
          {children.trim()}
        </pre>
      )}
    </div>
  );
}

function Badge({ children, color }: { children: string; color: string }) {
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", padding: "2px 8px",
      background: color + "22", border: `1px solid ${color}44`,
      borderRadius: 5, color, fontSize: 11, fontWeight: 700,
      letterSpacing: "0.06em", textTransform: "uppercase", fontFamily: "inherit",
    }}>
      {children}
    </span>
  );
}

function Section({ id, title, tag, tagColor, children }: {
  id: string; title: string; tag?: string; tagColor?: string; children: React.ReactNode;
}) {
  return (
    <section id={id} style={{ scrollMarginTop: 80, marginBottom: 56 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 24 }}>
        <h2 style={{ margin: 0, fontSize: 22, fontWeight: 700, color: "#e4e4f0" }}>{title}</h2>
        {tag && <Badge color={tagColor ?? "#7c3aed"}>{tag}</Badge>}
      </div>
      {children}
    </section>
  );
}

function KV({ k, v, desc }: { k: string; v: string; desc?: string }) {
  return (
    <div style={{
      display: "grid", gridTemplateColumns: "220px 1fr", gap: "0 20px",
      padding: "12px 16px", borderBottom: "1px solid #1a1a2a", alignItems: "start",
    }}>
      <span style={{ fontFamily: "ui-monospace, Menlo, monospace", color: "#7c3aed", fontSize: 13, fontWeight: 600 }}>{k}</span>
      <div>
        <span style={{ color: "#e4e4f0", fontSize: 13, fontFamily: "ui-monospace, Menlo, monospace" }}>{v}</span>
        {desc && <div style={{ color: "#6b7280", fontSize: 12, marginTop: 3 }}>{desc}</div>}
      </div>
    </div>
  );
}

function FlowNode({ label, sub, color, icon }: { label: string; sub?: string; color: string; icon: string }) {
  return (
    <div style={{
      background: "#111119", border: `1px solid ${color}55`, borderRadius: 10,
      padding: "12px 18px", minWidth: 160, textAlign: "center",
      boxShadow: `0 0 18px ${color}18`,
    }}>
      <div style={{ fontSize: 22, marginBottom: 4 }}>{icon}</div>
      <div style={{ color, fontWeight: 700, fontSize: 13 }}>{label}</div>
      {sub && <div style={{ color: "#6b7280", fontSize: 11, marginTop: 3 }}>{sub}</div>}
    </div>
  );
}

function Arrow({ label }: { label?: string }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 2, padding: "4px 0" }}>
      {label && <span style={{ color: "#6b7280", fontSize: 11, fontStyle: "italic" }}>{label}</span>}
      <div style={{ width: 1, height: 24, background: "#2e2e4e" }} />
      <div style={{ width: 0, height: 0, borderLeft: "5px solid transparent", borderRight: "5px solid transparent", borderTop: "8px solid #2e2e4e" }} />
    </div>
  );
}

function HArrow({ label }: { label?: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
      <div style={{ width: 32, height: 1, background: "#2e2e4e" }} />
      {label && <span style={{ color: "#6b7280", fontSize: 10 }}>{label}</span>}
      <div style={{ width: 32, height: 1, background: "#2e2e4e" }} />
    </div>
  );
}

export default function BotDocsPage() {
  const [activeSection, setActiveSection] = useState("flux");

  const scrollTo = (id: string) => {
    setActiveSection(id);
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth" });
  };

  return (
    <div style={{
      minHeight: "100vh", background: "#0b0b12", color: "#e4e4f0",
      fontFamily: "system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
      display: "flex",
    }}>
      {/* Sidebar */}
      <nav style={{
        width: 220, flexShrink: 0, position: "sticky", top: 0, height: "100vh",
        padding: "32px 0", borderRight: "1px solid #1a1a2a", overflowY: "auto",
        background: "#0d0d1a",
      }}>
        <div style={{ padding: "0 20px 20px", borderBottom: "1px solid #1a1a2a" }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: "#e11d48", letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: 4 }}>
            OnlyChat AI
          </div>
          <div style={{ fontSize: 14, fontWeight: 600, color: "#e4e4f0" }}>Documentation bot</div>
        </div>
        <ul style={{ listStyle: "none", margin: 0, padding: "16px 0" }}>
          {SECTIONS.map(s => (
            <li key={s.id}>
              <button
                onClick={() => scrollTo(s.id)}
                style={{
                  width: "100%", textAlign: "left", padding: "8px 20px",
                  background: activeSection === s.id ? "#7c3aed18" : "transparent",
                  borderLeft: activeSection === s.id ? "2px solid #7c3aed" : "2px solid transparent",
                  border: "none", color: activeSection === s.id ? "#a78bfa" : "#6b7280",
                  fontSize: 13, cursor: "pointer", fontFamily: "inherit",
                  transition: "all 0.15s",
                }}
              >
                {s.label}
              </button>
            </li>
          ))}
        </ul>
      </nav>

      {/* Main content */}
      <main style={{ flex: 1, padding: "40px 48px", maxWidth: 900, overflowY: "auto" }}>
        <div style={{ marginBottom: 40 }}>
          <h1 style={{ margin: "0 0 8px", fontSize: 30, fontWeight: 800, color: "#e4e4f0" }}>
            Architecture & Prompts du bot
          </h1>
          <p style={{ margin: 0, color: "#6b7280", fontSize: 15 }}>
            Référence technique complète — tous les prompts envoyés à Claude, la logique de décision, et les paramètres configurables.
          </p>
        </div>

        {/* ── FLUX ── */}
        <Section id="flux" title="Flux du bot" tag="Vue d'ensemble" tagColor="#10b981">
          <p style={{ color: "#6b7280", fontSize: 14, marginBottom: 24 }}>
            Chaque message entrant d'un fan déclenche ce pipeline dans l'ordre strict suivant.
          </p>

          <div style={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
            <FlowNode label="Message fan reçu" icon="📩" color="#10b981" sub="Telegram webhook" />
            <Arrow label="vérif. licence active" />
            <FlowNode label="Contrôle licence" icon="🔑" color="#f59e0b" sub="isCreatorLicenseActive()" />
            <Arrow label="licence OK" />
            <FlowNode label="Paiement ?" icon="⭐" color="#e11d48" sub="successful_payment ?" />

            <div style={{ display: "flex", gap: 40, margin: "8px 0", alignItems: "flex-start" }}>
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
                <div style={{ color: "#10b981", fontSize: 11, fontWeight: 600, marginBottom: 8 }}>OUI</div>
                <FlowNode label="Avance script" icon="✅" color="#10b981" sub="stepIndex += 1" />
              </div>
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
                <div style={{ color: "#e11d48", fontSize: 11, fontWeight: 600, marginBottom: 8 }}>NON</div>
                <FlowNode label="waitingForPayment ?" icon="⏳" color="#f59e0b" sub="média payant en attente" />
                <Arrow />
                <div style={{ display: "flex", gap: 24, alignItems: "flex-start" }}>
                  <div style={{ textAlign: "center" }}>
                    <div style={{ color: "#f59e0b", fontSize: 11, fontWeight: 600, marginBottom: 6 }}>réduction demandée<br />ou 10 min passées</div>
                    <FlowNode label="Prompt réduction" icon="💸" color="#f59e0b" sub="discountOffered" />
                  </div>
                  <div style={{ textAlign: "center" }}>
                    <div style={{ color: "#e11d48", fontSize: 11, fontWeight: 600, marginBottom: 6 }}>skipFollowup OFF<br />+ 10 min passées</div>
                    <FlowNode label="Relance vente" icon="🔥" color="#e11d48" sub="salePushSent → stop" />
                  </div>
                </div>
              </div>
            </div>

            <Arrow label="flux normal" />
            <FlowNode label="Cooldown sexualisation" icon="⏱️" color="#6366f1" sub="cooldownDays OU sexy keyword" />
            <Arrow label="cooldown OK" />
            <FlowNode label="Script à lancer ?" icon="📋" color="#7c3aed" sub="pickBestScript() ou premier" />
            <Arrow />
            <div style={{ display: "flex", gap: 40, alignItems: "flex-start", margin: "4px 0" }}>
              <div style={{ textAlign: "center" }}>
                <div style={{ color: "#7c3aed", fontSize: 11, fontWeight: 600, marginBottom: 6 }}>premier script<br />+ pas de warmup encore</div>
                <FlowNode label="Prompt warmup" icon="🔥" color="#7c3aed" sub="2-3 messages teaser" />
              </div>
              <div style={{ textAlign: "center" }}>
                <div style={{ color: "#6366f1", fontSize: 11, fontWeight: 600, marginBottom: 6 }}>script actif<br />messages ≥ needed</div>
                <FlowNode label="Étape script" icon="🎬" color="#6366f1" sub="sendScriptStep()" />
              </div>
            </div>
            <Arrow />
            <FlowNode label="Réponse IA principale" icon="🤖" color="#10b981" sub="buildCreatorPrompt() + contexte" />
            <Arrow />
            <FlowNode label="Profil fan mis à jour" icon="👤" color="#6b7280" sub="updateFanProfile() — async" />
          </div>
        </Section>

        {/* ── WARMUP ── */}
        <Section id="warmup" title="Prompt Warmup" tag="Premier contact" tagColor="#7c3aed">
          <p style={{ color: "#6b7280", fontSize: 14, marginBottom: 20 }}>
            Envoyé <strong style={{ color: "#e4e4f0" }}>une seule fois</strong> avant le premier script,
            uniquement si <code style={{ color: "#a78bfa" }}>warmupSent === false</code>.
            Génère 2-3 messages courts pour créer de l'anticipation.
          </p>
          <PromptBlock label="WARMUP PROMPT — envoyé à Claude" color="#7c3aed">
{`[buildCreatorPrompt(settings, styleProfile)]

Le fan vient de te parler. Tu vas bientôt lui envoyer du contenu exclusif.
Envoie 2-3 messages courts et naturels pour créer de l'anticipation sans mentionner de photo/vidéo explicitement.
Sois mystérieuse, taquine, donne envie. Format: sépare chaque message par |||`}
          </PromptBlock>
          <div style={{ background: "#111119", border: "1px solid #1e1e2e", borderRadius: 8, padding: "14px 18px" }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: "#6b7280", letterSpacing: "0.06em", textTransform: "uppercase", marginBottom: 10 }}>Comportement</div>
            <ul style={{ margin: 0, paddingLeft: 20, color: "#a0a0c0", fontSize: 13, lineHeight: 1.8 }}>
              <li>Délai avant envoi : <code style={{ color: "#7c3aed" }}>responseDelayMinutes</code> si configuré, sinon 15-35 secondes aléatoire</li>
              <li>Indicateur de frappe envoyé toutes les 4,5s pendant le délai</li>
              <li>Les bulles sont séparées par <code style={{ color: "#7c3aed" }}>|||</code>, max 3 gardées</li>
              <li>Délai inter-bulle : 4-9 secondes aléatoire avec typing indicator</li>
            </ul>
          </div>
        </Section>

        {/* ── INTER-STEP ── */}
        <Section id="interstep" title="Prompt inter-étape" tag="Entre les étapes" tagColor="#6366f1">
          <p style={{ color: "#6b7280", fontSize: 14, marginBottom: 20 }}>
            Injecté dans le prompt IA principal quand le fan est dans un script actif mais pas encore à l'étape suivante.
            Crée l'anticipation sans dévoiler le contenu.
          </p>
          <PromptBlock label="INTER-STEP CONTEXT — injecté dans systemPrompt" color="#6366f1">
{`TU ES EN TRAIN DE PRÉPARER LE TERRAIN (encore ~{remaining} messages avant d'envoyer du contenu exclusif) :
{nextStep.preMediaTeaser ? \`Indice sur le prochain contenu : "{nextStep.preMediaTeaser}"\` : "Prépare le fan à recevoir quelque chose de spécial."}
{nextStep.message ? \`Prochain message du script : "{nextStep.message.slice(0, 60)}..."\` : ""}
- Crée l'envie naturellement, sans spoiler
- Réponds au fan ET glisse une phrase qui crée l'anticipation
- NE DIS PAS "j'ai une vidéo" ou "je t'envoie une photo", reste mystérieuse`}
          </PromptBlock>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginTop: 4 }}>
            <div style={{ background: "#111119", border: "1px solid #1e1e2e", borderRadius: 8, padding: "14px 18px" }}>
              <div style={{ fontSize: 11, fontWeight: 700, color: "#6b7280", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 8 }}>Vitesse d'avancement</div>
              <div style={{ fontSize: 13, color: "#a0a0c0", lineHeight: 1.7 }}>
                <div>⚡ <strong style={{ color: "#10b981" }}>fast</strong> — 1 à 3 messages</div>
                <div>📍 <strong style={{ color: "#f59e0b" }}>normal</strong> — 4 à 7 messages</div>
                <div>🐢 <strong style={{ color: "#e11d48" }}>slow</strong> — 8 à 13 messages</div>
              </div>
            </div>
            <div style={{ background: "#111119", border: "1px solid #1e1e2e", borderRadius: 8, padding: "14px 18px" }}>
              <div style={{ fontSize: 11, fontWeight: 700, color: "#6b7280", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 8 }}>Déclenchement</div>
              <div style={{ fontSize: 13, color: "#a0a0c0", lineHeight: 1.7 }}>
                Quand <code style={{ color: "#6366f1" }}>messagesSinceStep ≥ needed</code>,
                le moteur exécute l'étape et réinitialise le compteur.
              </div>
            </div>
          </div>
        </Section>

        {/* ── WAITING PAYMENT ── */}
        <Section id="waitingpayment" title="Prompt attente de paiement" tag="Bloque tout sujet lié au paiement" tagColor="#e11d48">
          <p style={{ color: "#6b7280", fontSize: 14, marginBottom: 20 }}>
            Quand <code style={{ color: "#e11d48" }}>waitingForPayment === true</code>, ce contexte remplace entièrement l'inter-step.
            Le bot chatte normalement <strong style={{ color: "#e4e4f0" }}>sans jamais mentionner le paiement</strong>.
          </p>
          <PromptBlock label="WAITING PAYMENT CONTEXT — remplace inter-step" color="#e11d48">
{`RÈGLE ABSOLUE — NE JAMAIS ENFREINDRE : Tu continues à chatter normalement avec ce fan
sur n'importe quel autre sujet (sa journée, ses activités, toi, la météo, etc.).
INTERDIT FORMELLEMENT de mentionner : paiement, plateforme, lien, accès, validation,
contenu, stars, argent, achat, offre, ou quoi que ce soit lié au contenu exclusif.
Le système de paiement Telegram fonctionne automatiquement, tu n'as RIEN à gérer.
Sois juste naturelle et spontanée.`}
          </PromptBlock>
          <div style={{ background: "#1a1018", border: "1px solid #e11d4855", borderRadius: 8, padding: "14px 18px", fontSize: 13, color: "#a0a0c0" }}>
            <strong style={{ color: "#e11d48" }}>Fallback textuel :</strong> si le fan écrit l'un des PAID_KEYWORDS
            (ex: "j'ai payé", "i paid"…), le bot avance au step suivant sans attendre la confirmation Telegram — utile si
            le webhook <code style={{ color: "#f87171" }}>successful_payment</code> est manqué.
          </div>
        </Section>

        {/* ── DISCOUNT ── */}
        <Section id="discount" title="Prompt réduction" tag="Offre spéciale" tagColor="#f59e0b">
          <p style={{ color: "#6b7280", fontSize: 14, marginBottom: 20 }}>
            Déclenché si <code style={{ color: "#f59e0b" }}>discountEnabled</code> sur l'étape ET (le fan dit un DISCOUNT_KEYWORD OU 10 min se sont écoulées).
            Renvoie le même média au prix réduit.
          </p>
          <PromptBlock label="DISCOUNT PROMPT" color="#f59e0b">
{`[buildCreatorPrompt(settings, styleProfile)]

Tu as envoyé un contenu exclusif payant au fan.
{fanWantsDiscount ? "Il semble hésiter sur le prix." : "Il n'a pas encore cliqué pour débloquer."}

Propose-lui une offre spéciale — dis-lui juste que tu lui fais un prix spécial, sans parler de
chiffres exacts si possible. Le bouton de paiement est directement sur le message dans Telegram,
donc NE mentionne PAS de "plateforme", "lien externe", "accès", ou "validation" — le paiement
se fait en un clic sur le message.
Sois naturelle, un peu coquine, comme si tu faisais une exception juste pour lui.
1-2 messages courts maximum, séparés par |||`}
          </PromptBlock>
          <div style={{ background: "#111119", border: "1px solid #1e1e2e", borderRadius: 8, padding: "14px 18px", fontSize: 13, color: "#a0a0c0" }}>
            Après l'envoi du message de réduction : le même <code style={{ color: "#f59e0b" }}>sendScriptStep()</code> est rappelé
            avec <code style={{ color: "#f59e0b" }}>forcePrice = step.discountedPriceStars</code>.
            Le flag <code style={{ color: "#f59e0b" }}>discountOffered</code> passe à <code style={{ color: "#f59e0b" }}>true</code> pour ne pas boucler.
          </div>
        </Section>

        {/* ── SALE PUSH ── */}
        <Section id="salepush" title="Prompt relance vente" tag="Dernière chance" tagColor="#e11d48">
          <p style={{ color: "#6b7280", fontSize: 14, marginBottom: 20 }}>
            Uniquement si <code style={{ color: "#e11d48" }}>skipFollowupIfPaid === false</code> sur l'étape ET 10 min écoulées.
            Envoie un dernier message séduisant, puis <strong style={{ color: "#e11d48" }}>arrête le script</strong>.
          </p>
          <PromptBlock label="SALE PUSH PROMPT" color="#e11d48">
{`[buildCreatorPrompt(settings, styleProfile)]

Tu as envoyé un contenu payant il y a un moment. Le fan peut encore le débloquer directement
dans le chat Telegram (il voit le bouton de paiement en étoiles sur le message).

Fais une DERNIÈRE relance naturelle et séduisante — pas de mention de "plateforme", "lien",
"accès" ou "validation". Le paiement se fait directement sur le message que tu lui as envoyé
dans le chat.
Sois légère, coquine, donne envie. 1-2 messages courts max séparés par |||
Style inspiré de tes exemples :
{styleProfile.realExamples.slice(0, 3) → "Fan: …\nToi: …"}`}
          </PromptBlock>
          <div style={{ background: "#1a1018", border: "1px solid #e11d4855", borderRadius: 8, padding: "12px 16px", fontSize: 13, color: "#f87171" }}>
            ⚠️ Après ce message : <code>fan.activeScript = null</code> — le script est terminé, même sans paiement.
            Si <code>skipFollowupIfPaid === true</code>, le bot avance silencieusement à l'étape suivante après 10 min.
          </div>
        </Section>

        {/* ── FAN PROFILE ── */}
        <Section id="fanprofile" title="Prompt profil fan" tag="Extraction de données" tagColor="#10b981">
          <p style={{ color: "#6b7280", fontSize: 14, marginBottom: 20 }}>
            Appelé <strong style={{ color: "#e4e4f0" }}>après la réponse IA principale</strong>, de manière asynchrone.
            Analyse les 10 derniers messages pour mettre à jour le profil stocké du fan.
          </p>
          <PromptBlock label="FAN PROFILE EXTRACTION PROMPT" color="#10b981">
{`Tu es un assistant qui analyse des conversations pour extraire les informations personnelles
partagées par un fan.

Profil actuel du fan :
{fan.fanProfile || "(aucun profil pour l'instant)"}

Mets à jour le profil du fan en français avec UNIQUEMENT les informations qu'il a lui-même
mentionnées. Format compact, une ligne par info connue. Si une info est déjà dans le profil
et toujours valide, garde-la. N'invente rien.

Exemple de format :
Prénom : Yoann
Âge : 33 ans
Ville/Région : Rhône-Alpes
Métier : mécanicien auto indépendant
Situation : célibataire
Centres d'intérêt : aime les femmes de 20-25 ans, cherche une fille coquine sans prise de tête

Réponds UNIQUEMENT avec le profil mis à jour, rien d'autre.
Si aucune nouvelle info, réponds "(inchangé)".`}
          </PromptBlock>
          <div style={{ background: "#111119", border: "1px solid #1e1e2e", borderRadius: 8, padding: "14px 18px", fontSize: 13, color: "#a0a0c0" }}>
            Le profil est ensuite réinjecté dans chaque prompt IA principal via la section
            <code style={{ color: "#10b981" }}> CE QUE TU SAIS SUR CE FAN</code>.
            Si la réponse est <code style={{ color: "#6b7280" }}>"(inchangé)"</code> ou moins de 5 caractères, aucune mise à jour.
          </div>
        </Section>

        {/* ── SCRIPT PICKER ── */}
        <Section id="scriptpicker" title="Prompt choix de script" tag="Intelligence contextuelle" tagColor="#6366f1">
          <p style={{ color: "#6b7280", fontSize: 14, marginBottom: 20 }}>
            Appelé par <code style={{ color: "#6366f1" }}>pickBestScript()</code> quand plusieurs scripts sont disponibles
            (après le premier). Choisit le plus adapté selon l'heure, le profil et le dernier message.
          </p>
          <PromptBlock label="SCRIPT PICKER PROMPT" color="#6366f1">
{`Tu es un expert en marketing de contenu adulte. Tu dois choisir le meilleur script à envoyer
à un fan en ce moment.

Heure actuelle : {moment} ({localHour}h)   ← matin/après-midi/soir/nuit (timezone: Europe/Paris)
Dernier message du fan : "{lastMessage}"
Profil du fan : {fan.fanProfile || "Inconnu"}

Scripts disponibles :
1. "{script.name}" — {script.description}
2. "{script.name}" — {script.description}
...

Réponds UNIQUEMENT avec le numéro du script le plus adapté (ex: "2").
Critères de choix :
- Heure de la journée (script de soirée le soir, de matin le matin, etc.)
- Ce que le fan a demandé ou ce qui l'intéresse
- Le script qui a le plus de chances de convertir selon le contexte`}
          </PromptBlock>
          <div style={{ background: "#111119", border: "1px solid #1e1e2e", borderRadius: 8, padding: "14px 18px", fontSize: 13, color: "#a0a0c0" }}>
            Si un seul script disponible → pas d'appel IA, sélection directe.
            Si premier script → priorité au script marqué <code style={{ color: "#6366f1" }}>first: true</code>.
          </div>
        </Section>

        {/* ── PROMPT RÉPONSE IA PRINCIPAL ── */}
        <Section id="waitingpayment" title="Prompt réponse IA principal" tag="Chaque message" tagColor="#a78bfa">
          <p style={{ color: "#6b7280", fontSize: 14, marginBottom: 20 }}>
            Envoyé pour chaque message du fan après les vérifications de script.
            Assemblé dynamiquement depuis plusieurs blocs.
          </p>
          <PromptBlock label="SYSTEM PROMPT PRINCIPAL — assemblage complet" color="#a78bfa">
{`[buildCreatorPrompt(settings, styleProfile)]          ← personnalité & instructions créatrice

[SECTION PROFIL FAN — si fan.fanProfile existe]
CE QUE TU SAIS SUR CE FAN :
{fan.fanProfile}
Utilise ces infos pour personnaliser tes réponses.

[SECTION EXEMPLES DE STYLE — si styleProfile.realExamples existe]
EXEMPLES DE TA FAÇON DE PARLER (reproduis ce style, ces expressions, ces émojis) :
Fan: "..."
Toi: "..."
---
Fan: "..."
Toi: "..."
(jusqu'à 6 exemples)

[SECTION CONTEXTE SCRIPT — inter-step OU waitingForPayment]
→ voir sections dédiées ci-dessus

RÈGLES DE RÉPONSE — OBLIGATOIRES :
- Réponds en 1, 2 ou 3 messages MAXIMUM, séparés par "|||"
- Chaque message = UNE seule phrase courte (comme un SMS), jamais un pavé
- INTERDIT d'écrire plus de 15 mots dans un seul message
- Si le fan pose plusieurs questions, réponds à chacune en UN message court
- Réponds EN PRIORITÉ aux questions du fan, puis termine par une phrase qui donne envie de continuer
- Tu ne répètes JAMAIS une phrase déjà envoyée
[si "ça va" déjà posé] - NE DEMANDE PLUS comment il va, tu l'as déjà fait
[si "tu fais quoi" déjà posé] - NE DEMANDE PLUS ce qu'il fait

Format STRICT : texte|||texte|||texte (1 à 3 bulles, jamais plus)
Exemples corrects :
"Haha t'es direct toi 😏|||j'aime bien ça|||c'est quoi ton vrai prénom ?"
"Oui je suis là 😊|||tu fais quoi en ce moment ?"
"Pauline 😘"`}
          </PromptBlock>
          <div style={{ background: "#111119", border: "1px solid #1e1e2e", borderRadius: 8, padding: "14px 18px", fontSize: 13, color: "#a0a0c0" }}>
            <strong style={{ color: "#e4e4f0" }}>Timing :</strong> délai <code style={{ color: "#a78bfa" }}>responseDelayMinutes</code> si configuré,
            sinon 20-60s aléatoire. Les 8 dernières secondes avant envoi : typing indicator actif.
            Historique : 30 derniers messages (Supabase, optionnel).
          </div>
        </Section>

        {/* ── KEYWORDS ── */}
        <Section id="keywords" title="Mots-clés déclencheurs" tag="Détection automatique" tagColor="#f59e0b">
          <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
            <div style={{ background: "#111119", border: "1px solid #1e1e2e", borderRadius: 10, overflow: "hidden" }}>
              <div style={{ background: "#131320", padding: "12px 18px", borderBottom: "1px solid #1e1e2e" }}>
                <Badge color="#e11d48">SEXY_KEYWORDS</Badge>
                <span style={{ marginLeft: 12, color: "#6b7280", fontSize: 13 }}>Court-circuite le cooldown de sexualisation — lance le script immédiatement</span>
              </div>
              <div style={{ padding: "14px 18px", display: "flex", flexWrap: "wrap", gap: 8 }}>
                {["nude", "t'es sexy", "tes sexy", "fesse", "chatte", "t'es bonne", "tes bonne", "photo de toi", "montre toi", "nue", "seins", "cul"].map(kw => (
                  <code key={kw} style={{ background: "#1a1025", border: "1px solid #e11d4833", color: "#f87171", padding: "3px 10px", borderRadius: 5, fontSize: 12 }}>{kw}</code>
                ))}
              </div>
            </div>

            <div style={{ background: "#111119", border: "1px solid #1e1e2e", borderRadius: 10, overflow: "hidden" }}>
              <div style={{ background: "#131320", padding: "12px 18px", borderBottom: "1px solid #1e1e2e" }}>
                <Badge color="#f59e0b">DISCOUNT_KEYWORDS</Badge>
                <span style={{ marginLeft: 12, color: "#6b7280", fontSize: 13 }}>Déclenche l'offre de réduction immédiatement (sans attendre les 10 min)</span>
              </div>
              <div style={{ padding: "14px 18px", display: "flex", flexWrap: "wrap", gap: 8 }}>
                {["réduction", "discount", "moins cher", "trop cher", "c'est cher", "j'ai pas l'argent", "jai pas l'argent", "j'ai pas d'argent", "jai pas d'argent", "pas les moyens", "j'ai pas les sous", "je peux pas payer", "jpeux pas", "promo", "offre", "remise", "prix", "cher"].map(kw => (
                  <code key={kw} style={{ background: "#1a1a10", border: "1px solid #f59e0b33", color: "#fbbf24", padding: "3px 10px", borderRadius: 5, fontSize: 12 }}>{kw}</code>
                ))}
              </div>
            </div>

            <div style={{ background: "#111119", border: "1px solid #1e1e2e", borderRadius: 10, overflow: "hidden" }}>
              <div style={{ background: "#131320", padding: "12px 18px", borderBottom: "1px solid #1e1e2e" }}>
                <Badge color="#10b981">PAID_KEYWORDS</Badge>
                <span style={{ marginLeft: 12, color: "#6b7280", fontSize: 13 }}>Fallback si <code>successful_payment</code> n'est pas reçu — avance le script</span>
              </div>
              <div style={{ padding: "14px 18px", display: "flex", flexWrap: "wrap", gap: 8 }}>
                {["j'ai payé", "j'ai payer", "jai payé", "jai payer", "j ai payé", "j ai payer", "jpayé", "jpayer", "i paid", "already paid", "j'ai acheté", "jai acheté"].map(kw => (
                  <code key={kw} style={{ background: "#0f1a16", border: "1px solid #10b98133", color: "#34d399", padding: "3px 10px", borderRadius: 5, fontSize: 12 }}>{kw}</code>
                ))}
              </div>
            </div>

            <div style={{ background: "#111119", border: "1px solid #1e1e2e", borderRadius: 10, overflow: "hidden" }}>
              <div style={{ background: "#131320", padding: "12px 18px", borderBottom: "1px solid #1e1e2e" }}>
                <Badge color="#6366f1">KEYWORD SCRIPT</Badge>
                <span style={{ marginLeft: 12, color: "#6b7280", fontSize: 13 }}>Si le message exact correspond au nom d'un script — lance ce script directement</span>
              </div>
              <div style={{ padding: "14px 18px", color: "#a0a0c0", fontSize: 13 }}>
                Le texte du fan est normalisé (<code style={{ color: "#6366f1" }}>toLowerCase().replace(/[^a-z0-9]/g, "")</code>)
                et comparé aux noms de scripts. Uniquement si aucun script n'est déjà actif.
              </div>
            </div>
          </div>
        </Section>

        {/* ── PARAMS ── */}
        <Section id="params" title="Paramètres clés" tag="Valeurs & timings" tagColor="#6b7280">
          <div style={{ background: "#111119", border: "1px solid #1e1e2e", borderRadius: 10, overflow: "hidden" }}>
            <KV k="TEN_MIN" v="10 * 60 * 1000 ms" desc="Seuil d'inaction avant réduction automatique ou relance vente" />
            <KV k="fast range" v="1–3 messages" desc="Nombre de messages du fan entre chaque étape (speed: fast)" />
            <KV k="normal range" v="4–7 messages" desc="Nombre de messages du fan entre chaque étape (speed: normal, défaut)" />
            <KV k="slow range" v="8–13 messages" desc="Nombre de messages du fan entre chaque étape (speed: slow)" />
            <KV k="TYPING_BEFORE_SEND" v="8 000 ms" desc="L'indicateur de frappe s'affiche pendant 8s avant chaque réponse IA" />
            <KV k="typing interval" v="4 500 ms" desc="Fréquence d'envoi de sendChatAction('typing')" />
            <KV k="inter-bulle warmup" v="4 000–9 000 ms" desc="Délai aléatoire entre chaque bulle warmup" />
            <KV k="delay (aucune config)" v="20–60 s" desc="Délai IA aléatoire si responseDelayMinutes non configuré" />
            <KV k="delay warmup (aucune config)" v="15–35 s" desc="Délai avant premier envoi warmup si non configuré" />
            <KV k="cooldownDays" v="settings.sexualizationCooldownDays ?? 2" desc="Jours depuis le premier message avant de lancer un script" />
            <KV k="strictCooldownHours" v="settings.strictScriptCooldownHours ?? 24" desc="Délai minimum entre deux scripts différents" />
            <KV k="inactivityTimeoutHours" v="script.inactivityTimeoutHours ?? 4" desc="Durée max d'un script sans progression avant expiration" />
            <KV k="historique" v="30 messages" desc="Nombre de messages du passé injectés dans le prompt principal" />
            <KV k="exemples style" v="6 premiers" desc="Nombre d'exemples real-chat injectés depuis styleProfile.realExamples" />
            <KV k="COMMISSION_RATE" v="10%" desc="Commission prélevée sur chaque vente de Stars (billing)" />
            <KV k="STARS_TO_USD" v="$0.013 / Star" desc="Taux de conversion pour les revenues USD affichés" />
            <KV k="LICENSE_PRICE_USD" v="$30 / mois" desc="Prix d'une licence créateur (par créateur, 30 jours)" />
          </div>
        </Section>

        <div style={{ height: 60 }} />
      </main>
    </div>
  );
}
