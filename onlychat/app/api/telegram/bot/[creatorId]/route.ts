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
import { recordStarsSale } from "@/lib/billing-store";

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

  const extractPrompt = `Tu es un assistant qui analyse des conversations pour extraire les informations personnelles partagées par un fan.

Voici la conversation récente :
${context}

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
Se décrit comme : pas le plus beau, un peu enrobé, "gros nounours" joueur

Réponds UNIQUEMENT avec le profil mis à jour, rien d'autre. Si aucune nouvelle info, réponds "(inchangé)".`;

  const updated = await chatWithAI(extractPrompt, "", []);
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

    // ── 2. Script "First" — seulement si conditions remplies et fan actif ──
    if (canLaunchScript && !fan.activeScript && (fan.completedScripts?.length ?? 0) === 0) {
      const firstScript = activeScripts.find(s => s.first);
      if (firstScript) {
        // Warm-up : quelques messages de chauffe avant le script
        if (!fan.warmupSent) {
          fan.warmupSent = true;
          // Sauvegarder avant d'envoyer le warm-up
          const fansWu = loadFans(creator.id);
          const wuIdx = fansWu.findIndex(f => f.telegramId === fanId);
          if (wuIdx >= 0) fansWu[wuIdx] = fan;
          saveFans(creator.id, fansWu);

          // Messages de chauffe générés par l'IA
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

          // Maintenant lance le vrai script
          await new Promise(r => setTimeout(r, 3000));
          fan.activeScript = { scriptId: firstScript.id, stepIndex: 0, messagesSinceStep: 999, startedAt: new Date().toISOString() };
        } else {
          fan.activeScript = { scriptId: firstScript.id, stepIndex: 0, messagesSinceStep: 999, startedAt: new Date().toISOString() };
        }
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

RÈGLES IMPORTANTES :
- Tu réponds TOUJOURS en plusieurs messages courts séparés par "|||" (2 à 4 bulles max, 1-2 phrases chacune)
- Tu ne répètes JAMAIS une question ou phrase que tu as déjà envoyée
- Tu ne demandes JAMAIS plusieurs fois "ça va ?" ou des variantes
- Tu réagis naturellement à ce que dit le fan, tu ne follows pas un script
- Tu es spontanée, chaleureuse, tu crées un lien authentique
${alreadyAsked.includes("ça va") || alreadyAsked.includes("tu vas") ? "- NE DEMANDE PLUS comment il va, tu l'as déjà fait" : ""}
${alreadyAsked.includes("tu fais quoi") || alreadyAsked.includes("tu fais quoi") ? "- NE DEMANDE PLUS ce qu'il fait" : ""}

Format de réponse OBLIGATOIRE : sépare chaque bulle par |||
Exemple : "Haha oui exactement 😏|||t'as raison en fait|||tu fais quoi ce soir ?"`;

      // Délai naturel
      const delayMs = settings.responseDelayMinutes > 0
        ? settings.responseDelayMinutes * 60 * 1000
        : (20 + Math.floor(Math.random() * 40)) * 1000;
      const typingInterval = setInterval(() => sendTyping(creator.botToken, chatId, bizId), 4500);
      await sendTyping(creator.botToken, chatId, bizId);
      await new Promise(r => setTimeout(r, delayMs));
      clearInterval(typingInterval);

      const reply = await chatWithAI(systemPrompt, userText, history);

      // Sépare en bulles sur ||| ou sur les sauts de ligne
      const rawBubbles = reply.includes("|||")
        ? reply.split("|||")
        : reply.split(/\n{1,}/);

      const bubbles = rawBubbles
        .map(b => b.trim())
        .filter(b => b.length > 0)
        .slice(0, 4);

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

  // Répondre IMMÉDIATEMENT à Telegram (évite timeout 25s)
  // Le traitement se fait en arrière-plan
  handleUpdate(creatorId, update).catch(err => console.error("[Bot background error]", err));

  return NextResponse.json({ ok: true });
}
