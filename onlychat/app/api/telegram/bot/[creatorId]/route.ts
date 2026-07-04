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

/** Résout /api/media/... → chemin disque absolu */
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

/** Envoie 1 fichier (photo ou vidéo) en multipart binaire */
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
    // Fallback : URL directe
    form.append(field, mediaUrl);
  }

  const res = await fetch(`https://api.telegram.org/bot${token}/${method}`, {
    method: "POST", body: form,
  });
  const json = await res.json();
  if (!json.ok) console.error(`[sendMediaFile] ${json.description} | url=${mediaUrl}`);
  return json;
}

/** Envoie paid media en multipart avec attach:// (méthode officielle Telegram) */
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
      // Fallback URL publique
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
  userId?: string, fanId?: string, scriptId?: string
) {
  const price = step.priceStars > 0
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
      // Contenu payant via Telegram Stars
      const result = await sendPaidMedia(token, chatId, step.mediaUrls.filter(Boolean), price, bizId);
      if (result?.ok && userId && fanId && scriptId) {
        recordStarsSale(userId, String(chatId), fanId, scriptId, price);
      }
    } else {
      // Contenu gratuit — envoi binaire direct
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

/* ─── Nombre de messages requis entre étapes (approximatif, pas pile) ─── */
function messagesNeeded(speed: string): number {
  const rand = (min: number, max: number) => min + Math.floor(Math.random() * (max - min + 1));
  if (speed === "fast")   return rand(1, 3);   // environ 2
  if (speed === "slow")   return rand(8, 13);  // environ 10
  return rand(4, 7);                           // environ 5 (normal)
}

/* ─── Moteur de script ─── */
async function runScriptEngine(
  fan: Fan, script: Script, token: string,
  chatId: number, appBase: string, bizId?: string,
  userId?: string, fanId?: string
): Promise<Fan> {
  const active = fan.activeScript!;
  const step = script.steps[active.stepIndex];
  if (!step) {
    // Script terminé
    fan.activeScript = null;
    fan.completedScripts = [...(fan.completedScripts ?? []), script.id];
    await sendText(token, chatId, "✨", bizId);
    return fan;
  }

  const needed = messagesNeeded(step.messagesBetweenSteps ?? "normal");

  if (active.messagesSinceStep < needed) {
    // Pas encore l'heure d'avancer — le bot répond en IA free
    return fan;
  }

  // Envoie l'étape
  await sendScriptStep(token, chatId, step, appBase, bizId, userId, fanId, script.id);

  // Avance à la prochaine étape
  active.stepIndex += 1;
  active.messagesSinceStep = 0;

  if (active.stepIndex >= script.steps.length) {
    fan.activeScript = null;
    fan.completedScripts = [...(fan.completedScripts ?? []), script.id];
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
  // Construire le contexte de la conversation
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

  // Vérifie la licence (auto-renouvelle si nécessaire)
  autoRenewExpiredLicenses(userId);
  if (!isCreatorLicenseActive(userId, creatorId)) {
    console.log(`[Bot] Licence expirée ou absente pour créateur ${creatorId} — réponse bloquée`);
    return;
  }

  try {
    const msg = (update.business_message || update.message) as Record<string, unknown> | undefined;
    if (!msg?.text) return;
    if ((msg.from as Record<string, unknown>)?.is_bot) return;

    const bizMsg = update.business_message as Record<string, unknown> | undefined;
    const chatId: number = (msg.chat as Record<string, unknown>).id as number;
    const fromObj = msg.from as Record<string, unknown> | undefined;
    const fanId = String(fromObj?.id ?? chatId);
    const fanUsername: string = (fromObj?.username as string) || "";
    const fanName: string = [fromObj?.first_name, fromObj?.last_name].filter(Boolean).join(" ") || fanUsername || fanId;
    const userText: string = msg.text as string;
    const bizId: string | undefined = bizMsg?.business_connection_id as string | undefined;
    const appBase = getWebhookBase();

    // Enregistre / récupère le fan
    let fan = upsertFan(creator.id, fanId, { name: fanName, username: fanUsername || null });

    // Vérifie si l'IA est désactivée pour ce fan
    if (!fan.enableIA) return;

    // Charge les settings & scripts
    const settings = loadCreatorSettings(userId, creator.id);
    const scripts = loadScripts(creator.id);
    const activeScripts = scripts.filter(s => s.active);

    // Mots déclencheurs sexuels → court-circuite le cooldown
    const SEXY_KEYWORDS = ["nude", "t'es sexy", "tes sexy", "fesse", "chatte", "t'es bonne", "tes bonne", "photo de toi", "montre toi", "nue", "seins", "cul"];
    const fanSaidSexy = SEXY_KEYWORDS.some(kw => userText.toLowerCase().includes(kw));

    // Cooldown : X jours depuis le PREMIER message du fan
    const firstMsgAt = new Date(fan.firstMessageAt ?? fan.lastInteraction);
    const cooldownDays = settings.sexualizationCooldownDays ?? 2;
    const cooldownMs = cooldownDays * 24 * 60 * 60 * 1000;
    const cooldownOk = (Date.now() - firstMsgAt.getTime()) >= cooldownMs;

    // Peut lancer le script : cooldown respecté OU mot déclencheur
    const canLaunchScript = cooldownOk || fanSaidSexy;

    // ── 1. Déclenchement par nom de script (mot-clé exact) ──
    const keyword = userText.trim().toLowerCase();
    const keywordScript = activeScripts.find(s =>
      s.name.toLowerCase().replace(/[^a-z0-9]/g, "") === keyword.replace(/[^a-z0-9]/g, "")
    );
    if (keywordScript && !fan.activeScript) {
      fan.activeScript = { scriptId: keywordScript.id, stepIndex: 0, messagesSinceStep: 999, startedAt: new Date().toISOString() };
    }

    // ── 2. Lancement de script — seulement si conditions remplies ──
    if (canLaunchScript && !fan.activeScript) {
      const completed = fan.completedScripts ?? [];
      const remaining = activeScripts.filter(s => !completed.includes(s.id));

      let chosenScript: Script | null = null;

      if (completed.length === 0) {
        // Premier script = toujours celui marqué ⭐ First
        chosenScript = activeScripts.find(s => s.first) ?? remaining[0] ?? null;
      } else if (remaining.length > 0) {
        // Scripts suivants = IA choisit le meilleur selon contexte
        chosenScript = await pickBestScript(remaining, fan, userText, settings);
      }

      if (chosenScript) {
        // Warm-up avant le PREMIER script seulement
        if (completed.length === 0 && !fan.warmupSent) {
          fan.warmupSent = true;
          const fansWu = loadFans(creator.id);
          const wuIdx = fansWu.findIndex(f => f.telegramId === fanId);
          if (wuIdx >= 0) fansWu[wuIdx] = fan;
          saveFans(creator.id, fansWu);

          const styleProfile = loadCreatorStyleProfile(creator.id);
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
            .map(b => b.trim()).filter(b => b.length > 0).slice(0, 3);

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
        console.log(`[Bot] Script choisi : "${chosenScript.name}" (${completed.length === 0 ? "premier/étoile" : "IA pick"}) pour fan ${fanId}`);
      }
    }

    // ── 3. Incrémente le compteur de messages de l'étape en cours ──
    if (fan.activeScript) {
      fan.activeScript.messagesSinceStep += 1;
    }

    // ── 4. Exécute le moteur de script si actif ──
    let scriptHandled = false;
    if (fan.activeScript) {
      const script = scripts.find(s => s.id === fan.activeScript?.scriptId);
      if (script) {
        const stepIdx = fan.activeScript.stepIndex;
        const step = script.steps[stepIdx];
        const needed = messagesNeeded(step?.messagesBetweenSteps ?? "normal");

        if (fan.activeScript.messagesSinceStep >= needed) {
          fan = await runScriptEngine(fan, script, creator.botToken, chatId, appBase, bizId, userId, fanId);
          scriptHandled = true;
        }
      }
    }

    // ── 5. Sauvegarde le fan mis à jour ──
    const fans = loadFans(creator.id);
    const fanIdx = fans.findIndex(f => f.telegramId === fanId);
    if (fanIdx >= 0) fans[fanIdx] = fan;
    saveFans(creator.id, fans);

    // ── 6. Réponse IA (si pas géré par le script) ──
    if (!scriptHandled) {
      const styleProfile = loadCreatorStyleProfile(creator.id);

      let history: { role: "user" | "assistant"; content: string }[] = [];
      let conversation;
      try {
        conversation = await getOrCreateConversation("telegram_business", `${creator.id}_${fanId}`, fanUsername || fanName, creator.name);
        history = await getHistory(conversation.id, 30);
      } catch { /* Supabase optionnel */ }

      // Extraire les questions déjà posées par le bot pour éviter les répétitions
      const alreadyAsked = history
        .filter(h => h.role === "assistant")
        .map(h => h.content)
        .join(" ");

      const fanProfileSection = fan.fanProfile
        ? `\n\nCE QUE TU SAIS SUR CE FAN :\n${fan.fanProfile}\nUtilise ces infos pour personnaliser tes réponses (appelle-le par son prénom si tu le connais, parle de ses intérêts...).\n`
        : "";

      const systemPrompt = buildCreatorPrompt(settings, styleProfile) + fanProfileSection + `

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

      // Délai naturel : attend en silence, puis typing 8 sec avant d'envoyer
      const delayMs = settings.responseDelayMinutes > 0
        ? settings.responseDelayMinutes * 60 * 1000
        : (20 + Math.floor(Math.random() * 40)) * 1000;
      const TYPING_BEFORE_SEND = 8000; // 8 secondes de typing visible
      const waitMs = Math.max(0, delayMs - TYPING_BEFORE_SEND);
      // Attendre en silence
      await new Promise(r => setTimeout(r, waitMs));
      // Puis typing visible 8 sec
      const typingInterval = setInterval(() => sendTyping(creator.botToken, chatId, bizId), 4500);
      await sendTyping(creator.botToken, chatId, bizId);
      await new Promise(r => setTimeout(r, TYPING_BEFORE_SEND));
      clearInterval(typingInterval);

      const reply = await chatWithAI(systemPrompt, userText, history);

      // Sépare en bulles sur ||| ou sur les sauts de ligne
      const rawBubbles = reply.includes("|||")
        ? reply.split("|||")
        : reply.split(/\n{1,}/);

      const bubbles = rawBubbles
        .map(b => b.trim())
        .filter(b => b.length > 0)
        .slice(0, 3);

      for (let i = 0; i < bubbles.length; i++) {
        if (i > 0) {
          // Délai naturel entre bulles : 4 à 12 secondes
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

      // Mise à jour du profil fan en arrière-plan (pas de await pour ne pas bloquer)
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
const DEBOUNCE_MS = 5000; // attendre 5s pour regrouper les messages

function enqueueFanMessage(creatorId: string, fanId: string, text: string, update: Record<string, unknown>) {
  const key = `${creatorId}_${fanId}`;
  const queue = fanQueues.get(key) ?? [];
  queue.push({ text, update, receivedAt: Date.now() });
  fanQueues.set(key, queue);

  // Réinitialise le timer à chaque nouveau message
  const existing = fanTimers.get(key);
  if (existing) clearTimeout(existing);

  const timer = setTimeout(async () => {
    fanTimers.delete(key);
    const msgs = fanQueues.get(key) ?? [];
    fanQueues.delete(key);
    if (msgs.length === 0) return;

    // Regrouper tous les textes en un seul message
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

  // Déduplique les updates Telegram (Telegram retente si réponse trop lente)
  const updateId = update.update_id as number | undefined;
  if (updateId) {
    const seenFile = path.join(getDataDir(), `seen-updates-${creatorId}.json`);
    let seen: number[] = [];
    try { seen = JSON.parse(fs.readFileSync(seenFile, "utf-8")); } catch { /* nouveau */ }
    if (seen.includes(updateId)) return NextResponse.json({ ok: true });
    seen = [...seen.slice(-200), updateId];
    try { fs.writeFileSync(seenFile, JSON.stringify(seen)); } catch { /* ignore */ }
  }

  // Extraire fanId pour le debounce
  const msg = (update.business_message || update.message) as Record<string, unknown> | undefined;
  const text = msg?.text as string | undefined;
  if (msg && text && !(msg.from as Record<string, unknown>)?.is_bot) {
    const fromObj = msg.from as Record<string, unknown> | undefined;
    const chatId = (msg.chat as Record<string, unknown>)?.id as number;
    const fanId = String(fromObj?.id ?? chatId);
    // Mettre en queue avec debounce 5s
    enqueueFanMessage(creatorId, fanId, text, update);
  }

  return NextResponse.json({ ok: true });
}
