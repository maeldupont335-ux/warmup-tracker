import { NextRequest, NextResponse } from "next/server";
import { analyzeTelegramExport } from "@/lib/style-analyzer";
import {
  loadStyleIndex, loadActiveStyleProfile, saveStyleProfile,
  deleteStyleProfile, setActiveProfile, getStyleProfile
} from "@/lib/style-store";

// GET /api/training?creatorId=xxx
// → { index, activeProfile }
export async function GET(req: NextRequest) {
  try {
    const creatorId = new URL(req.url).searchParams.get("creatorId") ?? "";
    if (!creatorId) return NextResponse.json({ error: "creatorId requis" }, { status: 400 });

    const index = loadStyleIndex(creatorId);
    const activeProfile = loadActiveStyleProfile(creatorId);
    return NextResponse.json({ index, activeProfile });
  } catch {
    return NextResponse.json({ index: { active: null, profiles: [] }, activeProfile: null });
  }
}

// POST /api/training
// Cas 1 : { creatorId, preAnalyzed, profileName } → upload direct d'un profil analysé
// Cas 2 : { creatorId, exportData, yourName, profileName, accumulate } → analyse + save
export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const { creatorId, preAnalyzed, exportData, yourName, profileName, accumulate } = body;

    if (!creatorId) return NextResponse.json({ error: "creatorId requis" }, { status: 400 });

    // Cas 1 : profil déjà analysé
    if (preAnalyzed?.realExamples) {
      const name = profileName || preAnalyzed.name || "Profil importé";
      const meta = saveStyleProfile(creatorId, preAnalyzed, name, true);
      return NextResponse.json({
        ok: true,
        meta,
        index: loadStyleIndex(creatorId),
        stats: {
          totalMessages: preAnalyzed.totalMessagesAnalyzed ?? 0,
          examplesExtracted: preAnalyzed.realExamples.length,
          topEmojis: preAnalyzed.commonEmojis?.slice(0, 8) ?? [],
          commonPhrases: preAnalyzed.commonPhrases?.slice(0, 6) ?? [],
          avgLength: preAnalyzed.avgMessageLength ?? 0,
          usesAbbreviations: preAnalyzed.usesAbbreviations ?? false,
          commonGreetings: preAnalyzed.commonGreetings?.slice(0, 4) ?? [],
        },
      });
    }

    // Cas 2 : export Telegram brut
    if (!exportData?.messages) {
      return NextResponse.json({ error: "Format invalide — importe un export Telegram JSON ou un profil .json" }, { status: 400 });
    }

    // Détection auto du nom
    const freq: Record<string, number> = {};
    for (const m of exportData.messages) {
      if (m.from) freq[m.from] = (freq[m.from] ?? 0) + 1;
    }
    const detectedName = yourName?.trim() || Object.entries(freq).sort((a, b) => b[1] - a[1])[0]?.[0] || "";

    const incoming = analyzeTelegramExport(exportData, detectedName);

    if (incoming.totalMessagesAnalyzed === 0) {
      const availableNames = [...new Set(
        exportData.messages.map((m: { from?: string }) => m.from).filter(Boolean)
      )].slice(0, 10) as string[];

      let bestName = "";
      let bestCount = 0;
      for (const name of availableNames) {
        const p = analyzeTelegramExport(exportData, name as string);
        if (p.totalMessagesAnalyzed > bestCount) {
          bestCount = p.totalMessagesAnalyzed;
          bestName = name as string;
        }
      }
      return NextResponse.json({
        error: yourName
          ? `Aucun message trouvé pour "${yourName}".`
          : "Impossible de détecter ton nom automatiquement.",
        availableNames,
        suggestedName: bestName,
      }, { status: 400 });
    }

    // Accumulation si demandée
    let finalProfile = incoming;
    if (accumulate) {
      const index = loadStyleIndex(creatorId);
      if (index.active) {
        const existing = getStyleProfile(creatorId, index.active);
        if (existing) {
          const allEx = [...existing.realExamples, ...incoming.realExamples];
          const seen = new Set<string>();
          finalProfile = {
            ...incoming,
            realExamples: allEx.filter(e => {
              const k = e.yourReply.slice(0, 30);
              if (seen.has(k)) return false;
              seen.add(k);
              return true;
            }).slice(0, 60),
            commonEmojis: [...new Set([...existing.commonEmojis, ...incoming.commonEmojis])].slice(0, 15),
            commonPhrases: [...new Set([...existing.commonPhrases, ...incoming.commonPhrases])].slice(0, 20),
            commonGreetings: [...new Set([...existing.commonGreetings, ...incoming.commonGreetings])].slice(0, 8),
            totalMessagesAnalyzed: existing.totalMessagesAnalyzed + incoming.totalMessagesAnalyzed,
          };
        }
      }
    }

    const name = profileName || detectedName || "Nouveau profil";
    const meta = saveStyleProfile(creatorId, finalProfile, name, true);

    return NextResponse.json({
      ok: true,
      meta,
      detectedName,
      index: loadStyleIndex(creatorId),
      stats: {
        totalMessages: finalProfile.totalMessagesAnalyzed,
        examplesExtracted: finalProfile.realExamples.length,
        topEmojis: finalProfile.commonEmojis.slice(0, 8),
        commonPhrases: finalProfile.commonPhrases.slice(0, 6),
        avgLength: finalProfile.avgMessageLength,
        usesAbbreviations: finalProfile.usesAbbreviations,
        commonGreetings: finalProfile.commonGreetings.slice(0, 4),
      },
    });
  } catch (err) {
    console.error(err);
    return NextResponse.json({ error: "Erreur lors de l'analyse" }, { status: 500 });
  }
}

// PATCH /api/training → { creatorId, activeSlug } pour changer le profil actif
export async function PATCH(req: NextRequest) {
  try {
    const { creatorId, activeSlug } = await req.json();
    if (!creatorId || !activeSlug) return NextResponse.json({ error: "Paramètres manquants" }, { status: 400 });
    setActiveProfile(creatorId, activeSlug);
    return NextResponse.json({ ok: true, index: loadStyleIndex(creatorId) });
  } catch {
    return NextResponse.json({ error: "Erreur" }, { status: 500 });
  }
}

// DELETE /api/training?creatorId=xxx&slug=yyy
export async function DELETE(req: NextRequest) {
  try {
    const url = new URL(req.url);
    const creatorId = url.searchParams.get("creatorId") ?? "";
    const slug = url.searchParams.get("slug") ?? "";
    if (!creatorId) return NextResponse.json({ error: "creatorId requis" }, { status: 400 });
    if (slug) {
      deleteStyleProfile(creatorId, slug);
    }
    return NextResponse.json({ ok: true, index: loadStyleIndex(creatorId) });
  } catch {
    return NextResponse.json({ error: "Erreur" }, { status: 500 });
  }
}
