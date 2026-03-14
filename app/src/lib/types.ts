export type PlanTier = 'free' | 'starter' | 'pro' | 'agency';

export interface User {
  id: string;
  email: string;
  name: string;
  plan: PlanTier;
  credits: number;
  stripeCustomerId?: string;
  createdAt: string;
}

export interface ResearchResult {
  id: string;
  niche: string;
  marketSize: string;
  competition: 'low' | 'medium' | 'high';
  revenueModel: string;
  startupCost: string;
  timeToRevenue: string;
  score: number;
  opportunities: string[];
  risks: string[];
  actionPlan: string[];
  keywords: string[];
  createdAt: string;
}

export interface ContentResult {
  id: string;
  title: string;
  content: string;
  type: 'blog' | 'landing' | 'email' | 'social' | 'ad';
  keywords: string[];
  seoScore: number;
  wordCount: number;
  createdAt: string;
}

export interface BusinessIdea {
  id: string;
  name: string;
  description: string;
  targetMarket: string;
  revenueStreams: string[];
  validationScore: number;
  feedback: string;
  nextSteps: string[];
  createdAt: string;
}

export interface AgentTask {
  id: string;
  type: 'research' | 'content' | 'validate' | 'competitor';
  status: 'pending' | 'running' | 'completed' | 'failed';
  input: Record<string, string>;
  output?: string;
  creditsUsed: number;
  createdAt: string;
}

export interface PricingPlan {
  id: PlanTier;
  name: string;
  price: number;
  priceId: string;
  credits: number;
  features: string[];
  popular?: boolean;
}
