import { NextRequest, NextResponse } from "next/server";
import fs from "fs";
import path from "path";
import { getWebhookBase } from "@/lib/app-config";
import { createServerClient } from "@supabase/ssr";
import { getDataDir } from "@/lib/data-dir";

export interface Creator {
  id: string;
  name: string;
  botUsername: string;
  botToken: string;
  businessConnection: string | null;
  license: "none" | "telegram" | "onlyfans";
  syncStatus: "active" | "inactive";
  autoRenew: boolean;
  enableIA: boolean;
  webhookSet: boolean;
  createdAt: string;
}

/* ── Auth ── */
async function getUserId(req: NextRequest): Promise<string | null> {
  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    { cookies: { getAll: () => req.cookies.getAll(), setAll: () => {} } }
  );
  const { data: { user } } = await supabase.auth.getUser();
  return user?.id ?? null;
}

/* ── Storage par userId ── */
function userFile(userId: string) {
  return path.join(getDataDir(), "users", `${userId}-creators.json`);
}

function load(userId: string): Creator[] {
  try {
    const f = userFile(userId);
    if (!fs.existsSync(f)) return [];
    return JSON.parse(fs.readFileSync(f, "utf-8"));
  } catch { return []; }
}

function save(userId: string, creators: Creator[]) {
  const f = userFile(userId);
  const dir = path.dirname(f);
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(f, JSON.stringify(creators, null, 2));
}

/* ── Telegram API ── */
async function telegramAPI(token: string, method: string, body?: Record<string, unknown>) {
  const res = await fetch(`https://api.telegram.org/bot${token}/${method}`, {
    method: body ? "POST" : "GET",
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  return res.json();
}

function getAppUrl(): string {
  const base = getWebhookBase();
  if (!base) throw new Error("URL de production non configurée — va dans Paramètres et entre ton URL Render.");
  return base;
}

/* ── Routes ── */
export async function GET(req: NextRequest) {
  const userId = await getUserId(req);
  if (!userId) return NextResponse.json({ error: "Non authentifié" }, { status: 401 });
  return NextResponse.json({ creators: load(userId) });
}

export async function POST(req: NextRequest) {
  const userId = await getUserId(req);
  if (!userId) return NextResponse.json({ error: "Non authentifié" }, { status: 401 });
  const body = await req.json();

  if (body.action && body.id) {
    const creators = load(userId);
    const idx = creators.findIndex(c => c.id === body.id);
    if (idx === -1) return NextResponse.json({ error: "Créateur introuvable" }, { status: 404 });

    if (body.action === "toggle-ia") {
      creators[idx].enableIA = body.value;
      save(userId, creators);
      return NextResponse.json({ ok: true });
    }
    if (body.action === "toggle-renew") {
      creators[idx].autoRenew = body.value;
      save(userId, creators);
      return NextResponse.json({ ok: true });
    }
    if (body.action === "set-webhook") {
      const c = creators[idx];
      let secureBase: string;
      try { secureBase = getAppUrl(); } catch (e) { return NextResponse.json({ error: String(e) }, { status: 400 }); }
      const webhookUrl = `${secureBase}/api/telegram/bot/${c.id}`;
      console.log("[set-webhook] URL:", webhookUrl);
      const result = await telegramAPI(c.botToken, "setWebhook", {
        url: webhookUrl,
        allowed_updates: ["message", "business_message", "business_connection"],
      });
      console.log("[set-webhook] Telegram:", JSON.stringify(result));
      if (!result.ok) return NextResponse.json({ error: `${result.description} (URL: ${webhookUrl})` }, { status: 400 });
      creators[idx].webhookSet = true;
      creators[idx].syncStatus = "active";
      save(userId, creators);
      return NextResponse.json({ ok: true, webhookUrl });
    }
    if (body.action === "set-business") {
      creators[idx].businessConnection = body.username || null;
      save(userId, creators);
      return NextResponse.json({ ok: true });
    }
    if (body.action === "assign-license") {
      creators[idx].license = body.license;
      save(userId, creators);
      return NextResponse.json({ ok: true });
    }
    if (body.action === "renew-token") {
      if (!body.botToken) return NextResponse.json({ error: "Token manquant" }, { status: 400 });
      const me = await telegramAPI(body.botToken, "getMe");
      if (!me.ok) return NextResponse.json({ error: "Token invalide" }, { status: 400 });
      creators[idx].botToken = body.botToken;
      creators[idx].botUsername = `@${me.result.username}`;
      let base: string;
      try { base = getAppUrl(); } catch (e) { return NextResponse.json({ error: String(e) }, { status: 400 }); }
      const wh = await telegramAPI(body.botToken, "setWebhook", {
        url: `${base}/api/telegram/bot/${creators[idx].id}`,
        allowed_updates: ["message", "business_message", "business_connection"],
      });
      creators[idx].webhookSet = wh.ok;
      creators[idx].syncStatus = wh.ok ? "active" : "inactive";
      save(userId, creators);
      return NextResponse.json({ ok: true });
    }
    return NextResponse.json({ error: "Action inconnue" }, { status: 400 });
  }

  // Créer un nouveau créateur
  const { name, botToken } = body;
  if (!name || !botToken) return NextResponse.json({ error: "Nom et token requis" }, { status: 400 });
  const me = await telegramAPI(botToken, "getMe");
  if (!me.ok) return NextResponse.json({ error: "Token bot invalide" }, { status: 400 });

  const creators = load(userId);
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
  save(userId, creators);
  return NextResponse.json({ ok: true, creator });
}

export async function DELETE(req: NextRequest) {
  const userId = await getUserId(req);
  if (!userId) return NextResponse.json({ error: "Non authentifié" }, { status: 401 });
  const { id } = await req.json();
  const creators = load(userId);
  const c = creators.find(cr => cr.id === id);
  if (c?.botToken && c.webhookSet) {
    await telegramAPI(c.botToken, "deleteWebhook").catch(() => {});
  }
  save(userId, creators.filter(cr => cr.id !== id));
  return NextResponse.json({ ok: true });
}
