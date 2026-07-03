import { NextRequest, NextResponse } from "next/server";
import fs from "fs";
import path from "path";
import { getDataDir } from "@/lib/data-dir";

const SECRET = "onlychat-admin-2026";

export async function POST(req: NextRequest) {
  const secret = req.headers.get("x-admin-secret");
  if (secret !== SECRET) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  try {
    const { creatorId, profile } = await req.json();
    if (!profile?.realExamples) {
      return NextResponse.json({ error: "Profil invalide" }, { status: 400 });
    }

    const dir = getDataDir();
    if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });

    const filename = creatorId ? `style-${creatorId}.json` : "style-global.json";
    const filepath = path.join(dir, filename);
    fs.writeFileSync(filepath, JSON.stringify(profile, null, 2), "utf-8");

    return NextResponse.json({
      ok: true,
      file: filename,
      examples: profile.realExamples.length,
    });
  } catch (err) {
    console.error(err);
    return NextResponse.json({ error: "Erreur serveur" }, { status: 500 });
  }
}
