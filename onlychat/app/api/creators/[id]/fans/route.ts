import { NextRequest, NextResponse } from "next/server";
import { getDataDir } from "@/lib/data-dir";
import { createServerClient } from "@supabase/ssr";
import { isCreatorLicenseActive } from "@/lib/billing-store";
import fs from "fs";
import path from "path";

export interface ActiveScript {
  scriptId: string;
  stepIndex: number;           // étape actuelle (0-based)
  messagesSinceStep: number;   // messages échangés depuis la dernière étape
  startedAt: string;
}

export interface Fan {
  id: string;
  creatorId: string;
  name: string;
  username: string | null;
  telegramId: string;
  lastInteraction: string;
  scriptsUsed: string;
  totalStars: number | null;
  totalUsd: number | null;
  enableIA: boolean;
  tags: string[];
  activeScript: ActiveScript | null;
  completedScripts: string[];
  firstMessageAt: string;    // date du tout premier message du fan
  warmupSent: boolean;       // warm-up envoyé avant le premier script
  fanProfile: string;        // résumé du profil du fan (prénom, âge, ville, job...)
}

function filePath(creatorId: string) {
  return path.join(getDataDir(), "creators", `${creatorId}-fans.json`);
}

export function loadFans(creatorId: string): Fan[] {
  try {
    const f = filePath(creatorId);
    if (!fs.existsSync(f)) return [];
    const fans = JSON.parse(fs.readFileSync(f, "utf-8"));
    // Migration: ajouter les nouveaux champs si absents
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    return fans.map((fan: any): Fan => ({
      activeScript: null,
      completedScripts: [],
      firstMessageAt: fan.lastInteraction ?? new Date().toISOString(),
      warmupSent: false,
      fanProfile: "",
      ...fan,
    }));
  } catch { return []; }
}

export function saveFans(creatorId: string, fans: Fan[]) {
  const dir = path.join(getDataDir(), "creators");
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(filePath(creatorId), JSON.stringify(fans, null, 2));
}

export function upsertFan(creatorId: string, telegramId: string, patch: Partial<Fan>): Fan {
  const fans = loadFans(creatorId);
  const idx = fans.findIndex(f => f.telegramId === telegramId);
  if (idx >= 0) {
    fans[idx] = { ...fans[idx], ...patch, lastInteraction: new Date().toISOString() };
    saveFans(creatorId, fans);
    return fans[idx];
  }
  const fan: Fan = {
    id: Date.now().toString(),
    creatorId,
    name: patch.name ?? telegramId,
    username: patch.username ?? null,
    telegramId,
    lastInteraction: new Date().toISOString(),
    scriptsUsed: "0/0",
    totalStars: null,
    totalUsd: null,
    enableIA: true,
    tags: [],
    activeScript: null,
    completedScripts: [],
    firstMessageAt: new Date().toISOString(),
    warmupSent: false,
    fanProfile: "",
    ...patch,
  };
  fans.unshift(fan);
  saveFans(creatorId, fans);
  return fan;
}

type Ctx = { params: Promise<{ id: string }> };

export async function GET(_: NextRequest, { params }: Ctx) {
  const { id } = await params;
  return NextResponse.json({ fans: loadFans(id) });
}

async function getUserId(req: NextRequest): Promise<string | null> {
  try {
    const supabase = createServerClient(
      process.env.NEXT_PUBLIC_SUPABASE_URL!,
      process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
      { cookies: { getAll: () => req.cookies.getAll(), setAll: () => {} } }
    );
    const { data: { user } } = await supabase.auth.getUser();
    return user?.id ?? null;
  } catch { return null; }
}

export async function PATCH(req: NextRequest, { params }: Ctx) {
  const { id } = await params;
  const body = await req.json();
  const fans = loadFans(id);

  // Bloquer enableIA si pas de licence active pour ce créateur
  if (body.enableIA === true || (body.all === true && body.enableIA === true)) {
    const userId = await getUserId(req);
    if (!userId || !isCreatorLicenseActive(userId, id)) {
      return NextResponse.json({ error: "Licence Telegram requise pour activer l'IA" }, { status: 403 });
    }
  }

  if (body.all !== undefined) {
    saveFans(id, fans.map(f => ({ ...f, enableIA: body.enableIA })));
    return NextResponse.json({ ok: true });
  }

  // Lancer un script manuellement pour un fan
  if (body.action === "launch-script") {
    const idx = fans.findIndex(f => f.telegramId === body.telegramId);
    if (idx < 0) return NextResponse.json({ error: "Fan introuvable" }, { status: 404 });
    fans[idx].activeScript = {
      scriptId: body.scriptId,
      stepIndex: 0,
      messagesSinceStep: 999, // déclenche immédiatement au prochain message
      startedAt: new Date().toISOString(),
    };
    saveFans(id, fans);
    return NextResponse.json({ ok: true });
  }

  // Arrêter le script en cours
  if (body.action === "stop-script") {
    const idx = fans.findIndex(f => f.telegramId === body.telegramId);
    if (idx < 0) return NextResponse.json({ error: "Fan introuvable" }, { status: 404 });
    fans[idx].activeScript = null;
    saveFans(id, fans);
    return NextResponse.json({ ok: true });
  }

  const idx = fans.findIndex(f => f.id === body.fanId || f.telegramId === body.telegramId);
  if (idx < 0) return NextResponse.json({ error: "Fan introuvable" }, { status: 404 });
  fans[idx] = { ...fans[idx], ...body };
  saveFans(id, fans);
  return NextResponse.json({ ok: true });
}
