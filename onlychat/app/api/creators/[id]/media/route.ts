import { NextRequest, NextResponse } from "next/server";
import { createServerClient } from "@supabase/ssr";
import { getDataDir } from "@/lib/data-dir";
import fs from "fs";
import path from "path";

async function getUserId(req: NextRequest): Promise<string | null> {
  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    { cookies: { getAll: () => req.cookies.getAll(), setAll: () => {} } }
  );
  const { data: { user } } = await supabase.auth.getUser();
  return user?.id ?? null;
}

export function sanitizeFolder(name: string): string {
  return name.replace(/[^a-zA-Z0-9_-]/g, "-").replace(/-+/g, "-").replace(/^-|-$/g, "");
}

export function mediaDir(userId: string, creatorId: string, folder?: string) {
  const base = path.join(getDataDir(), "uploads", userId, creatorId);
  return folder ? path.join(base, sanitizeFolder(folder)) : base;
}

/** URL publique d'un fichier média (sert via /api/media/...) */
export function mediaUrl(userId: string, creatorId: string, folder: string, fileName: string) {
  return `/api/media/${userId}/${creatorId}/${sanitizeFolder(folder)}/${fileName}`;
}

type Ctx = { params: Promise<{ id: string }> };

export async function GET(req: NextRequest, { params }: Ctx) {
  const userId = await getUserId(req);
  if (!userId) return NextResponse.json({ error: "Non authentifié" }, { status: 401 });
  const { id } = await params;
  const folder = new URL(req.url).searchParams.get("folder") ?? undefined;

  const dir = mediaDir(userId, id, folder);
  if (!fs.existsSync(dir)) return NextResponse.json({ items: [] });

  const items = fs.readdirSync(dir).map(name => {
    const fullPath = path.join(dir, name);
    const stat = fs.statSync(fullPath);
    const isDir = stat.isDirectory();
    return {
      name, isDir, size: stat.size,
      url: (!isDir && folder) ? mediaUrl(userId, id, folder, name) : null,
    };
  });

  return NextResponse.json({ items });
}

export async function POST(req: NextRequest, { params }: Ctx) {
  const userId = await getUserId(req);
  if (!userId) return NextResponse.json({ error: "Non authentifié" }, { status: 401 });
  const { id } = await params;
  const folder = new URL(req.url).searchParams.get("folder") ?? "general";

  const formData = await req.formData();
  const file = formData.get("file") as File | null;
  if (!file) return NextResponse.json({ error: "Aucun fichier" }, { status: 400 });

  const dir = mediaDir(userId, id, folder);
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });

  const ext = file.name.split(".").pop() ?? "bin";
  const fileName = `${Date.now()}-${Math.random().toString(36).slice(2, 7)}.${ext}`;
  fs.writeFileSync(path.join(dir, fileName), Buffer.from(await file.arrayBuffer()));

  return NextResponse.json({ ok: true, url: mediaUrl(userId, id, folder, fileName), name: fileName });
}

export async function DELETE(req: NextRequest, { params }: Ctx) {
  const userId = await getUserId(req);
  if (!userId) return NextResponse.json({ error: "Non authentifié" }, { status: 401 });
  const { id } = await params;
  const { folder, fileName } = await req.json();

  const target = fileName
    ? path.join(mediaDir(userId, id, folder), fileName)
    : mediaDir(userId, id, folder);

  if (fs.existsSync(target)) {
    if (fs.statSync(target).isDirectory()) fs.rmSync(target, { recursive: true });
    else fs.unlinkSync(target);
  }
  return NextResponse.json({ ok: true });
}
