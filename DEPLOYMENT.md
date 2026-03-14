# NixorAI — Deployment Guide

## $500 Budget Passive Revenue Strategy

### Cost Breakdown
| Item | Cost |
|------|------|
| Domain (.com) | $12/year |
| Vercel Hosting | Free (or $20/mo Pro) |
| Anthropic API (Claude) | ~$50/mo at scale |
| Stripe (payments) | 2.9% + $0.30/txn |
| **Total to launch** | **~$62 first month** |

---

## Step 1: Environment Setup

Copy `.env.example` to `.env.local` and fill in:

```bash
cp .env.example .env.local
```

### Required Keys:

1. **ANTHROPIC_API_KEY** — Get from https://console.anthropic.com
2. **STRIPE_SECRET_KEY** — Get from https://dashboard.stripe.com
3. **STRIPE_PUBLISHABLE_KEY** — From Stripe Dashboard
4. **STRIPE_WEBHOOK_SECRET** — After setting up webhook

### Stripe Setup:
1. Create products in Stripe Dashboard:
   - Starter: $19/mo
   - Pro: $49/mo
   - Agency: $149/mo
2. Copy Price IDs to `.env.local`
3. Set webhook endpoint: `https://yourdomain.com/api/stripe/webhook`
4. Add events: `checkout.session.completed`

---

## Step 2: Deploy to Vercel (Free)

```bash
npm install -g vercel
vercel deploy
```

Or connect GitHub repo at https://vercel.com/new

---

## Step 3: Revenue Projections

### Conservative (Month 1-3)
- 10 free users → 2 convert to Starter ($19) = **$38/mo**
- 1 Pro user ($49) = **$49/mo**
- Total: **~$87/mo**

### Growth (Month 4-6)
- 50 Starter users = **$950/mo**
- 10 Pro users = **$490/mo**
- 2 Agency users = **$298/mo**
- Total: **~$1,738/mo**

### Scale (Month 7-12)
- Target: 100+ paying users
- Projected MRR: **$3,000-$8,000/mo**
- ROI on $500 budget: **500-1600%**

---

## Step 4: Marketing (Organic, $0)

1. **Product Hunt launch** — Submit on Tuesday morning
2. **Indie Hackers** — Post your journey, link to tool
3. **Twitter/X** — Document building in public
4. **Reddit** — r/SaaS, r/entrepreneur, r/IndieHackers
5. **SEO content** — Use your own Content Generator!

---

## Local Development

```bash
cd app
npm install
npm run dev
```

Visit http://localhost:3000

**Demo account:** demo@nixor.ai / demo123 (Pro plan)
