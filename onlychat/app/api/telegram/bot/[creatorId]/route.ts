import { NextRequest, NextResponse } from "next/server";
import { chatWithAI } from "@/lib/claude";
import { getOrCreateConversation, saveMessage, getHistory } from "@/lib/conversation-store";
import { upsertFan, loadFans, saveFans } from "@/app/api/creators/[id]/fans/route";
import { loadCreatorSettings, buildCreatorPrompt, loadCreatorStyleProfile } from "@/app/api/creators/[id]/settings/route";
import { loadScripts } from "@/lib/scripts-store";
import { getWebhookBase } from "@/lib/app-config";
import fs from "fs";
import path from "path";
import type { Creator } from "@/app/api/creators/route";
import type { Script, ScriptStep } from "@/lib/scripts-store";
import type { Fan } from "@/app/api/creators/[id]/fans/route";
import { getDataDir } from "@/lib/data-dir";
import { recordStarsSale, isCreatorLicenseActive, autoRenewExpiredLicenses } from "@/lib/billing-store";

/* ─── Cherche le creator dans tous les fichiers users ─── */
function findCreator(creatorId: string): { creator: Creator; userId: string } | null {
  const usersDir = path.join(getDataDir(), "users");
  if (!fs.existsSync(usersDir)) return null;
  for (const file of fs.readdirSync(usersDir)) {
    if (!file.endsWith("-creators.json")) continue;
    try {
      const creators: Creator[] = JSON.parse(fs.readFileSync(path.join(usersDir, file), "utf-8"));
      const creator = creators.find(c => c.id === creatorId);
      if (creator) return { creator, userId: file.replace("-creators.json", "") };
    } catch { continue; }
  }
  return null;
}

/* ─── Telegram helpers ─── */
async function tg(token: string, method: string, body: Record<string, unknown>) {
  const res = await fetch(`https://api.telegram.org/bot${token}/${method}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return res.json();
}

const MIME_MAP: Record<string, string> = {
  jpg: "image/jpeg", jpeg: "image/jpeg", png: "image/png",
  gif: "image/gif", webp: "image/webp",
  mp4: "video/mp4", mov: "video/quicktime", webm: "video/webm", avi: "video/x-msvideo",
};

function getMime(fileName: string) {
  return MIME_MAP[fileName.split(".").pop()?.toLowerCase() ?? ""] ?? "application/octet-stream";
}

function resolveLocalPath(mediaUrl: string): string | null {
  const match = mediaUrl.match(/^\/api\/media\/(.+)$/);
  if (!match) return null;
  return path.join(getDataDir(), "uploads", ...match[1].split("/"));
}

async function sendTyping(token: string, chatId: number, bizId?: string) {
  const p: Record<string, unknown> = { chat_id: chatId, action: "typing" };
  if (bizId) p.business_connection_id = bizId;
  await tg(token, "sendChatAction", p);
}

async function sendText(token: string, chatId: number, text: string, bizId?: string) {
  const p: Record<string, unknown> = { chat_id: chatId, text };
  if (bizId) p.business_connection_id = bizId;
  return tg(token, "sendMessage", p);
}

async function sendMediaFile(token: string, chatId: number, mediaUrl: string, bizId?: string) {
  const isVideo = /\.(mp4|mov|webm|avi)$/i.test(mediaUrl);
  const localPath = resolveLocalPath(mediaUrl);
  const method = isVideo ? "sendVideo" : "sendPhoto";
  const field  = isVideo ? "video" : "photo";

  const form = new FormData();
  form.append("chat_id", String(chatId));
  if (bizId) form.append("business_connection_id", bizId);

  if (localPath && fs.existsSync(localPath)) {
    const buf = fs.readFileSync(localPath);
    const name = path.basename(localPath);
    form.append(field, new Blob([buf], { type: getMime(name) }), name);
  } else {
    form.append(field, mediaUrl);
  }

  const res = await fetch(`https://api.telegram.org/bot${token}/${method}`, {
    method: "POST", body: form,
  });
  const json = await res.json();
  if (!json.ok) console.error(`[sendMediaFile] ${json.description} | url=${mediaUrl}`);
  return json;
}

async function sendPaidMedia(token: string, chatId: number, mediaUrls: string[], stars: number, bizId?: string) {
  const form = new FormData();
  form.append("chat_id", String(chatId));
  form.append("star_count", String(stars));
  if (bizId) form.append("business_connection_id", bizId);

  const mediaArray: { type: string; media: string }[] = [];

  for (let i = 0; i < mediaUrls.length; i++) {
    const mediaUrl = mediaUrls[i];
    const isVideo = /\.(mp4|mov|webm|avi)$/i.test(mediaUrl);
    const localPath = resolveLocalPath(mediaUrl);
    const attachKey = `file${i}`;

    if (localPath && fs.existsSync(localPath)) {
      const buf = fs.readFileSync(localPath);
      const name = path.basename(localPath);
      form.append(attachKey, new Blob([buf], { type: getMime(name) }), name);
      mediaArray.push({ type: isVideo ? "video" : "photo", media: `attach://${attachKey}` });
    } else {
      mediaArray.push({ type: isVideo ? "video" : "photo", media: mediaUrl });
    }
  }

  if (mediaArray.length === 0) return;
  form.append("media", JSON.stringify(mediaArray));

  const res = await fetch(`https://api.telegram.org/bot${token}/sendPaidMedia`, {
    method: "POST", body: form,
  });
  const json = await res.json();
  if (!json.ok) console.error(`[sendPaidMedia] ${json.description} | stars=${stars}`);
  return json;
}

/* ─── Envoie une étape de script ─── */
async function sendScriptStep(
  token: string, chatId: number, step: ScriptStep,
  appBase: string, bizId?: string,
  userId?: string, fanId?: string, scriptId?: string,
  forcePrice?: number  // pour envoyer au prix réduit
) {
  const price = forcePrice !== undefined
    ? forcePrice
    : step.priceStars > 0
      ? (step.discountEnabled && step.discountedPriceStars > 0 ? step.discountedPriceStars : step.priceStars)
      : 0;

  // 1. Message texte
  if (step.message.trim()) {
    await sendTyping(token, chatId, bizId);
    await new Promise(r => setTimeout(r, 600 + step.message.length * 25));
    await sendText(token, chatId, step.message, bizId);
  }

  // 2. Teaser pré-média (seulement si contenu payant)
  if (step.preMediaTeaser?.trim() && step.mediaUrls.length > 0 && price > 0) {
    await new Promise(r => setTimeout(r, 500));
    await sendText(token, chatId, step.preMediaTeaser, bizId);
  }

  // 3. Médias
  if (step.mediaUrls.filter(Boolean).length > 0) {
    await new Promise(r => setTimeout(r, 400));
    if (price > 0) {
      const result = await sendPaidMedia(token, chatId, step.mediaUrls.filter(Boolean), price, bizId);
      if (result?.ok && userId && fanId && scriptId) {
        recordStarsSale(userId, String(chatId), fanId, scriptId, price);
      }
    } else {
      for (const mediaUrl of step.mediaUrls.filter(Boolean)) {
        await sendMediaFile(token, chatId, mediaUrl, bizId);
        await new Promise(r => setTimeout(r, 400));
      }
    }
  }

  // 4. Messages post-média
  for (const pm of (step.postMediaMessages ?? [])) {
    if (!pm.message.trim()) continue;
    await new Promise(r => setTimeout(r, (pm.delaySeconds ?? 3) * 1000));
    await sendText(token, chatId, pm.message, bizId);
  }
}

/* ─── Nombre de messages requis entre étapes ─── */
function messagesNeeded(speed: string): number {
  const rand = (min: number, max: number) => min + Math.floor(Math.random() * (max - min + 1));
  if (speed === "fast")   return rand(1, 3);
  if (speed === "slow")   return rand(8, 13);
  return rand(4, 7);
}

/* ─── Mots-clés de réduction ─── */
const DISCOUNT_KEYWORDS = [
  "réduction", "discount", "moins cher", "trop cher", "c'est cher",
  "j'ai pas l'argent", "jai pas l'argent", "j'ai pas d'argent", "jai pas d'argent",
  "pas les moyens", "j'ai pas les sous", "je peux pas payer", "jpeux pas",
  "promo", "offre", "remise", "prix", "cher",
];

/* ─── Moteur de script ─── */
async function runScriptEngine(
  fan: Fan, script: Script, token: string,
  chatId: number, appBase: string, bizId?: string,
  userId?: string, fanId?: string
): Promise<Fan> {
  const active = fan.activeScript!;

  // Si on attend un paiement → ne pas renvoyer l'étape
  if (active.waitingForPayment) return fan;

  const step = script.steps[active.stepIndex];
  if (!step) {
    fan.activeScript = null;
    fan.completedScripts = [...(fan.completedScripts ?? []), script.id];
    await sendText(token, chatId, "✨", bizId);
    return fan;
  }

  const needed = messagesNeeded(step.messagesBetweenSteps ?? "normal");

  if (active.messagesSinceStep < needed) {
    return fan;
  }

  // Envoie l'étape
  await sendScriptStep(token, chatId, step, appBase, bizId, userId, fanId, script.id);

  if (step.priceStars > 0) {
    // Tout média payant → toujours attendre avant de continuer
    // skipFollowupIfPaid coché   = avancer après 10 min même sans paiement
    // skipFollowupIfPaid décoché = attendre paiement confirmé, sinon push vente + stop
    active.waitingForPayment = true;
    active.mediaSentAt = new Date().toISOString();
    active.discountOffered = false;
    active.salePushSent = false;
  } else {
    // Contenu gratuit → avance immédiatement
    active.stepIndex += 1;
    active.messagesSinceStep = 0;
    active.waitingForPayment = false;

    if (active.stepIndex >= script.steps.length) {
      fan.activeScript = null;
      fan.completedScripts = [...(fan.completedScripts ?? []), script.id];
      fan.lastScriptEndedAt = new Date().toISOString();
    }
  }

  return fan;
}

/* ─── Sélection intelligente du meilleur script ─── */
async function pickBestScript(
  availableScripts: Script[],
  fan: Fan,
  lastMessage: string,
  settings: { timezone?: string }
): Promise<Script | null> {
  if (availableScripts.length === 0) return null;
  if (availableScripts.length === 1) return availableScripts[0];

  const tz = "Europe/Paris";
  const localHour = parseInt(new Date().toLocaleString("fr-FR", { timeZone: tz, hour: "2-digit", hour12: false }));
  const moment = localHour >= 5 && localHour < 12 ? "matin"
    : localHour >= 12 && localHour < 18 ? "après-midi"
    : localHour >= 18 && localHour < 22 ? "soir"
    : "nuit";

  const scriptList = availableScripts.map((s, i) =>
    `${i + 1}. "${s.name}" — ${s.description || "Pas de description"}`
  ).join("\n");

  const prompt = `Tu es un expert en marketing de contenu adulte. Tu dois choisir le meilleur script à envoyer à un fan en ce moment.

Heure actuelle : ${moment} (${localHour}h)
Dernier message du fan : "${lastMessage}"
Profil du fan : ${fan.fanProfile || "Inconnu"}

Scripts disponibles :
${scriptList}

Réponds UNIQUEMENT avec le numéro du script le plus adapté (ex: "2").
Critères de choix :
- Heure de la journée (script de soirée le soir, de matin le matin, etc.)
- Ce que le fan a demandé ou ce qui l'intéresse
- Le script qui a le plus de chances de convertir selon le contexte`;

  const answer = await chatWithAI(prompt, "Choisis le meilleur script.", []);
  const num = parseInt(answer.trim().match(/\d+/)?.[0] ?? "1");
  return availableScripts[Math.max(0, Math.min(num - 1, availableScripts.length - 1))];
}

/* ─── Mise à jour profil fan ─── */
async function updateFanProfile(
  creatorId: string,
  fanId: string,
  fan: Fan,
  lastMessage: string,
  history: { role: string; content: string }[]
) {
  const recentMessages = history.slice(-10).map(h =>
    `${h.role === "user" ? "Fan" : "Modèle"}: ${h.content}`
  ).join("\n");
  const context = recentMessages + `\nFan: ${lastMessage}`;

  const extractSystemPrompt = `Tu es un assistant qui analyse des conversations pour extraire les informations personnelles partagées par un fan.

Profil actuel du fan :
${fan.fanProfile || "(aucun profil pour l'instant)"}

Mets à jour le profil du fan en français avec UNIQUEMENT les informations qu'il a lui-même mentionnées. Format compact, une ligne par info connue. Si une info est déjà dans le profil et toujours valide, garde-la. N'invente rien.

Exemple de format :
Prénom : Yoann
Âge : 33 ans
Ville/Région : Rhône-Alpes
Métier : mécanicien auto indépendant
Situation : célibataire
Centres d'intérêt : aime les femmes de 20-25 ans, cherche une fille coquine sans prise de tête

Réponds UNIQUEMENT avec le profil mis à jour, rien d'autre. Si aucune nouvelle info, réponds "(inchangé)".`;

  const updated = await chatWithAI(extractSystemPrompt, `Voici la conversation récente :\n${context}\n\nMets à jour le profil.`, []);
  if (updated && updated !== "(inchangé)" && updated.length > 5) {
    const fans = loadFans(creatorId);
    const idx = fans.findIndex(f => f.telegramId === fanId);
    if (idx >= 0) {
      fans[idx].fanProfile = updated.trim();
      saveFans(creatorId, fans);
    }
  }
}

/* ─── Traitement principal (fire-and-forget) ─── */
async function handleUpdate(creatorId: string, update: Record<string, unknown>) {
  const found = findCreator(creatorId);
  if (!found || !found.creator.enableIA) return;

  const { creator, userId } = found;

  autoRenewExpiredLicenses(userId);
  if (!isCreatorLicenseActive(userId, creatorId)) {
    console.log(`[Bot] Licence expirée ou absente pour créateur ${creatorId} — réponse bloquée`);
    return;
  }

  try {
    const msg = (update.business_message || update.message) as Record<string, unknown> | undefined;
    if (!msg) return;
    if ((msg.from as Record<string, unknown>)?.is_bot) return;

    const bizMsg = update.business_message as Record<string, unknown> | undefined;
    const chatId: number = (msg.chat as Record<string, unknown>).id as number;
    const fromObj = msg.from as Record<string, unknown> | undefined;
    const fanId = String(fromObj?.id ?? chatId);
    const fanUsername: string = (fromObj?.username as string) || "";
    const fanName: string = [fromObj?.first_name, fromObj?.last_name].filter(Boolean).join(" ") || fanUsername || fanId;
    const bizId: string | undefined = bizMsg?.business_connection_id as string | undefined;
    const appBase = getWebhookBase();

    // Enregistre / récupère le fan
    let fan = upsertFan(creator.id, fanId, { name: fanName, username: fanUsername || null });
    if (!fan.enableIA) return;

    const settings = loadCreatorSettings(userId, creator.id);
    const scripts = loadScripts(creator.id);
    const activeScripts = scripts.filter(s => s.active);
    const styleProfile = loadCreatorStyleProfile(creator.id);

    /* ── Paiement Stars confirmé ── */
    const successfulPayment = (msg as Record<string, unknown>)?.successful_payment as Record<string, unknown> | undefined;
    if (successfulPayment) {
      if (fan.activeScript?.waitingForPayment) {
        const paidStars = successfulPayment.total_amount as number;
        console.log(`[Bot] Paiement confirmé ${paidStars}⭐ pour fan ${fanId}`);
        fan.activeScript.waitingForPayment = false;
        fan.activeScript.stepIndex += 1;
        fan.activeScript.messagesSinceStep = 999; // déclenche la prochaine étape rapidement
        fan.activeScript.mediaSentAt = null;
        if (fan.activeScript.stepIndex >= (scripts.find(s => s.id === fan.activeScript?.scriptId)?.steps.length ?? 0)) {
          fan.completedScripts = [...(fan.completedScripts ?? []), fan.activeScript.scriptId];
          fan.activeScript = null;
        }
        const fans = loadFans(creator.id);
        const idx = fans.findIndex(f => f.telegramId === fanId);
        if (idx >= 0) fans[idx] = fan;
        saveFans(creator.id, fans);
      }
      return;
    }

    const userText: string = (msg.text as string) || "";
    if (!userText) return;

    /* ── Gestion du paiement en attente ── */
    if (fan.activeScript?.waitingForPayment && fan.activeScript.mediaSentAt) {
      const script = scripts.find(s => s.id === fan.activeScript?.scriptId);
      const step = script?.steps[fan.activeScript.stepIndex];
      const elapsed = Date.now() - new Date(fan.activeScript.mediaSentAt).getTime();
      const TEN_MIN = 10 * 60 * 1000;
      const fanWantsDiscount = DISCOUNT_KEYWORDS.some(kw => userText.toLowerCase().includes(kw));

      // Détection paiement confirmé par le fan en texte (fallback si successful_payment manqué)
      const PAID_KEYWORDS = ["j'ai payé", "j'ai payer", "jai payé", "jai payer", "j ai payé", "j ai payer", "jpayé", "jpayer", "i paid", "already paid", "j'ai acheté", "jai acheté"];
      const fanClaimsPayment = PAID_KEYWORDS.some(kw => userText.toLowerCase().includes(kw));
      if (fanClaimsPayment && fan.activeScript) {
        console.log(`[Bot] Fan ${fanId} a confirmé le paiement par message texte — avance le script`);
        fan.activeScript.waitingForPayment = false;
        fan.activeScript.stepIndex += 1;
        fan.activeScript.messagesSinceStep = 999;
        fan.activeScript.mediaSentAt = null;
        if (fan.activeScript.stepIndex >= (script?.steps.length ?? 0)) {
          fan.completedScripts = [...(fan.completedScripts ?? []), fan.activeScript.scriptId];
          fan.lastScriptEndedAt = new Date().toISOString();
          fan.activeScript = null;
        }
        const fansP = loadFans(creator.id);
        const idxP = fansP.findIndex(f => f.telegramId === fanId);
        if (idxP >= 0) fansP[idxP] = fan;
        saveFans(creator.id, fansP);
        // Continue pour envoyer le prochain step immédiatement
      }

      if (step) {
        // Proposer le prix réduit si : fan demande réduction OU 10 min passées sans paiement
        if (step.discountEnabled && step.discountedPriceStars > 0 && !fan.activeScript.discountOffered
          && (fanWantsDiscount || elapsed >= TEN_MIN)) {
          fan.activeScript.discountOffered = true;
          // Générer un message de proposition de prix réduit
          const discountPrompt = buildCreatorPrompt(settings, styleProfile) + `
Tu as envoyé un contenu exclusif payant au fan. ${fanWantsDiscount ? "Il semble hésiter sur le prix." : "Il n'a pas encore cliqué pour débloquer."}

Propose-lui une offre spéciale — dis-lui juste que tu lui fais un prix spécial, sans parler de chiffres exacts si possible. Le bouton de paiement est directement sur le message dans Telegram, donc NE mentionne PAS de "plateforme", "lien externe", "accès", ou "validation" — le paiement se fait en un clic sur le message.
Sois naturelle, un peu coquine, comme si tu faisais une exception juste pour lui.
1-2 messages courts maximum, séparés par |||`;

          const discountMsg = await chatWithAI(discountPrompt, userText, []);
          const bubbles = (discountMsg.includes("|||") ? discountMsg.split("|||") : discountMsg.split("\n"))
            .map((b: string) => b.trim()).filter((b: string) => b.length > 0).slice(0, 2);

          for (let i = 0; i < bubbles.length; i++) {
            if (i > 0) { await sendTyping(creator.botToken, chatId, bizId); await new Promise(r => setTimeout(r, 4000)); }
            await sendText(creator.botToken, chatId, bubbles[i], bizId);
          }
          await new Promise(r => setTimeout(r, 2000));
          // Renvoie le même média au prix réduit
          await sendScriptStep(creator.botToken, chatId, step, appBase, bizId, userId, fanId, script!.id, step.discountedPriceStars);

          const fans = loadFans(creator.id);
          const idx = fans.findIndex(f => f.telegramId === fanId);
          if (idx >= 0) fans[idx] = fan;
          saveFans(creator.id, fans);
          return;
        }

        // skipFollowupIfPaid COCHÉ + 10 min passées → avancer au prochain step sans paiement
        if (step.skipFollowupIfPaid && elapsed >= TEN_MIN) {
          fan.activeScript.waitingForPayment = false;
          fan.activeScript.mediaSentAt = null;
          fan.activeScript.stepIndex += 1;
          fan.activeScript.messagesSinceStep = 999;
          if (fan.activeScript.stepIndex >= (script?.steps.length ?? 0)) {
            fan.completedScripts = [...(fan.completedScripts ?? []), fan.activeScript.scriptId];
            fan.lastScriptEndedAt = new Date().toISOString();
            fan.activeScript = null;
          }
          const fans2 = loadFans(creator.id);
          const idx2 = fans2.findIndex(f => f.telegramId === fanId);
          if (idx2 >= 0) fans2[idx2] = fan;
          saveFans(creator.id, fans2);
          // Continue pour envoyer la réponse IA normale
        }

        // skipFollowupIfPaid DÉCOCHÉ + 10 min passées → push vente puis stop
        if (!step.skipFollowupIfPaid && elapsed >= TEN_MIN && fan.activeScript && !fan.activeScript.salePushSent) {
          fan.activeScript.salePushSent = true;
          const salePushPrompt = buildCreatorPrompt(settings, styleProfile) + `
Tu as envoyé un contenu payant il y a un moment. Le fan peut encore le débloquer directement dans le chat Telegram (il voit le bouton de paiement en étoiles sur le message).

Fais une DERNIÈRE relance naturelle et séduisante — pas de mention de "plateforme", "lien", "accès" ou "validation". Le paiement se fait directement sur le message que tu lui as envoyé dans le chat.
Sois légère, coquine, donne envie. 1-2 messages courts max séparés par |||
Style inspiré de tes exemples :
${styleProfile?.realExamples?.slice(0, 3).map(e => `Fan: "${e.fanMessage}"\nToi: "${e.yourReply}"`).join("\n---\n") ?? ""}`;

          const pushMsg = await chatWithAI(salePushPrompt, userText, []);
          const bubbles = (pushMsg.includes("|||") ? pushMsg.split("|||") : pushMsg.split("\n"))
            .map((b: string) => b.trim()).filter((b: string) => b.length > 0).slice(0, 2);

          for (let i = 0; i < bubbles.length; i++) {
            if (i > 0) { await sendTyping(creator.botToken, chatId, bizId); await new Promise(r => setTimeout(r, 4000)); }
            await sendText(creator.botToken, chatId, bubbles[i], bizId);
          }

          // Stop le script
          fan.activeScript = null;
          fan.lastScriptEndedAt = new Date().toISOString();

          const fans = loadFans(creator.id);
          const idx = fans.findIndex(f => f.telegramId === fanId);
          if (idx >= 0) fans[idx] = fan;
          saveFans(creator.id, fans);
          return;
        }
      }
    }

    /* ── Inactivity timeout : expire le script si trop de temps passé ── */
    if (fan.activeScript) {
      const activeScriptData = scripts.find(s => s.id === fan.activeScript?.scriptId);
      if (activeScriptData) {
        const startedAt = new Date(fan.activeScript.startedAt);
        const timeoutMs = (activeScriptData.inactivityTimeoutHours ?? 4) * 60 * 60 * 1000;
        if (Date.now() - startedAt.getTime() > timeoutMs) {
          console.log(`[Bot] Script "${activeScriptData.name}" expiré après ${activeScriptData.inactivityTimeoutHours}h pour fan ${fanId}`);
          fan.activeScript = null;
          fan.lastScriptEndedAt = new Date().toISOString();
        }
      }
    }

    /* ── Mots déclencheurs sexuels → court-circuite le cooldown ── */
    const SEXY_KEYWORDS = ["nude", "t'es sexy", "tes sexy", "fesse", "chatte", "t'es bonne", "tes bonne", "photo de toi", "montre toi", "nue", "seins", "cul"];
    const fanSaidSexy = SEXY_KEYWORDS.some(kw => userText.toLowerCase().includes(kw));

    const firstMsgAt = new Date(fan.firstMessageAt ?? fan.lastInteraction);
    const cooldownDays = settings.sexualizationCooldownDays ?? 2;
    const cooldownMs = cooldownDays * 24 * 60 * 60 * 1000;
    const cooldownOk = (Date.now() - firstMsgAt.getTime()) >= cooldownMs;
    const canLaunchScript = cooldownOk || fanSaidSexy;

    /* ── Déclenchement par nom de script (mot-clé exact) ── */
    const keyword = userText.trim().toLowerCase();
    const keywordScript = activeScripts.find(s =>
      s.name.toLowerCase().replace(/[^a-z0-9]/g, "") === keyword.replace(/[^a-z0-9]/g, "")
    );
    if (keywordScript && !fan.activeScript) {
      fan.activeScript = { scriptId: keywordScript.id, stepIndex: 0, messagesSinceStep: 999, startedAt: new Date().toISOString() };
    }

    /* ── Lancement de script ── */
    // Vérifie le strict cooldown entre scripts
    const strictCooldownOk = !fan.lastScriptEndedAt || (() => {
      const cooldownHours = settings.strictScriptCooldownHours ?? 24;
      const elapsed = Date.now() - new Date(fan.lastScriptEndedAt).getTime();
      return elapsed >= cooldownHours * 60 * 60 * 1000;
    })();

    if (canLaunchScript && !fan.activeScript && strictCooldownOk) {
      const completed = fan.completedScripts ?? [];
      const remaining = activeScripts.filter(s => !completed.includes(s.id));

      let chosenScript: Script | null = null;

      if (completed.length === 0) {
        chosenScript = activeScripts.find(s => s.first) ?? remaining[0] ?? null;
      } else if (remaining.length > 0) {
        chosenScript = await pickBestScript(remaining, fan, userText, settings);
      }

      if (chosenScript) {
        if (completed.length === 0 && !fan.warmupSent) {
          fan.warmupSent = true;
          const fansWu = loadFans(creator.id);
          const wuIdx = fansWu.findIndex(f => f.telegramId === fanId);
          if (wuIdx >= 0) fansWu[wuIdx] = fan;
          saveFans(creator.id, fansWu);

          const warmupPrompt = buildCreatorPrompt(settings, styleProfile) + `
Le fan vient de te parler. Tu vas bientôt lui envoyer du contenu exclusif.
Envoie 2-3 messages courts et naturels pour créer de l'anticipation sans mentionner de photo/vidéo explicitement.
Sois mystérieuse, taquine, donne envie. Format: sépare chaque message par |||`;

          const delayMs = settings.responseDelayMinutes > 0
            ? settings.responseDelayMinutes * 60 * 1000
            : (15 + Math.floor(Math.random() * 20)) * 1000;
          const typingWu = setInterval(() => sendTyping(creator.botToken, chatId, bizId), 4500);
          await sendTyping(creator.botToken, chatId, bizId);
          await new Promise(r => setTimeout(r, delayMs));
          clearInterval(typingWu);

          const warmupReply = await chatWithAI(warmupPrompt, userText, []);
          const warmupBubbles = (warmupReply.includes("|||") ? warmupReply.split("|||") : warmupReply.split("\n"))
            .map((b: string) => b.trim()).filter((b: string) => b.length > 0).slice(0, 3);

          for (let i = 0; i < warmupBubbles.length; i++) {
            if (i > 0) {
              await sendTyping(creator.botToken, chatId, bizId);
              await new Promise(r => setTimeout(r, 4000 + Math.random() * 5000));
            }
            await sendText(creator.botToken, chatId, warmupBubbles[i], bizId);
          }
          await new Promise(r => setTimeout(r, 3000));
        }

        fan.activeScript = { scriptId: chosenScript.id, stepIndex: 0, messagesSinceStep: 999, startedAt: new Date().toISOString() };
        console.log(`[Bot] Script choisi : "${chosenScript.name}" pour fan ${fanId}`);
      }
    }

    /* ── Incrémente compteur de messages ── */
    if (fan.activeScript && !fan.activeScript.waitingForPayment) {
      fan.activeScript.messagesSinceStep += 1;
    }

    /* ── Exécute le moteur de script si actif ── */
    let scriptHandled = false;
    const activeScriptRef = fan.activeScript;
    if (activeScriptRef && !activeScriptRef.waitingForPayment) {
      const script = scripts.find(s => s.id === activeScriptRef.scriptId);
      if (script) {
        const stepIdx = activeScriptRef.stepIndex;
        const step = script.steps[stepIdx];
        const needed = messagesNeeded(step?.messagesBetweenSteps ?? "normal");

        if (activeScriptRef.messagesSinceStep >= needed) {
          fan = await runScriptEngine(fan, script, creator.botToken, chatId, appBase, bizId, userId, fanId);
          scriptHandled = true;
        }
      }
    }

    /* ── Sauvegarde le fan ── */
    const fans = loadFans(creator.id);
    const fanIdx = fans.findIndex(f => f.telegramId === fanId);
    if (fanIdx >= 0) fans[fanIdx] = fan;
    saveFans(creator.id, fans);

    /* ── Réponse IA ── */
    {
      let history: { role: "user" | "assistant"; content: string }[] = [];
      let conversation;
      try {
        conversation = await getOrCreateConversation("telegram_business", `${creator.id}_${fanId}`, fanUsername || fanName, creator.name);
        history = await getHistory(conversation.id, 30);
      } catch { /* Supabase optionnel */ }

      const alreadyAsked = history.filter(h => h.role === "assistant").map(h => h.content).join(" ");

      const fanProfileSection = fan.fanProfile
        ? `\n\nCE QUE TU SAIS SUR CE FAN :\n${fan.fanProfile}\nUtilise ces infos pour personnaliser tes réponses.\n`
        : "";

      // Exemples du style d'entraînement
      const trainingExamples = styleProfile?.realExamples?.slice(0, 6)
        .map((e: { fanMessage: string; yourReply: string }) => `Fan: "${e.fanMessage}"\nToi: "${e.yourReply}"`)
        .join("\n---\n") ?? "";
      const trainingSection = trainingExamples
        ? `\n\nEXEMPLES DE TA FAÇON DE PARLER (reproduis ce style, ces expressions, ces émojis) :\n${trainingExamples}\n`
        : "";

      // Si le fan est dans un script, enrichit le prompt avec le contexte de la prochaine étape
      let interStepContext = "";
      if (fan.activeScript && !fan.activeScript.waitingForPayment && !scriptHandled) {
        const activeScriptData = scripts.find(s => s.id === fan.activeScript?.scriptId);
        const nextStep = activeScriptData?.steps[fan.activeScript.stepIndex];
        if (nextStep) {
          const needed = messagesNeeded(nextStep.messagesBetweenSteps ?? "normal");
          const remaining = Math.max(0, needed - fan.activeScript.messagesSinceStep);
          interStepContext = `

TU ES EN TRAIN DE PRÉPARER LE TERRAIN (encore ~${remaining} messages avant d'envoyer du contenu exclusif) :
${nextStep.preMediaTeaser ? `Indice sur le prochain contenu : "${nextStep.preMediaTeaser}"` : "Prépare le fan à recevoir quelque chose de spécial."}
${nextStep.message ? `Prochain message du script : "${nextStep.message.slice(0, 60)}..."` : ""}
- Crée l'envie naturellement, sans spoiler
- Réponds au fan ET glisse une phrase qui crée l'anticipation
- NE DIS PAS "j'ai une vidéo" ou "je t'envoie une photo", reste mystérieuse`;
      }
    }

      if (fan.activeScript?.waitingForPayment) {
        // Fan n'a pas encore payé — INTERDICTION absolue de parler de paiement
        interStepContext = `\n\nRÈGLE ABSOLUE — NE JAMAIS ENFREINDRE : Tu continues à chatter normalement avec ce fan sur n'importe quel autre sujet (sa journée, ses activités, toi, la météo, etc.). INTERDIT FORMELLEMENT de mentionner : paiement, plateforme, lien, accès, validation, contenu, stars, argent, achat, offre, ou quoi que ce soit lié au contenu exclusif. Le système de paiement Telegram fonctionne automatiquement, tu n'as RIEN à gérer. Sois juste naturelle et spontanée.`;
      }

      const systemPrompt = buildCreatorPrompt(settings, styleProfile) + fanProfileSection + trainingSection + interStepContext + `

RÈGLES DE RÉPONSE — OBLIGATOIRES :
- Réponds en 1, 2 ou 3 messages MAXIMUM, séparés par "|||"
- Chaque message = UNE seule phrase courte (comme un SMS), jamais un pavé
- INTERDIT d'écrire plus de 15 mots dans un seul message
- Si le fan pose plusieurs questions, réponds à chacune en UN message court
- Réponds EN PRIORITÉ aux questions du fan, puis termine par une phrase qui donne envie de continuer
- Tu ne répètes JAMAIS une phrase déjà envoyée
${alreadyAsked.includes("ça va") || alreadyAsked.includes("tu vas") ? "- NE DEMANDE PLUS comment il va, tu l'as déjà fait" : ""}
${alreadyAsked.includes("tu fais quoi") ? "- NE DEMANDE PLUS ce qu'il fait" : ""}

Format STRICT : texte|||texte|||texte (1 à 3 bulles, jamais plus)
Exemples corrects :
"Haha t'es direct toi 😏|||j'aime bien ça|||c'est quoi ton vrai prénom ?"
"Oui je suis là 😊|||tu fais quoi en ce moment ?"
"Pauline 😘"`;

      const delayMs = settings.responseDelayMinutes > 0
        ? settings.responseDelayMinutes * 60 * 1000
        : (20 + Math.floor(Math.random() * 40)) * 1000;
      const TYPING_BEFORE_SEND = 8000;
      const waitMs = Math.max(0, delayMs - TYPING_BEFORE_SEND);
      await new Promise(r => setTimeout(r, waitMs));
      const typingInterval = setInterval(() => sendTyping(creator.botToken, chatId, bizId), 4500);
      await sendTyping(creator.botToken, chatId, bizId);
      await new Promise(r => setTimeout(r, TYPING_BEFORE_SEND));
      clearInterval(typingInterval);

      const reply = await chatWithAI(systemPrompt, userText, history);

      const rawBubbles = reply.includes("|||") ? reply.split("|||") : reply.split(/\n{1,}/);
      const bubbles = rawBubbles.map((b: string) => b.trim()).filter((b: string) => b.length > 0).slice(0, 3);

      for (let i = 0; i < bubbles.length; i++) {
        if (i > 0) {
          const gap = (4000 + Math.random() * 8000);
          await sendTyping(creator.botToken, chatId, bizId);
          await new Promise(r => setTimeout(r, gap));
        }
        await sendText(creator.botToken, chatId, bubbles[i], bizId);
      }

      if (conversation) {
        await saveMessage(conversation.id, "user", userText);
        await saveMessage(conversation.id, "assistant", bubbles.join(" "));
      }

      updateFanProfile(creator.id, fanId, fan, userText, history).catch(() => {});
    }

    console.log(`[Bot ${creator.name}] @${fanUsername}: "${userText.slice(0, 40)}" | script=${fan.activeScript?.scriptId ?? "none"}`);
  } catch (err) {
    console.error(`[Bot error]`, err);
  }
}

/* ─── Queue de messages par fan (debounce 5s) ─── */
interface PendingMsg { text: string; update: Record<string, unknown>; receivedAt: number; }
const fanQueues = new Map<string, PendingMsg[]>();
const fanTimers = new Map<string, ReturnType<typeof setTimeout>>();
const DEBOUNCE_MS = 5000;

function enqueueFanMessage(creatorId: string, fanId: string, text: string, update: Record<string, unknown>) {
  const key = `${creatorId}_${fanId}`;
  const queue = fanQueues.get(key) ?? [];
  queue.push({ text, update, receivedAt: Date.now() });
  fanQueues.set(key, queue);

  const existing = fanTimers.get(key);
  if (existing) clearTimeout(existing);

  const timer = setTimeout(async () => {
    fanTimers.delete(key);
    const msgs = fanQueues.get(key) ?? [];
    fanQueues.delete(key);
    if (msgs.length === 0) return;

    const combinedText = msgs.map(m => m.text).join("\n");
    const firstUpdate = msgs[0].update;
    const mergedUpdate = { ...firstUpdate };
    const baseMsg = (firstUpdate.business_message || firstUpdate.message) as Record<string, unknown>;
    if (baseMsg) {
      const msgCopy = { ...baseMsg, text: combinedText };
      if (firstUpdate.business_message) mergedUpdate.business_message = msgCopy;
      else mergedUpdate.message = msgCopy;
    }

    await handleUpdate(creatorId, mergedUpdate).catch(err => console.error("[Bot background error]", err));
  }, DEBOUNCE_MS);

  fanTimers.set(key, timer);
}

/* ─── Route principale ─── */
export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ creatorId: string }> }
) {
  const { creatorId } = await params;
  const update = await req.json() as Record<string, unknown>;

  const updateId = update.update_id as number | undefined;
  if (updateId) {
    const seenFile = path.join(getDataDir(), `seen-updates-${creatorId}.json`);
    let seen: number[] = [];
    try { seen = JSON.parse(fs.readFileSync(seenFile, "utf-8")); } catch { /* nouveau */ }
    if (seen.includes(updateId)) return NextResponse.json({ ok: true });
    seen = [...seen.slice(-200), updateId];
    try { fs.writeFileSync(seenFile, JSON.stringify(seen)); } catch { /* ignore */ }
  }

  const msg = (update.business_message || update.message) as Record<string, unknown> | undefined;

  // Paiement Stars — transmettre directement à handleUpdate
  const successfulPayment = (msg as Record<string, unknown> | undefined)?.successful_payment;
  if (msg && successfulPayment) {
    handleUpdate(creatorId, update).catch(err => console.error("[Bot payment error]", err));
    return NextResponse.json({ ok: true });
  }

  const text = msg?.text as string | undefined;
  if (msg && text && !(msg.from as Record<string, unknown>)?.is_bot) {
    const fromObj = msg.from as Record<string, unknown> | undefined;
    const chatId = (msg.chat as Record<string, unknown>)?.id as number;
    const fanId = String(fromObj?.id ?? chatId);
    enqueueFanMessage(creatorId, fanId, text, update);
  }

  return NextResponse.json({ ok: true });
}
