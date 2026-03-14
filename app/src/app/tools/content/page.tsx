'use client';

import { useState } from 'react';
import Link from 'next/link';
import { FileText, ArrowLeft, Loader2, AlertCircle, X } from 'lucide-react';

const CONTENT_TYPES = [
  { id: 'blog', label: 'Blog Post', desc: '800-1200 word SEO article' },
  { id: 'landing', label: 'Landing Page', desc: 'Hero, benefits, CTA' },
  { id: 'email', label: 'Email Sequence', desc: '3-email nurture series' },
  { id: 'social', label: 'Social Posts', desc: '5 platform-ready posts' },
  { id: 'ad', label: 'Ad Copy', desc: '3 Google/Meta ad variations' },
];

export default function ContentPage() {
  const [topic, setTopic] = useState('');
  const [type, setType] = useState('blog');
  const [keywords, setKeywords] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!topic.trim()) return;
    setError('');
    setLoading(true);
    setResult(null);

    const kws = keywords.split(',').map(k => k.trim()).filter(Boolean);

    const res = await fetch('/api/agents/content', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ topic, type, keywords: kws }),
    });

    const data = await res.json();
    setLoading(false);

    if (!res.ok) {
      if (res.status === 401) { window.location.href = '/login'; return; }
      setError(data.error || 'Generation failed');
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
          <div className="w-10 h-10 bg-purple-600 rounded-xl flex items-center justify-center flex-shrink-0">
            <FileText className="w-5 h-5 text-white" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-white">Content Generation Agent</h1>
            <p className="text-gray-400">Generate SEO-optimized content that drives organic traffic and converts visitors.</p>
          </div>
        </div>

        <div className="bg-gray-900 border border-gray-800 rounded-2xl p-6">
          <form onSubmit={handleSubmit} className="space-y-6">
            {/* Content type */}
            <div>
              <label className="block text-sm font-medium text-gray-400 mb-3">Content Type</label>
              <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
                {CONTENT_TYPES.map((ct) => (
                  <button
                    key={ct.id}
                    type="button"
                    onClick={() => setType(ct.id)}
                    className={`p-3 rounded-xl border text-left transition-all ${
                      type === ct.id
                        ? 'bg-purple-950 border-purple-500 text-purple-300'
                        : 'bg-gray-800 border-gray-700 text-gray-400 hover:border-gray-600'
                    }`}
                  >
                    <div className="font-semibold text-sm">{ct.label}</div>
                    <div className="text-xs mt-0.5 opacity-70">{ct.desc}</div>
                  </button>
                ))}
              </div>
            </div>

            {/* Topic */}
            <div>
              <label className="block text-sm font-medium text-gray-400 mb-2">Topic / Subject</label>
              <input
                type="text"
                value={topic}
                onChange={e => setTopic(e.target.value)}
                placeholder="e.g. How to start a profitable AI micro-SaaS in 2025"
                className="w-full px-4 py-3 bg-gray-800 border border-gray-700 rounded-xl text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
                required
              />
            </div>

            {/* Keywords */}
            <div>
              <label className="block text-sm font-medium text-gray-400 mb-2">
                Target Keywords <span className="text-gray-600">(comma-separated)</span>
              </label>
              <input
                type="text"
                value={keywords}
                onChange={e => setKeywords(e.target.value)}
                placeholder="e.g. micro-saas, passive income, AI tools"
                className="w-full px-4 py-3 bg-gray-800 border border-gray-700 rounded-xl text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
              />
            </div>

            {error && (
              <div className="flex items-center gap-2 p-3 bg-red-950 border border-red-800 rounded-lg text-red-400 text-sm">
                <AlertCircle className="w-4 h-4" />
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading || !topic.trim()}
              className="w-full py-3.5 bg-purple-600 hover:bg-purple-500 text-white font-semibold rounded-xl transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
            >
              {loading ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Generating Content...
                </>
              ) : (
                <>
                  <FileText className="w-4 h-4" />
                  Generate Content (2 ⚡)
                </>
              )}
            </button>
          </form>
        </div>

        {/* Result */}
        {result && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
            <div className="w-full max-w-3xl max-h-[85vh] bg-gray-950 border border-gray-700 rounded-2xl flex flex-col">
              <div className="flex items-center justify-between p-6 border-b border-gray-800">
                <div>
                  <h2 className="text-white font-bold">{result.title as string}</h2>
                  <div className="flex gap-4 mt-1 text-xs text-gray-500">
                    <span>{result.wordCount as number} words</span>
                    <span>{result.readingTime as string}</span>
                    <span>SEO Score: {result.seoScore as number}/100</span>
                  </div>
                </div>
                <button onClick={() => setResult(null)} className="p-2 text-gray-400 hover:text-white hover:bg-gray-800 rounded-lg">
                  <X className="w-5 h-5" />
                </button>
              </div>
              <div className="flex-1 overflow-y-auto p-6">
                <div className="prose prose-invert prose-sm max-w-none">
                  <div className="p-4 bg-gray-900 rounded-xl mb-4">
                    <p className="text-gray-400 text-xs uppercase tracking-wide mb-1">Meta Description</p>
                    <p className="text-gray-200 text-sm">{result.metaDescription as string}</p>
                  </div>
                  <div className="p-4 bg-gray-900 rounded-xl mb-4">
                    <p className="text-gray-400 text-xs uppercase tracking-wide mb-2">CTA</p>
                    <p className="text-indigo-300 font-medium">{result.cta as string}</p>
                  </div>
                  <div className="p-4 bg-gray-900 rounded-xl">
                    <p className="text-gray-400 text-xs uppercase tracking-wide mb-2">Content</p>
                    <div className="text-gray-200 text-sm leading-relaxed whitespace-pre-wrap">
                      {result.content as string}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
