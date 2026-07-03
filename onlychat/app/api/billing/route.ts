import { NextRequest, NextResponse } from "next/server";
import { createServerClient } from "@supabase/ssr";
import {
  ADMIN_EMAIL, LICENSE_PRICE_USD,
  loadUserBilling, saveUserBilling, addTransaction,
  purchaseLicense, getPlatformStats,
} from "@/lib/billing-store";

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

  const billing = loadUserBilling(user.id, user.email ?? "");
  if (!billing.email && user.email) {
    billing.email = user.email;
    saveUserBilling(billing);
  }
  return NextResponse.json({ billing, licensePrice: LICENSE_PRICE_USD, isAdmin });
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

  // Acheter une licence
  if (body.action === "buy-license") {
    const result = purchaseLicense(user.id);
    return NextResponse.json(result);
  }

  return NextResponse.json({ error: "Action inconnue" }, { status: 400 });
}
