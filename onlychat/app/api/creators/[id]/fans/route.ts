import { NextRequest, NextResponse } from "next/server";
import fs from "fs";
import path from "path";

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
}

function filePath(creatorId: string) {
  return path.join(process.cwd(), "data", "creators", `${creatorId}-fans.json`);
}

export function loadFans(creatorId: string): Fan[] {
  try {
    const f = filePath(creatorId);
    if (!fs.existsSync(f)) return [];
    return JSON.parse(fs.readFileSync(f, "utf-8"));
  } catch { return []; }
}

export function saveFans(creatorId: string, fans: Fan[]) {
  const dir = path.join(process.cwd(), "data", "creators");
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

export async function PATCH(req: NextRequest, { params }: Ctx) {
  const { id } = await params;
  const body = await req.json();
  const fans = loadFans(id);

  if (body.all !== undefined) {
    // Toggle IA pour tous
    saveFans(id, fans.map(f => ({ ...f, enableIA: body.enableIA })));
    return NextResponse.json({ ok: true });
  }

  const idx = fans.findIndex(f => f.id === body.fanId);
  if (idx < 0) return NextResponse.json({ error: "Fan introuvable" }, { status: 404 });
  fans[idx] = { ...fans[idx], ...body };
  saveFans(id, fans);
  return NextResponse.json({ ok: true });
}
