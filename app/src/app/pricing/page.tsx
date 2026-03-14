'use client';

import { useState } from 'react';
import Link from 'next/link';
import { Brain, Check, Zap } from 'lucide-react';
import { PLANS } from '@/lib/plans';

const CREDIT_TABLE = [
  { action: 'Market Research', cost: 5, description: 'Full niche analysis with action plan' },
  { action: 'Trend Research', cost: 5, description: 'Emerging trends & opportunity mapping' },
  { action: 'Competitor Analysis', cost: 4, description: 'Full competitive landscape map' },
  { action: 'Business Validation', cost: 3, description: 'SWOT + revenue projections' },
  { action: 'Content Generation', cost: 2, description: 'Blog, landing, email, social, or ad content' },
];

const FAQ = [
  {
    q: 'What happens when I run out of credits?',
    a: 'Credits reset monthly on your billing date. You can also upgrade your plan mid-cycle to get more credits immediately.',
  },
  {
    q: 'Can I cancel anytime?',
    a: 'Yes, cancel anytime from your account settings. Your plan stays active until the end of the billing period.',
  },
  {
    q: 'Is there an API for developers?',
    a: 'Yes! Pro and Agency plans include API access to programmatically call all AI agents.',
  },
  {
    q: 'How accurate is the market research?',
    a: 'Our agents use Claude claude-sonnet-4-6, trained on extensive market data. Results are highly accurate for digital business niches, though you should always validate with your own research.',
  },
];

export default function PricingPage() {
  const [loading, setLoading] = useState<string | null>(null);

  const handleSelect = async (planId: string) => {
    if (planId === 'free') {
      window.location.href = '/register';
      return;
    }

    setLoading(planId);
    const res = await fetch('/api/stripe/checkout', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ planId }),
    });

    const data = await res.json();
    setLoading(null);

    if (res.status === 401) {
      window.location.href = '/login';
      return;
    }

    if (data.url) {
      window.location.href = data.url;
    }
  };

  return (
    <div className="min-h-screen bg-gray-950">
      {/* Nav */}
      <nav className="py-6 px-4 border-b border-gray-800">
        <div className="max-w-6xl mx-auto flex items-center justify-between">
          <Link href="/" className="flex items-center gap-2">
            <div className="w-8 h-8 bg-indigo-600 rounded-lg flex items-center justify-center">
              <Brain className="w-5 h-5 text-white" />
            </div>
            <span className="text-xl font-bold text-white">NixorAI</span>
          </Link>
          <Link href="/login" className="text-gray-400 hover:text-white text-sm">Sign in</Link>
        </div>
      </nav>

      <div className="max-w-6xl mx-auto px-4 py-20">
        {/* Header */}
        <div className="text-center mb-16">
          <h1 className="text-5xl font-extrabold text-white mb-4">
            Choose Your Plan
          </h1>
          <p className="text-xl text-gray-400">
            Start free, scale as you find profitable niches
          </p>
        </div>

        {/* Plans */}
        <div className="grid md:grid-cols-4 gap-6 mb-20">
          {PLANS.map((plan) => (
            <div
              key={plan.id}
              className={`relative p-6 rounded-2xl border transition-all ${
                plan.popular
                  ? 'bg-indigo-950 border-indigo-500 shadow-xl shadow-indigo-500/20'
                  : 'bg-gray-900 border-gray-800'
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
                  <span className="text-white text-4xl font-extrabold">${plan.price}</span>
                  {plan.price > 0 && <span className="text-gray-400 text-sm">/mo</span>}
                </div>
                <div className="flex items-center gap-1 mt-2 text-yellow-400 text-sm">
                  <Zap className="w-4 h-4" />
                  <span>{plan.credits} credits/mo</span>
                </div>
              </div>

              <ul className="space-y-3 mb-6">
                {plan.features.map((f, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm">
                    <Check className="w-4 h-4 text-green-400 mt-0.5 flex-shrink-0" />
                    <span className="text-gray-300">{f}</span>
                  </li>
                ))}
              </ul>

              <button
                onClick={() => handleSelect(plan.id)}
                disabled={loading === plan.id}
                className={`w-full py-3 rounded-xl font-semibold text-sm transition-all ${
                  plan.popular
                    ? 'bg-indigo-600 hover:bg-indigo-500 text-white'
                    : 'bg-gray-800 hover:bg-gray-700 text-white'
                }`}
              >
                {loading === plan.id ? 'Redirecting...' : plan.price === 0 ? 'Start Free' : `Get ${plan.name}`}
              </button>
            </div>
          ))}
        </div>

        {/* Credit costs */}
        <div className="mb-20">
          <h2 className="text-2xl font-bold text-white mb-6 text-center">Credit Usage Reference</h2>
          <div className="bg-gray-900 border border-gray-800 rounded-2xl overflow-hidden">
            <table className="w-full">
              <thead>
                <tr className="border-b border-gray-800">
                  <th className="text-left p-4 text-gray-400 text-sm font-medium">Action</th>
                  <th className="text-center p-4 text-gray-400 text-sm font-medium">Credits</th>
                  <th className="text-left p-4 text-gray-400 text-sm font-medium">Description</th>
                </tr>
              </thead>
              <tbody>
                {CREDIT_TABLE.map((item, i) => (
                  <tr key={i} className="border-b border-gray-800/50 last:border-0">
                    <td className="p-4 text-white font-medium text-sm">{item.action}</td>
                    <td className="p-4 text-center">
                      <span className="inline-flex items-center gap-1 text-yellow-400 text-sm font-bold">
                        <Zap className="w-3 h-3" /> {item.cost}
                      </span>
                    </td>
                    <td className="p-4 text-gray-400 text-sm">{item.description}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* FAQ */}
        <div>
          <h2 className="text-2xl font-bold text-white mb-8 text-center">Frequently Asked Questions</h2>
          <div className="grid md:grid-cols-2 gap-6">
            {FAQ.map((item, i) => (
              <div key={i} className="p-6 bg-gray-900 border border-gray-800 rounded-xl">
                <h3 className="text-white font-semibold mb-2">{item.q}</h3>
                <p className="text-gray-400 text-sm">{item.a}</p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
