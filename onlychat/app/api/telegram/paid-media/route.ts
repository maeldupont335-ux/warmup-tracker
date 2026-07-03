import { NextRequest, NextResponse } from "next/server";

const BOT_TOKEN = process.env.TELEGRAM_BOT_TOKEN;
const TELEGRAM_API = `https://api.telegram.org/bot${BOT_TOKEN}`;

// Envoie un média payant (Stars) via le Bot API Telegram
// https://core.telegram.org/bots/api#sendpaidmedia
export async function POST(req: NextRequest) {
  try {
    const { chatId, starCount, mediaType, mediaUrl, caption } = await req.json();

    if (!chatId || !starCount || !mediaUrl) {
      return NextResponse.json({ error: "chatId, starCount et mediaUrl requis" }, { status: 400 });
    }

    // Construction du media selon le type
    const media = [{
      type: mediaType === "video" ? "video" : "photo",
      media: mediaUrl, // URL publique ou file_id Telegram
    }];

    const payload = {
      chat_id: chatId,
      star_count: starCount,     // Prix en Stars Telegram (1 Star ≈ 0.013$)
      media,
      caption: caption || `🔒 Contenu exclusif — débloque pour ${starCount} ⭐`,
    };

    const res = await fetch(`${TELEGRAM_API}/sendPaidMedia`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    const data = await res.json();

    if (!data.ok) {
      return NextResponse.json({ error: data.description }, { status: 400 });
    }

    return NextResponse.json({ ok: true, messageId: data.result?.message_id });
  } catch (err) {
    console.error(err);
    return NextResponse.json({ error: "Erreur envoi média payant" }, { status: 500 });
  }
}

// Récupère la liste des file_id uploadés via le bot
export async function GET() {
  return NextResponse.json({
    info: "Pour envoyer un média payant, POST avec : chatId, starCount, mediaType (photo|video), mediaUrl, caption"
  });
}
