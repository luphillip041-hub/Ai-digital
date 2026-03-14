'use client';

import { useState } from 'react';
import Link from 'next/link';
import { CheckCircle, ArrowLeft, Loader2, AlertCircle } from 'lucide-react';
import ResultPanel from '@/components/ResultPanel';

const EXAMPLE_IDEAS = [
  'A SaaS tool that auto-generates LinkedIn content for B2B founders',
  'An AI-powered personal finance app for Gen Z',
  'Subscription box for specialty coffee from small farms',
  'A no-code tool for building AI chatbots without coding',
];

export default function ValidatePage() {
  const [idea, setIdea] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState('');

  const handleSubmit = async (ideaInput = idea) => {
    if (!ideaInput.trim()) return;
    setError('');
    setLoading(true);
    setResult(null);

    const res = await fetch('/api/agents/validate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ idea: ideaInput }),
    });

    const data = await res.json();
    setLoading(false);

    if (!res.ok) {
      if (res.status === 401) { window.location.href = '/login'; return; }
      setError(data.error || 'Validation failed');
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
          <div className="w-10 h-10 bg-green-600 rounded-xl flex items-center justify-center flex-shrink-0">
            <CheckCircle className="w-5 h-5 text-white" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-white">Business Validation Agent</h1>
            <p className="text-gray-400">Get an honest SWOT analysis, revenue projections, MVP features, and next steps for your idea.</p>
          </div>
        </div>

        <div className="bg-gray-900 border border-gray-800 rounded-2xl p-6 mb-6">
          <label className="block text-sm font-medium text-gray-400 mb-3">
            Describe your business idea in detail
          </label>
          <textarea
            value={idea}
            onChange={e => setIdea(e.target.value)}
            placeholder="Describe your idea: what problem it solves, who it's for, how you'd make money..."
            className="w-full px-4 py-3 bg-gray-800 border border-gray-700 rounded-xl text-white placeholder-gray-500 focus:outline-none focus:border-green-500 min-h-[120px] resize-none"
          />

          {error && (
            <div className="flex items-center gap-2 mt-3 p-3 bg-red-950 border border-red-800 rounded-lg text-red-400 text-sm">
              <AlertCircle className="w-4 h-4" />
              {error}
            </div>
          )}

          <button
            onClick={() => handleSubmit()}
            disabled={loading || !idea.trim()}
            className="mt-4 w-full py-3.5 bg-green-600 hover:bg-green-500 text-white font-semibold rounded-xl transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
          >
            {loading ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Validating Idea...
              </>
            ) : (
              <>
                <CheckCircle className="w-4 h-4" />
                Validate Business Idea (3 ⚡)
              </>
            )}
          </button>

          <div className="mt-4">
            <p className="text-gray-500 text-xs mb-2">Example ideas:</p>
            <div className="space-y-2">
              {EXAMPLE_IDEAS.map((ex) => (
                <button
                  key={ex}
                  onClick={() => { setIdea(ex); handleSubmit(ex); }}
                  className="block w-full text-left text-xs px-3 py-2 bg-gray-800 hover:bg-gray-700 border border-gray-700 text-gray-400 hover:text-gray-200 rounded-lg transition-colors"
                >
                  {ex}
                </button>
              ))}
            </div>
          </div>
        </div>

        {loading && (
          <div className="text-center py-12">
            <Loader2 className="w-8 h-8 text-green-400 animate-spin mx-auto mb-3" />
            <p className="text-white font-medium">Analyzing your business idea...</p>
            <p className="text-gray-400 text-sm">Running SWOT analysis and revenue projections</p>
          </div>
        )}

        {result && (
          <ResultPanel
            title="Business Validation Results"
            data={result}
            onClose={() => setResult(null)}
          />
        )}
      </div>
    </div>
  );
}
