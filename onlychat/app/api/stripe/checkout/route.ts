import { NextRequest, NextResponse } from "next/server";
import Stripe from "stripe";
import { createServerClient } from "@supabase/ssr";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const stripe = new Stripe(process.env.STRIPE_SECRET_KEY!, {} as any);

const PRICE_IDS: Record<string, string> = {
  pro: process.env.STRIPE_PRICE_PRO!,
  premium: process.env.STRIPE_PRICE_PREMIUM!,
};

export async function POST(req: NextRequest) {
  try {
    const { plan } = await req.json();
    const priceId = PRICE_IDS[plan?.toLowerCase()];
    if (!priceId) {
      return NextResponse.json({ error: "Plan invalide" }, { status: 400 });
    }

    // Récupère l'email de l'utilisateur connecté si possible
    let email: string | undefined;
    try {
      const supabase = createServerClient(
        process.env.NEXT_PUBLIC_SUPABASE_URL!,
        process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
        { cookies: { getAll: () => req.cookies.getAll(), setAll: () => {} } }
      );
      const { data: { user } } = await supabase.auth.getUser();
      email = user?.email ?? undefined;
    } catch { /* non authentifié — pas grave */ }

    const baseUrl = process.env.NEXT_PUBLIC_URL || "https://chat-ai-pro.onrender.com";

    const session = await stripe.checkout.sessions.create({
      mode: "subscription",
      payment_method_types: ["card"],
      line_items: [{ price: priceId, quantity: 1 }],
      success_url: `${baseUrl}/dashboard?checkout=success&plan=${plan}`,
      cancel_url: `${baseUrl}/#pricing`,
      allow_promotion_codes: true,
      metadata: { plan },
      customer_email: email || undefined,
    });

    return NextResponse.json({ url: session.url });
  } catch (err) {
    console.error("Stripe checkout error:", err);
    return NextResponse.json({ error: "Erreur Stripe" }, { status: 500 });
  }
}
