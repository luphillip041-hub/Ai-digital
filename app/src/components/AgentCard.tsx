'use client';

import { ReactNode } from 'react';
import { LucideIcon } from 'lucide-react';

interface AgentCardProps {
  icon: LucideIcon;
  title: string;
  description: string;
  cost: number;
  color: string;
  onClick: () => void;
  loading?: boolean;
}

export default function AgentCard({
  icon: Icon,
  title,
  description,
  cost,
  color,
  onClick,
  loading,
}: AgentCardProps) {
  return (
    <button
      onClick={onClick}
      disabled={loading}
      className="w-full text-left p-6 bg-gray-900 border border-gray-800 rounded-xl hover:border-gray-600 transition-all group disabled:opacity-50 disabled:cursor-not-allowed"
    >
      <div className={`w-12 h-12 ${color} rounded-xl flex items-center justify-center mb-4 group-hover:scale-110 transition-transform`}>
        <Icon className="w-6 h-6 text-white" />
      </div>
      <h3 className="text-white font-semibold mb-1">{title}</h3>
      <p className="text-gray-400 text-sm mb-3">{description}</p>
      <div className="flex items-center gap-1 text-yellow-400 text-xs font-medium">
        <span>⚡</span>
        <span>{cost} credits</span>
      </div>
    </button>
  );
}
