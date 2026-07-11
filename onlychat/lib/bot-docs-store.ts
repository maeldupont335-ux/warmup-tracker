import fs from "fs";
import path from "path";
import { getDataDir } from "./data-dir";

export interface BotDocsConfig {
  warmupPrompt: string;
  interStepContext: string;
  waitingPaymentContext: string;
  discountPrompt: string;
  salePushPrompt: string;
  responseRules: string;
  sexyKeywords: string[];
  discountKeywords: string[];
  paidKeywords: string[];
}

export const DEFAULT_CONFIG: BotDocsConfig = {
  warmupPrompt: `Le fan vient de te parler. Tu vas bientôt lui envoyer du contenu exclusif.
Envoie 2-3 messages courts et naturels pour créer de l'anticipation sans mentionner de photo/vidéo explicitement.
Sois mystérieuse, taquine, donne envie. Format: sépare chaque message par |||`,

  interStepContext: `TU ES EN TRAIN DE PRÉPARER LE TERRAIN (encore ~{remaining} messages avant d'envoyer du contenu exclusif) :
{teaser}
- Crée l'envie naturellement, sans spoiler
- Réponds au fan ET glisse une phrase qui crée l'anticipation
- NE DIS PAS "j'ai une vidéo" ou "je t'envoie une photo", reste mystérieuse`,

  waitingPaymentContext: `RÈGLE ABSOLUE — NE JAMAIS ENFREINDRE : Tu continues à chatter normalement avec ce fan sur n'importe quel autre sujet (sa journée, ses activités, toi, la météo, etc.). INTERDIT FORMELLEMENT de mentionner : paiement, plateforme, lien, accès, validation, contenu, stars, argent, achat, offre, ou quoi que ce soit lié au contenu exclusif. Le système de paiement Telegram fonctionne automatiquement, tu n'as RIEN à gérer. Sois juste naturelle et spontanée.`,

  discountPrompt: `Tu as envoyé un contenu exclusif payant au fan. {reason}

Propose-lui une offre spéciale — dis-lui juste que tu lui fais un prix spécial, sans parler de chiffres exacts si possible. Le bouton de paiement est directement sur le message dans Telegram, donc NE mentionne PAS de "plateforme", "lien externe", "accès", ou "validation" — le paiement se fait en un clic sur le message.
Sois naturelle, un peu coquine, comme si tu faisais une exception juste pour lui.
1-2 messages courts maximum, séparés par |||`,

  salePushPrompt: `Tu as envoyé un contenu payant il y a un moment. Le fan peut encore le débloquer directement dans le chat Telegram (il voit le bouton de paiement en étoiles sur le message).

Fais une DERNIÈRE relance naturelle et séduisante — pas de mention de "plateforme", "lien", "accès" ou "validation". Le paiement se fait directement sur le message que tu lui as envoyé dans le chat.
Sois légère, coquine, donne envie. 1-2 messages courts max séparés par |||`,

  responseRules: `RÈGLES DE RÉPONSE — OBLIGATOIRES :
- Réponds en 1, 2 ou 3 messages MAXIMUM, séparés par "|||"
- Chaque message = UNE seule phrase courte (comme un SMS), jamais un pavé
- INTERDIT d'écrire plus de 15 mots dans un seul message
- Si le fan pose plusieurs questions, réponds à chacune en UN message court
- Réponds EN PRIORITÉ aux questions du fan, puis termine par une phrase qui donne envie de continuer
- Tu ne répètes JAMAIS une phrase déjà envoyée

Format STRICT : texte|||texte|||texte (1 à 3 bulles, jamais plus)
Exemples corrects :
"Haha t'es direct toi 😏|||j'aime bien ça|||c'est quoi ton vrai prénom ?"
"Oui je suis là 😊|||tu fais quoi en ce moment ?"
"Pauline 😘"`,

  sexyKeywords: ["nude", "t'es sexy", "tes sexy", "fesse", "chatte", "t'es bonne", "tes bonne", "photo de toi", "montre toi", "nue", "seins", "cul"],

  discountKeywords: ["réduction", "discount", "moins cher", "trop cher", "c'est cher", "j'ai pas l'argent", "jai pas l'argent", "j'ai pas d'argent", "jai pas d'argent", "pas les moyens", "j'ai pas les sous", "je peux pas payer", "jpeux pas", "promo", "offre", "remise", "prix", "cher"],

  paidKeywords: ["j'ai payé", "j'ai payer", "jai payé", "jai payer", "j ai payé", "j ai payer", "jpayé", "jpayer", "i paid", "already paid", "j'ai acheté", "jai acheté"],
};

function configDir() {
  const d = path.join(getDataDir(), "bot-docs");
  if (!fs.existsSync(d)) fs.mkdirSync(d, { recursive: true });
  return d;
}

function configFile(userId: string) {
  return path.join(configDir(), `${userId}.json`);
}

export function loadBotDocsConfig(userId: string): BotDocsConfig {
  try {
    const f = configFile(userId);
    if (fs.existsSync(f)) {
      const data = JSON.parse(fs.readFileSync(f, "utf-8"));
      return { ...DEFAULT_CONFIG, ...data };
    }
  } catch { /* ignore */ }
  return { ...DEFAULT_CONFIG };
}

export function saveBotDocsConfig(userId: string, config: BotDocsConfig): void {
  fs.writeFileSync(configFile(userId), JSON.stringify(config, null, 2));
}
