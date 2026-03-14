import { PricingPlan } from './types';

export const PLANS: PricingPlan[] = [
  {
    id: 'free',
    name: 'Free',
    price: 0,
    priceId: '',
    credits: 5,
    features: [
      '5 AI research queries/month',
      '3 content generations',
      'Basic niche analyzer',
      'Community access',
    ],
  },
  {
    id: 'starter',
    name: 'Starter',
    price: 19,
    priceId: process.env.STRIPE_PRICE_STARTER || 'price_starter',
    credits: 100,
    features: [
      '100 AI research queries/month',
      'Unlimited content generation',
      'Market size estimator',
      'Competitor analysis',
      'Email support',
      'Export to PDF/CSV',
    ],
  },
  {
    id: 'pro',
    name: 'Pro',
    price: 49,
    priceId: process.env.STRIPE_PRICE_PRO || 'price_pro',
    credits: 500,
    features: [
      '500 AI research queries/month',
      'Everything in Starter',
      'Multi-agent deep research',
      'Business plan generator',
      'Revenue projections',
      'Priority support',
      'API access',
    ],
    popular: true,
  },
  {
    id: 'agency',
    name: 'Agency',
    price: 149,
    priceId: process.env.STRIPE_PRICE_AGENCY || 'price_agency',
    credits: 2000,
    features: [
      '2000 AI research queries/month',
      'Everything in Pro',
      'White-label reports',
      'Client management',
      'Custom AI agents',
      'Dedicated account manager',
      'SLA guarantee',
    ],
  },
];

export const CREDIT_COSTS: Record<string, number> = {
  market_research: 5,
  content_generation: 2,
  business_validation: 3,
  competitor_analysis: 4,
  deep_research: 10,
};
