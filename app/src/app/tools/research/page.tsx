'use client';

import { useState, useEffect, Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { TrendingUp, ArrowLeft, Search, Loader2, AlertCircle } from 'lucide-react';
import ResultPanel from '@/components/ResultPanel';

const EXAMPLES = [
  'AI writing tools for content creators',
  'Remote work software for distributed teams',
  'Pet tech and smart pet devices',
  'Sustainable packaging for e-commerce',
  'Mental health apps for Gen Z',
  'B2B SaaS for small restaurants',
];

function ResearchForm() {
  const searchParams = useSearchParams();
  const [topic, setTopic] = useState(searchParams.get('q') || '');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    const q = searchParams.get('q');
    if (q) {
      setTopic(q);
    }
  }, [searchParams]);

  const handleSubmit = async (topicInput = topic) => {
    if (!topicInput.trim()) return;
    setError('');
    setLoading(true);
    setResult(null);

    const res = await fetch('/api/agents/research', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ topic: topicInput }),
    });

    const data = await res.json();
    setLoading(false);

    if (!res.ok) {
      if (res.status === 401) {
        window.location.href = '/login';
        return;
      }
      setError(data.error || 'Research failed');
      return;
    }

    setResult(data.data);
  };

  return (
    <>
      {/* Input */}
      <div className="bg-gray-900 border border-gray-800 rounded-2xl p-6 mb-8">
        <label className="block text-sm font-medium text-gray-400 mb-3">
          Enter a market, niche, or business idea to research
        </label>
        <div className="flex gap-3">
          <div className="relative flex-1">
            <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-500" />
            <input
              type="text"
              value={topic}
              onChange={e => setTopic(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSubmit()}
              placeholder="e.g. AI tools for freelance writers"
              className="w-full pl-12 pr-4 py-3.5 bg-gray-800 border border-gray-700 rounded-xl text-white placeholder-gray-500 focus:outline-none focus:border-indigo-500"
            />
          </div>
          <button
            onClick={() => handleSubmit()}
            disabled={loading || !topic.trim()}
            className="px-6 py-3.5 bg-indigo-600 hover:bg-indigo-500 text-white font-semibold rounded-xl transition-colors disabled:opacity-50 flex items-center gap-2 whitespace-nowrap"
          >
            {loading ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Researching...
              </>
            ) : (
              <>
                <TrendingUp className="w-4 h-4" />
                Research (5 ⚡)
              </>
            )}
          </button>
        </div>

        {error && (
          <div className="flex items-center gap-2 mt-3 p-3 bg-red-950 border border-red-800 rounded-lg text-red-400 text-sm">
            <AlertCircle className="w-4 h-4" />
            {error}
          </div>
        )}

        <div className="mt-4">
          <p className="text-gray-500 text-xs mb-2">Try these examples:</p>
          <div className="flex flex-wrap gap-2">
            {EXAMPLES.map((ex) => (
              <button
                key={ex}
                onClick={() => { setTopic(ex); handleSubmit(ex); }}
                className="text-xs px-3 py-1.5 bg-gray-800 hover:bg-gray-700 border border-gray-700 text-gray-400 hover:text-gray-200 rounded-lg transition-colors"
              >
                {ex}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Loading state */}
      {loading && (
        <div className="text-center py-16">
          <div className="inline-flex flex-col items-center gap-4">
            <div className="w-16 h-16 bg-indigo-950 border border-indigo-700 rounded-2xl flex items-center justify-center">
              <Loader2 className="w-8 h-8 text-indigo-400 animate-spin" />
            </div>
            <div>
              <p className="text-white font-semibold">AI Agent is researching...</p>
              <p className="text-gray-400 text-sm mt-1">Analyzing market size, competition, and opportunities</p>
            </div>
          </div>
        </div>
      )}

      {/* Result modal */}
      {result && (
        <ResultPanel
          title="Market Research Results"
          data={result}
          onClose={() => setResult(null)}
        />
      )}
    </>
  );
}

export default function ResearchPage() {
  return (
    <div className="min-h-screen bg-gray-950 px-4 py-8">
      <div className="max-w-3xl mx-auto">
        <Link href="/dashboard" className="inline-flex items-center gap-2 text-gray-400 hover:text-white mb-8 text-sm">
          <ArrowLeft className="w-4 h-4" />
          Back to Dashboard
        </Link>

        <div className="mb-8">
          <div className="flex items-center gap-3 mb-2">
            <div className="w-10 h-10 bg-indigo-600 rounded-xl flex items-center justify-center">
              <TrendingUp className="w-5 h-5 text-white" />
            </div>
            <h1 className="text-2xl font-bold text-white">Market Research Agent</h1>
          </div>
          <p className="text-gray-400">
            Get comprehensive market analysis including size, competition, revenue model, startup costs, and a step-by-step action plan.
          </p>
        </div>

        <Suspense>
          <ResearchForm />
        </Suspense>
      </div>
    </div>
  );
}
