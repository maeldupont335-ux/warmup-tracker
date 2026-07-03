import { NextRequest, NextResponse } from "next/server";
import { chatWithAI } from "@/lib/claude";
import { loadSettings } from "@/lib/settings-store";
import { buildSystemPrompt } from "@/lib/prompt-builder";
import { getOrCreateConversation, saveMessage, getHistory } from "@/lib/conversation-store";
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

export async function POST(req: NextRequest) {
  try {
    const { message, fanId = "test-user", platform = "test" } = await req.json();
    if (!message?.trim()) return NextResponse.json({ error: "Message vide" }, { status: 400 });

    const settings = loadSettings();
    const styleProfile = loadStyleProfile();
    const systemPrompt = buildSystemPrompt(settings, styleProfile);

    // Historique Supabase
    let reply: string;
    try {
      const conversation = await getOrCreateConversation(platform, fanId, fanId, settings.creatorName);
      const history = await getHistory(conversation.id, 20);
      reply = await chatWithAI(systemPrompt, message, history);
      await saveMessage(conversation.id, "user", message);
      await saveMessage(conversation.id, "assistant", reply);
    } catch {
      // Fallback sans Supabase
      reply = await chatWithAI(systemPrompt, message);
    }

    return NextResponse.json({ reply, systemPrompt });
  } catch (err) {
    console.error(err);
    return NextResponse.json({ error: "Erreur IA — vérifie ta clé ANTHROPIC_API_KEY" }, { status: 500 });
  }
}
