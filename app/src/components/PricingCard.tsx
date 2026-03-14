'use client';

import { Check, Zap } from 'lucide-react';
import { PricingPlan } from '@/lib/types';

interface PricingCardProps {
  plan: PricingPlan;
  onSelect: (planId: string) => void;
  loading?: boolean;
  currentPlan?: string;
}

export default function PricingCard({ plan, onSelect, loading, currentPlan }: PricingCardProps) {
  const isCurrentPlan = currentPlan === plan.id;

  return (
    <div
      className={`relative p-6 rounded-2xl border transition-all ${
        plan.popular
          ? 'bg-indigo-950 border-indigo-500 shadow-lg shadow-indigo-500/20'
          : 'bg-gray-900 border-gray-800 hover:border-gray-600'
      }`}
    >
      {plan.popular && (
        <div className="absolute -top-3 left-1/2 -translate-x-1/2">
          <span className="bg-indigo-500 text-white text-xs font-bold px-3 py-1 rounded-full">
            MOST POPULAR
          </span>
        </div>
      )}

      <div className="mb-6">
        <h3 className="text-white font-bold text-xl mb-1">{plan.name}</h3>
        <div className="flex items-baseline gap-1">
          <span className="text-white text-4xl font-bold">${plan.price}</span>
          {plan.price > 0 && <span className="text-gray-400 text-sm">/month</span>}
        </div>
        <div className="flex items-center gap-1 mt-2 text-yellow-400 text-sm">
          <Zap className="w-4 h-4" />
          <span>{plan.credits} credits/month</span>
        </div>
      </div>

      <ul className="space-y-3 mb-6">
        {plan.features.map((feature, i) => (
          <li key={i} className="flex items-start gap-2 text-sm">
            <Check className="w-4 h-4 text-green-400 mt-0.5 flex-shrink-0" />
            <span className="text-gray-300">{feature}</span>
          </li>
        ))}
      </ul>

      <button
        onClick={() => onSelect(plan.id)}
        disabled={loading || isCurrentPlan}
        className={`w-full py-3 rounded-xl font-semibold text-sm transition-all ${
          isCurrentPlan
            ? 'bg-gray-700 text-gray-400 cursor-not-allowed'
            : plan.popular
            ? 'bg-indigo-600 hover:bg-indigo-500 text-white shadow-lg'
            : 'bg-gray-800 hover:bg-gray-700 text-white'
        }`}
      >
        {loading
          ? 'Processing...'
          : isCurrentPlan
          ? 'Current Plan'
          : plan.price === 0
          ? 'Get Started Free'
          : `Get ${plan.name}`}
      </button>
    </div>
  );
}
