import { NextRequest, NextResponse } from "next/server";
import { chatWithAI } from "@/lib/claude";
import { loadSettings } from "@/lib/settings-store";
import { buildSystemPrompt } from "@/lib/prompt-builder";
import fs from "fs";
import path from "path";
import { getDataDir } from "@/lib/data-dir";

function loadStyleProfile() {
  try {
    const file = path.join(getDataDir(), "style-profile.json");
    if (!fs.existsSync(file)) return null;
    return JSON.parse(fs.readFileSync(file, "utf-8"));
  } catch { return null; }
}
import {
  getOrCreateConversation,
  saveMessage,
  getHistory,
  incrementDailyStats,
} from "@/lib/conversation-store";

const BOT_TOKEN = process.env.TELEGRAM_BOT_TOKEN;
const TELEGRAM_API = `https://api.telegram.org/bot${BOT_TOKEN}`;

async function sendMessage(chatId: number, text: string) {
  await fetch(`${TELEGRAM_API}/sendMessage`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: chatId, text }),
  });
}

async function sendTyping(chatId: number) {
  await fetch(`${TELEGRAM_API}/sendChatAction`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: chatId, action: "typing" }),
  });
}

export async function POST(req: NextRequest) {
  try {
    const update = await req.json();
    const msg = update?.message;
    if (!msg?.text) return NextResponse.json({ ok: true });

    const chatId: number = msg.chat.id;
    const fanId = String(msg.from.id);
    const fanUsername: string = msg.from?.username || msg.from?.first_name || "fan";
    const userText: string = msg.text;

    // Charge les settings
    const settings = loadSettings();
    const styleProfile = loadStyleProfile();
    const systemPrompt = buildSystemPrompt(settings, styleProfile);

    // Récupère ou crée la conversation en Supabase
    const conversation = await getOrCreateConversation(
      "telegram",
      fanId,
      fanUsername,
      settings.creatorName || undefined
    );

    // Charge l'historique (20 derniers messages pour le contexte)
    const history = await getHistory(conversation.id, 20);

    // Montre "en train d'écrire..."
    await sendTyping(chatId);

    // Délai humain (1-3 secondes)
    await new Promise(r => setTimeout(r, 1000 + Math.random() * 2000));

    // Génère la réponse via Claude
    const reply = await chatWithAI(systemPrompt, userText, history);

    // Sauvegarde les deux messages en Supabase
    await saveMessage(conversation.id, "user", userText, { telegram_message_id: msg.message_id });
    await saveMessage(conversation.id, "assistant", reply);

    // Met à jour les stats
    await incrementDailyStats("messages_sent");

    // Envoie la réponse
    await sendMessage(chatId, reply);

    console.log(`[Telegram] @${fanUsername} → "${userText}" | IA → "${reply}"`);

    return NextResponse.json({ ok: true });
  } catch (err) {
    console.error("[Telegram webhook error]", err);
    return NextResponse.json({ error: "Internal error" }, { status: 500 });
  }
}
