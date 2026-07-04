import { NextRequest, NextResponse } from "next/server";
import { createServerClient } from "@supabase/ssr";
import {
  ADMIN_EMAIL, LICENSE_PRICE_USD,
  loadUserBilling, saveUserBilling, addTransaction,
  purchaseLicense, getPlatformStats,
  purchaseCreatorLicense, setCreatorAutoRenew, autoRenewExpiredLicenses,
  buyTelegramLicenses,
} from "@/lib/billing-store";
import fs from "fs";
import path from "path";
import { getDataDir } from "@/lib/data-dir";

async function getUser(req: NextRequest) {
  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    { cookies: { getAll: () => req.cookies.getAll(), setAll: () => {} } }
  );
  const { data: { user } } = await supabase.auth.getUser();
  return user;
}

// GET — infos billing de l'utilisateur courant (ou stats admin)
export async function GET(req: NextRequest) {
  const user = await getUser(req);
  if (!user) return NextResponse.json({ error: "Non authentifié" }, { status: 401 });

  const isAdmin = user.email === ADMIN_EMAIL;
  if (isAdmin && new URL(req.url).searchParams.get("admin") === "1") {
    return NextResponse.json(getPlatformStats());
  }

  autoRenewExpiredLicenses(user.id);
  const billing = loadUserBilling(user.id, user.email ?? "");
  if (!billing.email && user.email) {
    billing.email = user.email;
    saveUserBilling(billing);
  }
  const creators = _loadCreatorsForUser(user.id);
  return NextResponse.json({ billing, licensePrice: LICENSE_PRICE_USD, isAdmin, creators });
}

// POST — actions billing
export async function POST(req: NextRequest) {
  const user = await getUser(req);
  if (!user) return NextResponse.json({ error: "Non authentifié" }, { status: 401 });

  const body = await req.json();

  // Dépôt (admin seulement)
  if (body.action === "deposit") {
    if (user.email !== ADMIN_EMAIL)
      return NextResponse.json({ error: "Admin seulement" }, { status: 403 });
    const { targetUserId, amount } = body;
    if (!targetUserId || !amount || amount <= 0)
      return NextResponse.json({ error: "Paramètres invalides" }, { status: 400 });
    addTransaction(targetUserId, {
      type: "deposit", amount,
      description: `Dépôt admin : +${amount}$`,
    });
    return NextResponse.json({ ok: true });
  }

  // Dépôt sur son propre compte (admin se crédite lui-même)
  if (body.action === "self-deposit") {
    if (user.email !== ADMIN_EMAIL)
      return NextResponse.json({ error: "Admin seulement" }, { status: 403 });
    const { amount } = body;
    if (!amount || amount <= 0)
      return NextResponse.json({ error: "Montant invalide" }, { status: 400 });
    addTransaction(user.id, {
      type: "deposit", amount,
      description: `Dépôt admin : +${amount}$`,
    });
    return NextResponse.json({ ok: true });
  }

  // Acheter une licence (ancienne, globale)
  if (body.action === "buy-license") {
    const result = purchaseLicense(user.id);
    return NextResponse.json(result);
  }

  // Acheter des licences Telegram en pool
  if (body.action === "buy-telegram-licenses") {
    const qty = Math.max(1, parseInt(body.quantity ?? "1"));
    const result = buyTelegramLicenses(user.id, qty);
    return NextResponse.json(result);
  }

  // Acheter une licence par créateur
  if (body.action === "buy-creator-license") {
    const { creatorId, creatorName } = body;
    if (!creatorId) return NextResponse.json({ error: "creatorId requis" }, { status: 400 });
    // Auto-renew les licences expirées d'abord
    autoRenewExpiredLicenses(user.id);
    const result = purchaseCreatorLicense(user.id, creatorId, creatorName ?? creatorId);
    return NextResponse.json(result);
  }

  // Toggle auto-renouvellement
  if (body.action === "toggle-autorenew") {
    const { creatorId, autoRenew } = body;
    if (!creatorId) return NextResponse.json({ error: "creatorId requis" }, { status: 400 });
    setCreatorAutoRenew(user.id, creatorId, !!autoRenew);
    return NextResponse.json({ ok: true });
  }

  return NextResponse.json({ error: "Action inconnue" }, { status: 400 });
}

// Helper pour récupérer les créateurs depuis le fichier utilisateur
function _loadCreatorsForUser(userId: string): { id: string; name: string }[] {
  try {
    const f = path.join(getDataDir(), "users", `${userId}-creators.json`);
    if (!fs.existsSync(f)) return [];
    return JSON.parse(fs.readFileSync(f, "utf-8"));
  } catch { return []; }
}
