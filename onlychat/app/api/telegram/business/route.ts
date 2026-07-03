import { NextRequest, NextResponse } from "next/server";
import { chatWithAI } from "@/lib/claude";
import { loadSettings } from "@/lib/settings-store";
import { buildSystemPrompt } from "@/lib/prompt-builder";
import { getOrCreateConversation, saveMessage, getHistory } from "@/lib/conversation-store";
import fs from "fs";
import path from "path";
import { getDataDir } from "@/lib/data-dir";

const CONFIG_FILE = () => path.join(getDataDir(), "bot-config.json");
const STYLE_FILE = () => path.join(getDataDir(), "style-profile.json");

interface BotConfig {
  token: string;
  botInfo: { id: number; username: string; first_name: string } | null;
  webhookSet: boolean;
  businessEnabled: boolean;
}

function loadConfig(): BotConfig | null {
  try {
    const f = CONFIG_FILE();
    if (!fs.existsSync(f)) return null;
    return JSON.parse(fs.readFileSync(f, "utf-8"));
  } catch { return null; }
}

function saveConfig(config: BotConfig) {
  const f = CONFIG_FILE();
  const dir = path.dirname(f);
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(f, JSON.stringify(config, null, 2));
}

function loadStyleProfile() {
  try {
    const f = STYLE_FILE();
    if (!fs.existsSync(f)) return null;
    return JSON.parse(fs.readFileSync(f, "utf-8"));
  } catch { return null; }
}

async function telegramAPI(token: string, method: string, body?: Record<string, unknown>) {
  const res = await fetch(`https://api.telegram.org/bot${token}/${method}`, {
    method: body ? "POST" : "GET",
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  return res.json();
}

// GET — statut du bot
export async function GET() {
  const config = loadConfig();
  if (!config) return NextResponse.json({ connected: false, botToken: null, botInfo: null, webhookSet: false, businessEnabled: false });
  return NextResponse.json({
    connected: true,
    botToken: config.token.slice(0, 10) + "...",
    botInfo: config.botInfo,
    webhookSet: config.webhookSet,
    businessEnabled: config.businessEnabled,
  });
}

// POST — actions : connect | set-webhook | toggle
export async function POST(req: NextRequest) {
  const body = await req.json();

  // Action : connecter le bot
  if (body.action === "connect") {
    const { token } = body;
    const me = await telegramAPI(token, "getMe");
    if (!me.ok) return NextResponse.json({ error: "Token invalide — vérifie le token @BotFather" }, { status: 400 });

    const config: BotConfig = {
      token,
      botInfo: me.result,
      webhookSet: false,
      businessEnabled: true,
    };
    saveConfig(config);
    return NextResponse.json({ ok: true, botInfo: me.result });
  }

  // Action : set-webhook
  if (body.action === "set-webhook") {
    const config = loadConfig();
    if (!config) return NextResponse.json({ error: "Bot non configuré" }, { status: 400 });

    const result = await telegramAPI(config.token, "setWebhook", {
      url: body.webhookUrl,
      allowed_updates: ["message", "business_message", "business_connection", "edited_business_message"],
    });

    if (!result.ok) return NextResponse.json({ error: result.description }, { status: 400 });

    config.webhookSet = true;
    saveConfig(config);
    return NextResponse.json({ ok: true });
  }

  // Action : toggle IA on/off
  if (body.action === "toggle") {
    const config = loadConfig();
    if (!config) return NextResponse.json({ error: "Bot non configuré" }, { status: 400 });
    config.businessEnabled = body.enabled;
    saveConfig(config);
    return NextResponse.json({ ok: true });
  }

  // ─── WEBHOOK TELEGRAM BUSINESS ─────────────────────────────────────────────
  // Reçoit les updates Telegram (messages normaux ET business)
  const update = body;
  const config = loadConfig();

  if (!config?.businessEnabled) return NextResponse.json({ ok: true });

  try {
    // Supporte : message normal ET business_message (Telegram Business)
    const msg = update.business_message || update.message;
    const isBusinessMsg = !!update.business_message;
    const businessConnectionId: string | undefined = update.business_message?.business_connection_id;

    if (!msg?.text) return NextResponse.json({ ok: true });

    const chatId: number = msg.chat.id;
    const fanId = String(msg.from?.id ?? chatId);
    const fanUsername: string = msg.from?.username || msg.from?.first_name || "fan";
    const userText: string = msg.text;

    // Ignore les messages du bot lui-même
    if (msg.from?.is_bot) return NextResponse.json({ ok: true });

    const settings = loadSettings();
    const styleProfile = loadStyleProfile();
    const systemPrompt = buildSystemPrompt(settings, styleProfile);

    // Historique
    let conversation;
    let history: { role: "user" | "assistant"; content: string }[] = [];
    try {
      conversation = await getOrCreateConversation("telegram_business", fanId, fanUsername, settings.creatorName);
      history = await getHistory(conversation.id, 20);
    } catch { /* Supabase optionnel */ }

    // Délai humain
    await new Promise(r => setTimeout(r, 800 + Math.random() * 1500));

    // "En train d'écrire..."
    await telegramAPI(config.token, "sendChatAction", { chat_id: chatId, action: "typing" });

    // Génère la réponse
    const reply = await chatWithAI(systemPrompt, userText, history);

    // Envoie via Telegram Business (si connecté via Business) ou message normal
    const sendPayload: Record<string, unknown> = {
      chat_id: chatId,
      text: reply,
    };

    // Si c'est un message Business, répondre dans le contexte Business
    if (isBusinessMsg && businessConnectionId) {
      sendPayload.business_connection_id = businessConnectionId;
    }

    await telegramAPI(config.token, "sendMessage", sendPayload);

    // Sauvegarde en DB
    if (conversation) {
      await saveMessage(conversation.id, "user", userText);
      await saveMessage(conversation.id, "assistant", reply);
    }

    console.log(`[Business] @${fanUsername}: "${userText}" → "${reply.slice(0, 60)}..."`);
  } catch (err) {
    console.error("[Business webhook error]", err);
  }

  // Gestion connexion/déconnexion Business
  if (update.business_connection) {
    const conn = update.business_connection;
    console.log(`[Business] ${conn.is_enabled ? "Connecté" : "Déconnecté"} au compte Business ${conn.user?.username}`);
  }

  return NextResponse.json({ ok: true });
}

// DELETE — déconnecter le bot
export async function DELETE() {
  try {
    const config = loadConfig();
    if (config) {
      await telegramAPI(config.token, "deleteWebhook");
    }
    if (fs.existsSync(CONFIG_FILE())) fs.unlinkSync(CONFIG_FILE());
    return NextResponse.json({ ok: true });
  } catch {
    return NextResponse.json({ error: "Erreur" }, { status: 500 });
  }
}
