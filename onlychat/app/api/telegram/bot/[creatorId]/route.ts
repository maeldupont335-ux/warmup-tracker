import { NextRequest, NextResponse } from "next/server";
import { chatWithAI } from "@/lib/claude";
import { loadSettings } from "@/lib/settings-store";
import { buildSystemPrompt } from "@/lib/prompt-builder";
import { getOrCreateConversation, saveMessage, getHistory } from "@/lib/conversation-store";
import { upsertFan } from "@/app/api/creators/[id]/fans/route";
import fs from "fs";
import path from "path";
import type { Creator } from "@/app/api/creators/route";

const CREATORS_FILE = path.join(process.cwd(), "data", "creators.json");
const STYLE_FILE = path.join(process.cwd(), "data", "style-profile.json");

function loadCreators(): Creator[] {
  try {
    if (!fs.existsSync(CREATORS_FILE)) return [];
    return JSON.parse(fs.readFileSync(CREATORS_FILE, "utf-8"));
  } catch { return []; }
}

function loadStyleProfile() {
  try {
    if (!fs.existsSync(STYLE_FILE)) return null;
    return JSON.parse(fs.readFileSync(STYLE_FILE, "utf-8"));
  } catch { return null; }
}

async function sendTelegram(token: string, chatId: number, text: string, businessConnectionId?: string) {
  const payload: Record<string, unknown> = { chat_id: chatId, text };
  if (businessConnectionId) payload.business_connection_id = businessConnectionId;
  await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

async function sendTyping(token: string, chatId: number, businessConnectionId?: string) {
  const payload: Record<string, unknown> = { chat_id: chatId, action: "typing" };
  if (businessConnectionId) payload.business_connection_id = businessConnectionId;
  await fetch(`https://api.telegram.org/bot${token}/sendChatAction`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ creatorId: string }> }
) {
  const { creatorId } = await params;
  const update = await req.json();

  const creators = loadCreators();
  const creator = creators.find(c => c.id === creatorId);

  if (!creator || !creator.enableIA) return NextResponse.json({ ok: true });

  try {
    const msg = update.business_message || update.message;
    if (!msg?.text) return NextResponse.json({ ok: true });
    if (msg.from?.is_bot) return NextResponse.json({ ok: true });

    const chatId: number = msg.chat.id;
    const fanId = String(msg.from?.id ?? chatId);
    const fanUsername: string = msg.from?.username || "";
    const fanName: string = [msg.from?.first_name, msg.from?.last_name].filter(Boolean).join(" ") || fanUsername || fanId;
    const userText: string = msg.text;
    const businessConnectionId: string | undefined = update.business_message?.business_connection_id;

    // Enregistre / met à jour le fan
    upsertFan(creator.id, fanId, { name: fanName, username: fanUsername || null });

    // Vérifie si l'IA est désactivée pour ce fan spécifique
    const { loadFans } = await import("@/app/api/creators/[id]/fans/route");
    const fans = loadFans(creator.id);
    const fan = fans.find(f => f.telegramId === fanId);
    if (fan && !fan.enableIA) return NextResponse.json({ ok: true });

    // Settings + style
    const settings = loadSettings();
    // Injecte le nom de la créatrice dans le prompt
    const settingsWithName = { ...settings, creatorName: creator.name };
    const styleProfile = loadStyleProfile();
    const systemPrompt = buildSystemPrompt(settingsWithName, styleProfile);

    // Historique
    let conversation;
    let history: { role: "user" | "assistant"; content: string }[] = [];
    try {
      conversation = await getOrCreateConversation(
        "telegram_business",
        `${creator.id}_${fanId}`,
        fanUsername,
        creator.name
      );
      history = await getHistory(conversation.id, 20);
    } catch { /* Supabase optionnel */ }

    // Typing + délai humain
    await sendTyping(creator.botToken, chatId, businessConnectionId);
    await new Promise(r => setTimeout(r, 800 + Math.random() * 1500));

    // Génère la réponse
    const reply = await chatWithAI(systemPrompt, userText, history);

    // Envoie
    await sendTelegram(creator.botToken, chatId, reply, businessConnectionId);

    // Sauvegarde
    if (conversation) {
      await saveMessage(conversation.id, "user", userText);
      await saveMessage(conversation.id, "assistant", reply);
    }

    console.log(`[Bot ${creator.name}] @${fanUsername}: "${userText}" → "${reply.slice(0, 60)}"`);
  } catch (err) {
    console.error(`[Bot ${creator.name} error]`, err);
  }

  return NextResponse.json({ ok: true });
}
