import { NextRequest, NextResponse } from "next/server";
import { getClient } from "@/lib/telegram-client";
import { analyzeTelegramExport } from "@/lib/style-analyzer";
import fs from "fs";
import path from "path";
import { getDataDir } from "@/lib/data-dir";

const STYLE_FILE = () => path.join(getDataDir(), "style-profile.json");

export async function GET() {
  // Liste les conversations disponibles
  try {
    const client = await getClient();
    const dialogs = await client.getDialogs({ limit: 30 });

    const list = dialogs
      .filter(d => d.isUser || d.isGroup || d.isChannel)
      .map(d => ({
        id: d.id?.toString(),
        name: d.title || d.name || "Sans nom",
        type: d.isUser ? "user" : d.isGroup ? "group" : "channel",
        unreadCount: d.unreadCount,
      }));

    await client.disconnect();
    return NextResponse.json({ dialogs: list });
  } catch (err) {
    console.error(err);
    return NextResponse.json({ error: "Non connecté ou erreur" }, { status: 500 });
  }
}

export async function POST(req: NextRequest) {
  const { dialogId, yourName, limit = 500 } = await req.json();

  try {
    const client = await getClient();

    const messages: { from: string; text: string; type: "text" | "media" }[] = [];
    const entity = await client.getEntity(dialogId);

    let hitMedia = false;
    let fetched = 0;

    for await (const message of client.iterMessages(entity, { limit })) {
      if (hitMedia) break;
      fetched++;

      const hasMedia = !!(message.photo || message.video || message.document || message.audio || message.voice || message.sticker);

      if (hasMedia) {
        // Premier média trouvé → on s'arrête
        hitMedia = true;
        break;
      }

      if (message.text && message.text.trim()) {
        const senderName = (message.sender as { firstName?: string; lastName?: string; username?: string })?.firstName
          || (message.sender as { firstName?: string; lastName?: string; username?: string })?.username
          || "Inconnu";

        messages.push({
          from: senderName,
          text: message.text,
          type: "text",
        });
      }
    }

    await client.disconnect();

    if (messages.length === 0) {
      return NextResponse.json({ error: "Aucun message texte trouvé avant le premier média" }, { status: 400 });
    }

    // Adapte au format attendu par l'analyseur
    const exportData = {
      name: yourName,
      messages: messages.reverse().map((m, i) => ({
        id: i,
        type: "message",
        date: new Date().toISOString(),
        from: m.from,
        text: m.text,
      })),
    };

    const profile = analyzeTelegramExport(exportData, yourName);

    const f = STYLE_FILE();
    const dir = path.dirname(f);
    if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(f, JSON.stringify(profile, null, 2), "utf-8");

    return NextResponse.json({
      ok: true,
      messagesRead: fetched,
      textMessages: messages.length,
      stoppedAtMedia: hitMedia,
      stats: {
        totalMessages: profile.totalMessagesAnalyzed,
        examplesExtracted: profile.realExamples.length,
        topEmojis: profile.commonEmojis.slice(0, 5),
        commonPhrases: profile.commonPhrases.slice(0, 5),
        avgLength: profile.avgMessageLength,
      },
    });
  } catch (err) {
    console.error(err);
    return NextResponse.json({ error: `Erreur export: ${err}` }, { status: 500 });
  }
}
