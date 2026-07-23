import { NextRequest, NextResponse } from "next/server";
import Stripe from "stripe";
import { createServerClient } from "@supabase/ssr";
import { loadUserBilling } from "@/lib/billing-store";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const stripe = new Stripe(process.env.STRIPE_SECRET_KEY!, {} as any);

export async function POST(req: NextRequest) {
  try {
    const supabase = createServerClient(
      process.env.NEXT_PUBLIC_SUPABASE_URL!,
      process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
      { cookies: { getAll: () => req.cookies.getAll(), setAll: () => {} } }
    );
    const { data: { user } } = await supabase.auth.getUser();
    if (!user) return NextResponse.json({ error: "Non authentifié" }, { status: 401 });

    const billing = loadUserBilling(user.id, user.email ?? "");
    const customerId = (billing as Record<string, unknown>).stripeCustomerId as string | undefined;

    if (!customerId) {
      return NextResponse.json({ error: "Aucun abonnement actif" }, { status: 400 });
    }

    const baseUrl = process.env.NEXT_PUBLIC_URL || "https://chat-ai-pro.onrender.com";
    const session = await stripe.billingPortal.sessions.create({
      customer: customerId,
      return_url: `${baseUrl}/dashboard/subscription`,
    });

    return NextResponse.json({ url: session.url });
  } catch (err) {
    console.error("Stripe portal error:", err);
    return NextResponse.json({ error: "Erreur Stripe" }, { status: 500 });
  }
}
