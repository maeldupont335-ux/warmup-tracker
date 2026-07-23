import { NextRequest, NextResponse } from "next/server";
import Stripe from "stripe";
import { supabaseAdmin } from "@/lib/supabase";
import { loadUserBilling, saveUserBilling } from "@/lib/billing-store";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const stripe = new Stripe(process.env.STRIPE_SECRET_KEY!, {} as any);

export async function POST(req: NextRequest) {
  const body = await req.text();
  const sig = req.headers.get("stripe-signature");

  if (!sig) return NextResponse.json({ error: "No signature" }, { status: 400 });

  let event: Stripe.Event;
  try {
    event = stripe.webhooks.constructEvent(body, sig, process.env.STRIPE_WEBHOOK_SECRET!);
  } catch {
    return NextResponse.json({ error: "Invalid signature" }, { status: 400 });
  }

  switch (event.type) {
    case "checkout.session.completed": {
      const session = event.data.object as Stripe.Checkout.Session;
      const email = session.customer_details?.email || session.customer_email;
      const planKey = session.metadata?.plan || "";
      if (email) {
        const { data } = await supabaseAdmin.auth.admin.listUsers();
        const user = data?.users?.find(u => u.email === email);
        if (user) {
          const billing = loadUserBilling(user.id, email);
          (billing as Record<string, unknown>).stripePlan = planKey;
          (billing as Record<string, unknown>).stripeCustomerId = session.customer;
          (billing as Record<string, unknown>).stripeSubscriptionId = session.subscription;
          saveUserBilling(billing);
        }
      }
      break;
    }
    case "customer.subscription.deleted": {
      const sub = event.data.object as Stripe.Subscription;
      const customerId = sub.customer as string;
      const { data } = await supabaseAdmin.auth.admin.listUsers();
      for (const user of data?.users ?? []) {
        const billing = loadUserBilling(user.id, user.email ?? "");
        if ((billing as Record<string, unknown>).stripeCustomerId === customerId) {
          (billing as Record<string, unknown>).stripePlan = null;
          (billing as Record<string, unknown>).stripeSubscriptionId = null;
          saveUserBilling(billing);
          break;
        }
      }
      break;
    }
  }

  return NextResponse.json({ received: true });
}
