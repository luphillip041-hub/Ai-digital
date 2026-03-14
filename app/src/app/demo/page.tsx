'use client';

import { useState } from 'react';
import Link from 'next/link';
import { Brain, TrendingUp, Search, Loader2, AlertCircle, ArrowRight } from 'lucide-react';
import ResultPanel from '@/components/ResultPanel';

const DEMO_RESULTS: Record<string, unknown> = {
  niche: 'AI Writing Tools for Freelance Content Creators',
  marketSize: '$4.2B globally, growing at 23% CAGR',
  competition: 'medium',
  revenueModel: 'SaaS subscription ($19-$99/month)',
  startupCost: '$800-$2,500',
  timeToRevenue: '6-10 weeks',
  score: 82,
  opportunities: [
    'Niche down to specific content types (e.g., LinkedIn ghostwriters)',
    'Add SEO optimization features competitors lack',
    'Build in team collaboration for agencies',
  ],
  risks: [
    'OpenAI/Anthropic could compete directly',
    'Market becoming commoditized — differentiation critical',
  ],
  actionPlan: [
    'Validate with 20 interviews of freelance writers',
    'Build MVP with Claude API — target 3 key features',
    'Launch on Product Hunt and Indie Hackers',
    'Target $500/mo MRR in first 90 days',
    'Scale content marketing and SEO for organic growth',
  ],
  keywords: ['AI writing assistant', 'content creator tools', 'freelance writing software', 'AI copywriting'],
  summary: 'High opportunity niche with proven willingness to pay. Keys to success: niche specialization, UI/UX quality, and aggressive content marketing.',
};

export default function DemoPage() {
  const [topic, setTopic] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [showDemo, setShowDemo] = useState(false);
  const [error, setError] = useState('');

  const handleDemo = () => {
    setLoading(true);
    setTimeout(() => {
      setResult(DEMO_RESULTS);
      setLoading(false);
    }, 1500);
  };

  const handleReal = async () => {
    if (!topic.trim()) return;
    setError('');
    setLoading(true);
    setResult(null);

    const res = await fetch('/api/agents/research', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ topic }),
    });

    const data = await res.json();
    setLoading(false);

    if (res.status === 401) {
      setShowDemo(true);
      return;
    }

    if (!res.ok) {
      setError(data.error || 'Failed');
      return;
    }

    setResult(data.data);
  };

  return (
    <div className="min-h-screen bg-gray-950 px-4 py-8">
      <div className="max-w-3xl mx-auto">
        {/* Header */}
        <div className="text-center mb-10">
          <Link href="/" className="inline-flex items-center gap-2 mb-8">
            <div className="w-8 h-8 bg-indigo-600 rounded-lg flex items-center justify-center">
              <Brain className="w-5 h-5 text-white" />
            </div>
            <span className="text-xl font-bold text-white">NixorAI</span>
          </Link>
          <h1 className="text-4xl font-extrabold text-white mb-3">Try the AI Research Agent</h1>
          <p className="text-gray-400 text-lg">No account needed — see what our market research agent can do</p>
        </div>

        {/* Demo Research */}
        <div className="bg-gray-900 border border-gray-800 rounded-2xl p-6 mb-6">
          <div className="flex gap-3 mb-4">
            <div className="relative flex-1">
              <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-500" />
              <input
                type="text"
                value={topic}
                onChange={e => setTopic(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleReal()}
                placeholder="Enter any niche to research..."
                className="w-full pl-12 pr-4 py-3.5 bg-gray-800 border border-gray-700 rounded-xl text-white placeholder-gray-500 focus:outline-none focus:border-indigo-500"
              />
            </div>
            <button
              onClick={handleReal}
              disabled={loading || !topic.trim()}
              className="px-5 py-3.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl disabled:opacity-50 flex items-center gap-2 whitespace-nowrap"
            >
              {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <TrendingUp className="w-4 h-4" />}
              Research
            </button>
          </div>

          {error && (
            <div className="flex items-center gap-2 p-3 bg-red-950 border border-red-800 rounded-lg text-red-400 text-sm mb-3">
              <AlertCircle className="w-4 h-4" />
              {error}
            </div>
          )}

          <div className="flex items-center gap-3">
            <div className="flex-1 h-px bg-gray-800" />
            <span className="text-gray-500 text-xs">or try a pre-built demo</span>
            <div className="flex-1 h-px bg-gray-800" />
          </div>

          <button
            onClick={handleDemo}
            disabled={loading}
            className="w-full mt-3 py-3 bg-gray-800 hover:bg-gray-700 border border-gray-700 text-gray-300 rounded-xl text-sm font-medium transition-colors disabled:opacity-50"
          >
            Show Demo: AI Writing Tools Niche Analysis
          </button>
        </div>

        {loading && (
          <div className="text-center py-12">
            <Loader2 className="w-10 h-10 text-indigo-400 animate-spin mx-auto mb-4" />
            <p className="text-white font-semibold">Running Market Research Agent...</p>
          </div>
        )}

        {/* Upsell when not logged in */}
        {showDemo && (
          <div className="p-6 bg-indigo-950 border border-indigo-700 rounded-2xl mb-6">
            <h3 className="text-white font-bold mb-2">Create a free account to run live research</h3>
            <p className="text-indigo-300 text-sm mb-4">Get 5 free credits — no credit card required.</p>
            <Link
              href="/register"
              className="inline-flex items-center gap-2 px-6 py-3 bg-indigo-600 hover:bg-indigo-500 text-white font-semibold rounded-xl transition-colors"
            >
              Start Free
              <ArrowRight className="w-4 h-4" />
            </Link>
          </div>
        )}

        {result && (
          <ResultPanel
            title="Market Research Results"
            data={result}
            onClose={() => setResult(null)}
          />
        )}

        <div className="text-center mt-8">
          <Link
            href="/register"
            className="inline-flex items-center gap-2 px-8 py-4 bg-indigo-600 hover:bg-indigo-500 text-white font-bold rounded-xl transition-colors"
          >
            Get Started Free — 5 Credits Included
            <ArrowRight className="w-5 h-5" />
          </Link>
        </div>
      </div>
    </div>
  );
}
