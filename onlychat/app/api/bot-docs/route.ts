import { NextRequest, NextResponse } from "next/server";
import { createServerClient } from "@supabase/ssr";
import { loadBotDocsConfig, saveBotDocsConfig, DEFAULT_CONFIG } from "@/lib/bot-docs-store";

async function getUser(req: NextRequest) {
  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    { cookies: { getAll: () => req.cookies.getAll(), setAll: () => {} } }
  );
  const { data: { user } } = await supabase.auth.getUser();
  return user;
}

export async function GET(req: NextRequest) {
  const user = await getUser(req);
  if (!user) return NextResponse.json({ error: "Non authentifié" }, { status: 401 });
  const config = loadBotDocsConfig(user.id);
  return NextResponse.json({ config, defaults: DEFAULT_CONFIG });
}

export async function POST(req: NextRequest) {
  const user = await getUser(req);
  if (!user) return NextResponse.json({ error: "Non authentifié" }, { status: 401 });
  const body = await req.json();
  saveBotDocsConfig(user.id, { ...DEFAULT_CONFIG, ...body });
  return NextResponse.json({ ok: true });
}
