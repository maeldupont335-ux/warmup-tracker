import { NextRequest, NextResponse } from "next/server";
import { saveStyleProfile } from "@/lib/style-store";

const SECRET = process.env.ADMIN_SECRET ?? "onlychat-admin-2026";

export async function POST(req: NextRequest) {
  const secret = req.headers.get("x-admin-secret");
  if (secret !== SECRET) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  try {
    const { creatorId, profile, profileName } = await req.json();
    if (!profile?.realExamples || !creatorId) {
      return NextResponse.json({ error: "Profil ou creatorId invalide" }, { status: 400 });
    }

    const name = profileName || profile.name || "Profil importé";
    const meta = saveStyleProfile(creatorId, profile, name, true);

    return NextResponse.json({
      ok: true,
      file: `style-${creatorId}-${meta.slug}.json`,
      examples: meta.examples,
      slug: meta.slug,
    });
  } catch (err) {
    console.error(err);
    return NextResponse.json({ error: "Erreur serveur" }, { status: 500 });
  }
}
