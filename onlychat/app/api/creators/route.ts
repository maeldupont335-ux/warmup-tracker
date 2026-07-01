import { NextRequest, NextResponse } from "next/server";
import fs from "fs";
import path from "path";

const FILE = path.join(process.cwd(), "data", "creators.json");

export interface Creator {
  id: string;
  name: string;
  botUsername: string;
  botToken: string;
  businessConnection: string | null; // @username connecté via Telegram Business
  license: "none" | "telegram" | "onlyfans";
  syncStatus: "active" | "inactive";
  autoRenew: boolean;
  enableIA: boolean;
  webhookSet: boolean;
  createdAt: string;
}

function load(): Creator[] {
  try {
    if (!fs.existsSync(FILE)) return [];
    return JSON.parse(fs.readFileSync(FILE, "utf-8"));
  } catch { return []; }
}

function save(creators: Creator[]) {
  const dir = path.dirname(FILE);
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(FILE, JSON.stringify(creators, null, 2));
}

async function telegramAPI(token: string, method: string, body?: Record<string, unknown>) {
  const res = await fetch(`https://api.telegram.org/bot${token}/${method}`, {
    method: body ? "POST" : "GET",
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  return res.json();
}

// GET — liste tous les créateurs
export async function GET() {
  return NextResponse.json({ creators: load() });
}

// POST — ajouter un créateur ou action sur un créateur existant
export async function POST(req: NextRequest) {
  const body = await req.json();

  // Action sur un créateur existant
  if (body.action && body.id) {
    const creators = load();
    const idx = creators.findIndex(c => c.id === body.id);
    if (idx === -1) return NextResponse.json({ error: "Créateur introuvable" }, { status: 404 });

    if (body.action === "toggle-ia") {
      creators[idx].enableIA = body.value;
      save(creators);
      return NextResponse.json({ ok: true });
    }

    if (body.action === "toggle-renew") {
      creators[idx].autoRenew = body.value;
      save(creators);
      return NextResponse.json({ ok: true });
    }

    if (body.action === "set-webhook") {
      const c = creators[idx];
      if (!body.appUrl) return NextResponse.json({ error: "appUrl manquant" }, { status: 400 });
      const webhookUrl = `${body.appUrl}/api/telegram/bot/${c.id}`;
      console.log("[set-webhook] URL:", webhookUrl);
      const result = await telegramAPI(c.botToken, "setWebhook", {
        url: webhookUrl,
        allowed_updates: ["message", "business_message", "business_connection"],
      });
      console.log("[set-webhook] Telegram response:", JSON.stringify(result));
      if (!result.ok) return NextResponse.json({ error: result.description ?? "Telegram a refusé le webhook" }, { status: 400 });
      creators[idx].webhookSet = true;
      creators[idx].syncStatus = "active";
      save(creators);
      return NextResponse.json({ ok: true, webhookUrl });
    }

    if (body.action === "set-business") {
      creators[idx].businessConnection = body.username || null;
      save(creators);
      return NextResponse.json({ ok: true });
    }

    if (body.action === "assign-license") {
      creators[idx].license = body.license;
      save(creators);
      return NextResponse.json({ ok: true });
    }

    if (body.action === "renew-token") {
      const newToken = body.botToken;
      if (!newToken) return NextResponse.json({ error: "Token manquant" }, { status: 400 });
      const me = await telegramAPI(newToken, "getMe");
      if (!me.ok) return NextResponse.json({ error: "Token invalide" }, { status: 400 });
      creators[idx].botToken = newToken;
      creators[idx].botUsername = `@${me.result.username}`;
      // Reconnecte le webhook
      const webhookUrl = `${body.appUrl}/api/telegram/bot/${creators[idx].id}`;
      const wh = await telegramAPI(newToken, "setWebhook", {
        url: webhookUrl,
        allowed_updates: ["message", "business_message", "business_connection"],
      });
      creators[idx].webhookSet = wh.ok;
      creators[idx].syncStatus = wh.ok ? "active" : "inactive";
      save(creators);
      return NextResponse.json({ ok: true });
    }

    return NextResponse.json({ error: "Action inconnue" }, { status: 400 });
  }

  // Créer un nouveau créateur
  const { name, botToken } = body;
  if (!name || !botToken) return NextResponse.json({ error: "Nom et token requis" }, { status: 400 });

  // Vérifie le token
  const me = await telegramAPI(botToken, "getMe");
  if (!me.ok) return NextResponse.json({ error: "Token bot invalide — vérifie sur @BotFather" }, { status: 400 });

  const creators = load();

  // Vérifie doublon
  if (creators.find(c => c.botToken === botToken)) {
    return NextResponse.json({ error: "Ce bot est déjà enregistré" }, { status: 400 });
  }

  const creator: Creator = {
    id: Date.now().toString(),
    name,
    botUsername: `@${me.result.username}`,
    botToken,
    businessConnection: null,
    license: "none",
    syncStatus: "inactive",
    autoRenew: false,
    enableIA: false,
    webhookSet: false,
    createdAt: new Date().toISOString(),
  };

  creators.push(creator);
  save(creators);

  return NextResponse.json({ ok: true, creator });
}

// DELETE — supprimer un créateur
export async function DELETE(req: NextRequest) {
  const { id } = await req.json();
  const creators = load();
  const c = creators.find(cr => cr.id === id);

  if (c?.botToken && c.webhookSet) {
    await telegramAPI(c.botToken, "deleteWebhook").catch(() => {});
  }

  save(creators.filter(cr => cr.id !== id));
  return NextResponse.json({ ok: true });
}
