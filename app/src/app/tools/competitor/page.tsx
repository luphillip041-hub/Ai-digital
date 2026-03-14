'use client';

import { useState } from 'react';
import Link from 'next/link';
import { BarChart3, ArrowLeft, Search, Loader2, AlertCircle } from 'lucide-react';
import ResultPanel from '@/components/ResultPanel';

const EXAMPLES = [
  'AI writing assistants',
  'Project management SaaS',
  'Online course platforms',
  'Personal finance apps',
  'Email marketing tools',
];

export default function CompetitorPage() {
  const [niche, setNiche] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState('');

  const handleSubmit = async (nicheInput = niche) => {
    if (!nicheInput.trim()) return;
    setError('');
    setLoading(true);
    setResult(null);

    const res = await fetch('/api/agents/competitor', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ niche: nicheInput }),
    });

    const data = await res.json();
    setLoading(false);

    if (!res.ok) {
      if (res.status === 401) { window.location.href = '/login'; return; }
      setError(data.error || 'Analysis failed');
      return;
    }

    setResult(data.data);
  };

  return (
    <div className="min-h-screen bg-gray-950 px-4 py-8">
      <div className="max-w-3xl mx-auto">
        <Link href="/dashboard" className="inline-flex items-center gap-2 text-gray-400 hover:text-white mb-8 text-sm">
          <ArrowLeft className="w-4 h-4" />
          Back to Dashboard
        </Link>

        <div className="mb-8 flex items-start gap-3">
          <div className="w-10 h-10 bg-orange-600 rounded-xl flex items-center justify-center flex-shrink-0">
            <BarChart3 className="w-5 h-5 text-white" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-white">Competitor Analysis Agent</h1>
            <p className="text-gray-400">Map the competitive landscape, identify market gaps, and build a winning entry strategy.</p>
          </div>
        </div>

        <div className="bg-gray-900 border border-gray-800 rounded-2xl p-6">
          <label className="block text-sm font-medium text-gray-400 mb-3">Enter your niche or market</label>
          <div className="flex gap-3">
            <div className="relative flex-1">
              <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-500" />
              <input
                type="text"
                value={niche}
                onChange={e => setNiche(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleSubmit()}
                placeholder="e.g. AI writing assistants"
                className="w-full pl-12 pr-4 py-3.5 bg-gray-800 border border-gray-700 rounded-xl text-white placeholder-gray-500 focus:outline-none focus:border-orange-500"
              />
            </div>
            <button
              onClick={() => handleSubmit()}
              disabled={loading || !niche.trim()}
              className="px-6 py-3.5 bg-orange-600 hover:bg-orange-500 text-white font-semibold rounded-xl transition-colors disabled:opacity-50 flex items-center gap-2 whitespace-nowrap"
            >
              {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <BarChart3 className="w-4 h-4" />}
              Analyze (4 ⚡)
            </button>
          </div>

          {error && (
            <div className="flex items-center gap-2 mt-3 p-3 bg-red-950 border border-red-800 rounded-lg text-red-400 text-sm">
              <AlertCircle className="w-4 h-4" />
              {error}
            </div>
          )}

          <div className="mt-4 flex flex-wrap gap-2">
            {EXAMPLES.map((ex) => (
              <button
                key={ex}
                onClick={() => { setNiche(ex); handleSubmit(ex); }}
                className="text-xs px-3 py-1.5 bg-gray-800 hover:bg-gray-700 border border-gray-700 text-gray-400 hover:text-gray-200 rounded-lg transition-colors"
              >
                {ex}
              </button>
            ))}
          </div>
        </div>

        {loading && (
          <div className="text-center py-16">
            <Loader2 className="w-10 h-10 text-orange-400 animate-spin mx-auto mb-4" />
            <p className="text-white font-semibold">Analyzing competitive landscape...</p>
            <p className="text-gray-400 text-sm">Identifying competitors, gaps, and strategies</p>
          </div>
        )}

        {result && (
          <ResultPanel
            title="Competitor Analysis"
            data={result}
            onClose={() => setResult(null)}
          />
        )}
      </div>
    </div>
  );
}
