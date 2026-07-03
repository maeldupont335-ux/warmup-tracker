import { NextRequest, NextResponse } from "next/server";
import { loadSettings, saveSettings } from "@/lib/settings-store";
import { buildSystemPrompt, AISettings } from "@/lib/prompt-builder";
import { saveSettingsToDB } from "@/lib/conversation-store";

export async function GET() {
  const settings = loadSettings();
  const prompt = buildSystemPrompt(settings);
  return NextResponse.json({ settings, prompt });
}

export async function POST(req: NextRequest) {
  const body: AISettings = await req.json();

  // Sauvegarde locale (rapide)
  saveSettings(body);

  // Sauvegarde Supabase (async, ne bloque pas)
  saveSettingsToDB(body as unknown as Record<string, unknown>).catch(console.error);

  const prompt = buildSystemPrompt(body);
  return NextResponse.json({ ok: true, prompt });
}
