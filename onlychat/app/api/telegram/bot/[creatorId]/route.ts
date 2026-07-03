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

/* ─── Route principale ─── */
export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ creatorId: string }> }
) {
  const { creatorId } = await params;
  const update = await req.json();

  const found = findCreator(creatorId);
  if (!found || !found.creator.enableIA) return NextResponse.json({ ok: true });

  const { creator, userId } = found;

  try {
    const msg = update.business_message || update.message;
    if (!msg?.text) return NextResponse.json({ ok: true });
    if (msg.from?.is_bot) return NextResponse.json({ ok: true });

    const chatId: number = msg.chat.id;
    const fanId = String(msg.from?.id ?? chatId);
    const fanUsername: string = msg.from?.username || "";
    const fanName: string = [msg.from?.first_name, msg.from?.last_name].filter(Boolean).join(" ") || fanUsername || fanId;
    const userText: string = msg.text;
    const bizId: string | undefined = update.business_message?.business_connection_id;
    const appBase = getWebhookBase();

    // Enregistre / récupère le fan
    let fan = upsertFan(creator.id, fanId, { name: fanName, username: fanUsername || null });
    const isNewFan = fan.completedScripts?.length === 0 && fan.activeScript === null;

    // Vérifie si l'IA est désactivée pour ce fan
    if (!fan.enableIA) return NextResponse.json({ ok: true });

    // Charge les settings & scripts
    const settings = loadCreatorSettings(userId, creator.id);
    const scripts = loadScripts(creator.id);
    const activeScripts = scripts.filter(s => s.active);

    // ── 1. Déclenchement par mot-clé ──
    const keyword = userText.trim().toLowerCase();
    const keywordScript = activeScripts.find(s =>
      s.name.toLowerCase().replace(/[^a-z0-9]/g, "") === keyword.replace(/[^a-z0-9]/g, "")
    );
    if (keywordScript && !fan.activeScript) {
      fan.activeScript = { scriptId: keywordScript.id, stepIndex: 0, messagesSinceStep: 999, startedAt: new Date().toISOString() };
      const fans = loadFans(creator.id);
      const idx = fans.findIndex(f => f.telegramId === fanId);
      if (idx >= 0) fans[idx] = fan;
      saveFans(creator.id, fans);
    }

    // ── 2. Script "First" pour les nouveaux fans ──
    if (isNewFan && !fan.activeScript) {
      const firstScript = activeScripts.find(s => s.first);
      if (firstScript) {
        fan.activeScript = { scriptId: firstScript.id, stepIndex: 0, messagesSinceStep: 999, startedAt: new Date().toISOString() };
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
      const systemPrompt = buildCreatorPrompt(settings, styleProfile);
      let history: { role: "user" | "assistant"; content: string }[] = [];
      let conversation;
      try {
        conversation = await getOrCreateConversation("telegram_business", `${creator.id}_${fanId}`, fanUsername || fanName, creator.name);
        history = await getHistory(conversation.id, 20);
      } catch { /* Supabase optionnel */ }

      // 0 min → délai aléatoire 20-59s ; sinon délai exact en minutes
      const delayMs = settings.responseDelayMinutes > 0
        ? settings.responseDelayMinutes * 60 * 1000
        : (20 + Math.floor(Math.random() * 40)) * 1000;
      // Typing visible pendant tout le délai (Telegram coupe après 5s, on renouvelle)
      const typingInterval = setInterval(() => sendTyping(creator.botToken, chatId, bizId), 4500);
      await sendTyping(creator.botToken, chatId, bizId);
      await new Promise(r => setTimeout(r, delayMs));
      clearInterval(typingInterval);

      const reply = await chatWithAI(systemPrompt, userText, history);

      if (settings.splitLongMessages && reply.length > 200) {
        const sentences = reply.match(/[^.!?\n]+[.!?\n]*/g) ?? [reply];
        let bubble = "";
        for (const s of sentences) {
          bubble += s;
          if (bubble.length > 120) {
            await sendText(creator.botToken, chatId, bubble.trim(), bizId);
            await new Promise(r => setTimeout(r, 600 + Math.random() * 400));
            bubble = "";
          }
        }
        if (bubble.trim()) await sendText(creator.botToken, chatId, bubble.trim(), bizId);
      } else {
        await sendText(creator.botToken, chatId, reply, bizId);
      }

      if (conversation) {
        await saveMessage(conversation.id, "user", userText);
        await saveMessage(conversation.id, "assistant", reply);
      }
    }

    console.log(`[Bot ${creator.name}] @${fanUsername}: "${userText.slice(0, 40)}" | script=${fan.activeScript?.scriptId ?? "none"}`);
  } catch (err) {
    console.error(`[Bot ${creator.name} error]`, err);
  }

  return NextResponse.json({ ok: true });
}
