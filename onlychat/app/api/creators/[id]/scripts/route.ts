import { NextRequest, NextResponse } from "next/server";
import { loadScripts, saveScripts, defaultScript, Script } from "@/lib/scripts-store";

type Ctx = { params: Promise<{ id: string }> };

export async function GET(_: NextRequest, { params }: Ctx) {
  const { id } = await params;
  return NextResponse.json({ scripts: loadScripts(id) });
}

export async function POST(req: NextRequest, { params }: Ctx) {
  const { id } = await params;
  const body = await req.json();

  const scripts = loadScripts(id);

  // Upsert script complet
  if (body.script) {
    const s: Script = { ...body.script, creatorId: id, updatedAt: new Date().toISOString() };
    const idx = scripts.findIndex(x => x.id === s.id);
    if (idx >= 0) scripts[idx] = s;
    else scripts.unshift(s);
    saveScripts(id, scripts);
    return NextResponse.json({ ok: true, script: s });
  }

  // Créer nouveau script vide
  const s = defaultScript(id);
  if (body.name) s.name = body.name;
  if (body.description) s.description = body.description;
  scripts.unshift(s);
  saveScripts(id, scripts);
  return NextResponse.json({ ok: true, script: s });
}

export async function PATCH(req: NextRequest, { params }: Ctx) {
  const { id } = await params;
  const { scriptId, patch } = await req.json();
  const scripts = loadScripts(id);
  const idx = scripts.findIndex(s => s.id === scriptId);
  if (idx < 0) return NextResponse.json({ error: "Script introuvable" }, { status: 404 });
  scripts[idx] = { ...scripts[idx], ...patch, updatedAt: new Date().toISOString() };
  saveScripts(id, scripts);
  return NextResponse.json({ ok: true });
}

export async function DELETE(req: NextRequest, { params }: Ctx) {
  const { id } = await params;
  const { scriptId } = await req.json();
  saveScripts(id, loadScripts(id).filter(s => s.id !== scriptId));
  return NextResponse.json({ ok: true });
}
