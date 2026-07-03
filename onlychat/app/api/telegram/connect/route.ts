import { NextRequest, NextResponse } from "next/server";
import { sendCode, isConnected } from "@/lib/telegram-client";
import { getDataDir } from "@/lib/data-dir";
import fs from "fs";
import path from "path";

export async function GET() {
  return NextResponse.json({ connected: isConnected() });
}

export async function POST(req: NextRequest) {
  const { phone } = await req.json();
  if (!phone) return NextResponse.json({ error: "Numéro requis" }, { status: 400 });

  try {
    const { phoneCodeHash } = await sendCode(phone);
    const dir = getDataDir();
    if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(path.join(dir, "pending-hash.json"), JSON.stringify({ phoneCodeHash, phone }));
    return NextResponse.json({ ok: true, message: "Code envoyé par Telegram" });
  } catch (err) {
    console.error(err);
    return NextResponse.json({ error: "Erreur envoi code — vérifie API_ID et API_HASH" }, { status: 500 });
  }
}

export async function DELETE() {
  try {
    const sessionFile = path.join(getDataDir(), "telegram-session.txt");
    if (fs.existsSync(sessionFile)) fs.unlinkSync(sessionFile);
    return NextResponse.json({ ok: true });
  } catch {
    return NextResponse.json({ error: "Erreur" }, { status: 500 });
  }
}
