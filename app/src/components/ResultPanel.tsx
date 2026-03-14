'use client';

import { X, Download, Copy, CheckCircle } from 'lucide-react';
import { useState } from 'react';

interface ResultPanelProps {
  title: string;
  data: Record<string, unknown>;
  onClose: () => void;
}

function ScoreBar({ score }: { score: number }) {
  const color = score >= 75 ? 'bg-green-500' : score >= 50 ? 'bg-yellow-500' : 'bg-red-500';
  return (
    <div className="flex items-center gap-3">
      <div className="flex-1 h-2 bg-gray-700 rounded-full overflow-hidden">
        <div className={`h-full ${color} rounded-full transition-all`} style={{ width: `${score}%` }} />
      </div>
      <span className="text-white font-bold text-sm w-10">{score}/100</span>
    </div>
  );
}

function renderValue(value: unknown, depth = 0): React.ReactNode {
  if (value === null || value === undefined) return <span className="text-gray-500">—</span>;
  if (typeof value === 'boolean') return <span className={value ? 'text-green-400' : 'text-red-400'}>{String(value)}</span>;
  if (typeof value === 'number') return <span className="text-indigo-400 font-semibold">{value}</span>;
  if (typeof value === 'string') return <span className="text-gray-300">{value}</span>;
  if (Array.isArray(value)) {
    return (
      <ul className={`mt-1 space-y-1 ${depth > 0 ? 'ml-4' : ''}`}>
        {value.map((item, i) => (
          <li key={i} className="flex items-start gap-2 text-sm">
            <span className="text-indigo-400 mt-0.5">•</span>
            <span className="text-gray-300">{String(item)}</span>
          </li>
        ))}
      </ul>
    );
  }
  if (typeof value === 'object') {
    return (
      <div className={`mt-1 space-y-2 ${depth > 0 ? 'ml-4 border-l border-gray-700 pl-4' : ''}`}>
        {Object.entries(value as Record<string, unknown>).map(([k, v]) => (
          <div key={k}>
            <span className="text-gray-500 text-xs uppercase tracking-wide">{k.replace(/_/g, ' ')}</span>
            <div className="mt-0.5">{renderValue(v, depth + 1)}</div>
          </div>
        ))}
      </div>
    );
  }
  return <span className="text-gray-300">{String(value)}</span>;
}

export default function ResultPanel({ title, data, onClose }: ResultPanelProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(JSON.stringify(data, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownload = () => {
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${title.replace(/\s+/g, '-').toLowerCase()}-${Date.now()}.json`;
    a.click();
  };

  const score = data.score as number || data.validationScore as number || data.trendScore as number;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
      <div className="w-full max-w-2xl max-h-[85vh] bg-gray-950 border border-gray-700 rounded-2xl flex flex-col">
        <div className="flex items-center justify-between p-6 border-b border-gray-800">
          <h2 className="text-white font-bold text-lg">{title}</h2>
          <div className="flex items-center gap-2">
            <button
              onClick={handleCopy}
              className="p-2 text-gray-400 hover:text-white hover:bg-gray-800 rounded-lg transition-colors"
            >
              {copied ? <CheckCircle className="w-4 h-4 text-green-400" /> : <Copy className="w-4 h-4" />}
            </button>
            <button
              onClick={handleDownload}
              className="p-2 text-gray-400 hover:text-white hover:bg-gray-800 rounded-lg transition-colors"
            >
              <Download className="w-4 h-4" />
            </button>
            <button
              onClick={onClose}
              className="p-2 text-gray-400 hover:text-white hover:bg-gray-800 rounded-lg transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-6 space-y-4">
          {score !== undefined && (
            <div className="p-4 bg-gray-900 rounded-xl">
              <p className="text-gray-400 text-xs uppercase tracking-wide mb-2">Opportunity Score</p>
              <ScoreBar score={score} />
            </div>
          )}

          <div className="space-y-4">
            {Object.entries(data).map(([key, value]) => {
              if (['id', 'createdAt', 'score', 'validationScore', 'trendScore'].includes(key)) return null;
              return (
                <div key={key} className="p-4 bg-gray-900 rounded-xl">
                  <p className="text-gray-500 text-xs uppercase tracking-wide mb-2">
                    {key.replace(/([A-Z])/g, ' $1').replace(/_/g, ' ').trim()}
                  </p>
                  {renderValue(value)}
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
