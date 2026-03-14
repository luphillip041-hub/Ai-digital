'use client';

import { useState } from 'react';
import Link from 'next/link';
import { Zap, ArrowLeft, Search, Loader2, AlertCircle } from 'lucide-react';
import ResultPanel from '@/components/ResultPanel';

const INDUSTRIES = [
  'AI & Machine Learning', 'Health & Wellness', 'Remote Work', 'Creator Economy',
  'Fintech', 'EdTech', 'Climate Tech', 'E-commerce',
];

export default function TrendsPage() {
  const [industry, setIndustry] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState('');

  const handleSubmit = async (industryInput = industry) => {
    if (!industryInput.trim()) return;
    setError('');
    setLoading(true);
    setResult(null);

    const res = await fetch('/api/agents/trends', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ industry: industryInput }),
    });

    const data = await res.json();
    setLoading(false);

    if (!res.ok) {
      if (res.status === 401) { window.location.href = '/login'; return; }
      setError(data.error || 'Research failed');
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
          <div className="w-10 h-10 bg-yellow-600 rounded-xl flex items-center justify-center flex-shrink-0">
            <Zap className="w-5 h-5 text-white" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-white">Trend Research Agent</h1>
            <p className="text-gray-400">Discover emerging trends and business opportunities before they become mainstream.</p>
          </div>
        </div>

        <div className="bg-gray-900 border border-gray-800 rounded-2xl p-6">
          <label className="block text-sm font-medium text-gray-400 mb-3">Enter an industry to analyze</label>
          <div className="flex gap-3 mb-4">
            <div className="relative flex-1">
              <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-500" />
              <input
                type="text"
                value={industry}
                onChange={e => setIndustry(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleSubmit()}
                placeholder="e.g. AI & Machine Learning"
                className="w-full pl-12 pr-4 py-3.5 bg-gray-800 border border-gray-700 rounded-xl text-white placeholder-gray-500 focus:outline-none focus:border-yellow-500"
              />
            </div>
            <button
              onClick={() => handleSubmit()}
              disabled={loading || !industry.trim()}
              className="px-6 py-3.5 bg-yellow-600 hover:bg-yellow-500 text-white font-semibold rounded-xl transition-colors disabled:opacity-50 flex items-center gap-2 whitespace-nowrap"
            >
              {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Zap className="w-4 h-4" />}
              Research (5 ⚡)
            </button>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            {INDUSTRIES.map((ind) => (
              <button
                key={ind}
                onClick={() => { setIndustry(ind); handleSubmit(ind); }}
                className="text-xs px-3 py-2 bg-gray-800 hover:bg-yellow-950 hover:border-yellow-700 border border-gray-700 text-gray-400 hover:text-yellow-300 rounded-lg transition-colors text-center"
              >
                {ind}
              </button>
            ))}
          </div>

          {error && (
            <div className="flex items-center gap-2 mt-3 p-3 bg-red-950 border border-red-800 rounded-lg text-red-400 text-sm">
              <AlertCircle className="w-4 h-4" />
              {error}
            </div>
          )}
        </div>

        {loading && (
          <div className="text-center py-16">
            <Loader2 className="w-10 h-10 text-yellow-400 animate-spin mx-auto mb-4" />
            <p className="text-white font-semibold">Scanning for emerging trends...</p>
            <p className="text-gray-400 text-sm">Analyzing market signals and growth indicators</p>
          </div>
        )}

        {result && (
          <ResultPanel
            title="Trend Research Results"
            data={result}
            onClose={() => setResult(null)}
          />
        )}
      </div>
    </div>
  );
}
