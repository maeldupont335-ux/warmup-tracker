import { NextRequest, NextResponse } from "next/server";
import Stripe from "stripe";

const stripe = new Stripe(process.env.STRIPE_SECRET_KEY!, {
  apiVersion: "2025-06-30.basil",
});

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

    const baseUrl = process.env.NEXT_PUBLIC_URL || "https://chat-ai-pro.onrender.com";

    const session = await stripe.checkout.sessions.create({
      mode: "subscription",
      payment_method_types: ["card"],
      line_items: [{ price: priceId, quantity: 1 }],
      success_url: `${baseUrl}/dashboard?checkout=success&plan=${plan}`,
      cancel_url: `${baseUrl}/#pricing`,
      allow_promotion_codes: true,
    });

    return NextResponse.json({ url: session.url });
  } catch (err) {
    console.error("Stripe checkout error:", err);
    return NextResponse.json({ error: "Erreur Stripe" }, { status: 500 });
  }
}
