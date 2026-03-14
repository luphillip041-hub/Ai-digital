import { NextRequest, NextResponse } from 'next/server';
import Stripe from 'stripe';
import { DEMO_USERS } from '@/lib/auth';
import { PLANS } from '@/lib/plans';

const stripe = new Stripe(process.env.STRIPE_SECRET_KEY || 'sk_test_placeholder', {
  apiVersion: '2026-02-25.clover' as const,
});

export async function POST(request: NextRequest) {
  const body = await request.text();
  const sig = request.headers.get('stripe-signature');
  const webhookSecret = process.env.STRIPE_WEBHOOK_SECRET;

  if (!sig || !webhookSecret) {
    return NextResponse.json({ error: 'Missing signature' }, { status: 400 });
  }

  let event: Stripe.Event;
  try {
    event = stripe.webhooks.constructEvent(body, sig, webhookSecret);
  } catch {
    return NextResponse.json({ error: 'Invalid signature' }, { status: 400 });
  }

  if (event.type === 'checkout.session.completed') {
    const session = event.data.object as Stripe.Checkout.Session;
    const { userId, planId } = session.metadata || {};

    if (userId && planId) {
      const plan = PLANS.find(p => p.id === planId);
      if (plan) {
        // Update user in DB (here using in-memory store for demo)
        const user = Object.values(DEMO_USERS).find(u => u.id === userId);
        if (user) {
          user.plan = planId;
          user.credits = plan.credits;
        }
      }
    }
  }

  return NextResponse.json({ received: true });
}
