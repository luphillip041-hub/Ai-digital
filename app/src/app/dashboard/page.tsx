import { redirect } from 'next/navigation';
import Link from 'next/link';
import { getSession } from '@/lib/auth';
import { Brain, TrendingUp, FileText, CheckCircle, BarChart3, Zap, ArrowRight, Settings, Crown } from 'lucide-react';
import Navbar from '@/components/Navbar';

const AGENTS = [
  {
    icon: TrendingUp,
    title: 'Market Research',
    description: 'Analyze any niche — market size, competition, revenue model',
    cost: 5,
    color: 'bg-indigo-600',
    href: '/tools/research',
  },
  {
    icon: Zap,
    title: 'Trend Research',
    description: 'Discover emerging opportunities before they peak',
    cost: 5,
    color: 'bg-yellow-600',
    href: '/tools/trends',
  },
  {
    icon: BarChart3,
    title: 'Competitor Analysis',
    description: 'Map competitors and find market gaps',
    cost: 4,
    color: 'bg-orange-600',
    href: '/tools/competitor',
  },
  {
    icon: CheckCircle,
    title: 'Business Validation',
    description: 'SWOT analysis + revenue projections for your idea',
    cost: 3,
    color: 'bg-green-600',
    href: '/tools/validate',
  },
  {
    icon: FileText,
    title: 'Content Generator',
    description: 'SEO blogs, landing pages, emails, social posts',
    cost: 2,
    color: 'bg-purple-600',
    href: '/tools/content',
  },
];

const QUICK_NICHES = [
  'AI SaaS tools for freelancers',
  'Pet care subscription boxes',
  'Remote work productivity apps',
  'Sustainable fashion resale',
  'Online course platforms for Gen Z',
  'Micro-SaaS for real estate agents',
];

export default async function DashboardPage() {
  const session = await getSession();
  if (!session) redirect('/login');

  const { user } = session;
  const creditPercent = Math.min(100, Math.round((user.credits / 500) * 100));

  return (
    <div className="min-h-screen bg-gray-950">
      <Navbar user={user} />

      <div className="max-w-6xl mx-auto px-4 pt-24 pb-12">
        {/* Header */}
        <div className="flex items-start justify-between mb-8">
          <div>
            <h1 className="text-3xl font-bold text-white mb-1">
              Welcome back, {user.name.split(' ')[0]} 👋
            </h1>
            <p className="text-gray-400">What profitable niche will you explore today?</p>
          </div>
          <div className="flex items-center gap-3">
            <Link
              href="/pricing"
              className="flex items-center gap-2 px-4 py-2 bg-indigo-950 border border-indigo-700 text-indigo-300 rounded-xl text-sm hover:bg-indigo-900 transition-colors"
            >
              <Crown className="w-4 h-4" />
              Upgrade
            </Link>
            <button className="p-2 text-gray-400 hover:text-white hover:bg-gray-800 rounded-xl transition-colors">
              <Settings className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Stats row */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
          <div className="p-4 bg-gray-900 border border-gray-800 rounded-xl">
            <div className="text-gray-400 text-xs mb-1">Credits Remaining</div>
            <div className="text-2xl font-bold text-white">{user.credits}</div>
            <div className="mt-2 h-1.5 bg-gray-700 rounded-full overflow-hidden">
              <div
                className="h-full bg-indigo-500 rounded-full"
                style={{ width: `${creditPercent}%` }}
              />
            </div>
          </div>
          <div className="p-4 bg-gray-900 border border-gray-800 rounded-xl">
            <div className="text-gray-400 text-xs mb-1">Current Plan</div>
            <div className="text-2xl font-bold text-white capitalize">{user.plan}</div>
            <Link href="/pricing" className="text-indigo-400 text-xs hover:underline">Upgrade →</Link>
          </div>
          <div className="p-4 bg-gray-900 border border-gray-800 rounded-xl">
            <div className="text-gray-400 text-xs mb-1">Agents Available</div>
            <div className="text-2xl font-bold text-white">5</div>
            <div className="text-gray-500 text-xs">Research, Validate, Content</div>
          </div>
          <div className="p-4 bg-gray-900 border border-gray-800 rounded-xl">
            <div className="text-gray-400 text-xs mb-1">Monthly Reset</div>
            <div className="text-2xl font-bold text-white">30d</div>
            <div className="text-gray-500 text-xs">Credits auto-renew</div>
          </div>
        </div>

        {/* Agents grid */}
        <div className="mb-10">
          <h2 className="text-xl font-bold text-white mb-4">AI Agents</h2>
          <div className="grid md:grid-cols-3 lg:grid-cols-5 gap-4">
            {AGENTS.map((agent) => (
              <Link
                key={agent.title}
                href={agent.href}
                className="p-5 bg-gray-900 border border-gray-800 rounded-xl hover:border-gray-600 transition-all group"
              >
                <div className={`w-10 h-10 ${agent.color} rounded-xl flex items-center justify-center mb-3 group-hover:scale-110 transition-transform`}>
                  <agent.icon className="w-5 h-5 text-white" />
                </div>
                <h3 className="text-white font-semibold text-sm mb-1">{agent.title}</h3>
                <p className="text-gray-500 text-xs mb-3 leading-relaxed">{agent.description}</p>
                <div className="flex items-center justify-between">
                  <span className="text-yellow-400 text-xs">⚡ {agent.cost} credits</span>
                  <ArrowRight className="w-3 h-3 text-gray-600 group-hover:text-gray-400 transition-colors" />
                </div>
              </Link>
            ))}
          </div>
        </div>

        {/* Quick ideas */}
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-bold text-white flex items-center gap-2">
              <Brain className="w-5 h-5 text-indigo-400" />
              Quick Niche Ideas to Research
            </h2>
            <span className="text-gray-500 text-xs">Click to research instantly</span>
          </div>
          <div className="flex flex-wrap gap-2">
            {QUICK_NICHES.map((niche) => (
              <Link
                key={niche}
                href={`/tools/research?q=${encodeURIComponent(niche)}`}
                className="px-3 py-1.5 bg-gray-800 hover:bg-indigo-950 hover:border-indigo-700 border border-gray-700 rounded-lg text-gray-300 hover:text-indigo-300 text-sm transition-all"
              >
                {niche}
              </Link>
            ))}
          </div>
        </div>

        {/* $500 Budget Strategy Card */}
        <div className="mt-6 p-6 bg-gradient-to-r from-indigo-950 to-purple-950 border border-indigo-800 rounded-xl">
          <h2 className="text-xl font-bold text-white mb-3">
            💡 $500 Budget Strategy — How to Start Generating Passive Revenue
          </h2>
          <div className="grid md:grid-cols-3 gap-4 text-sm">
            <div className="p-4 bg-black/20 rounded-lg">
              <div className="text-indigo-300 font-semibold mb-2">Phase 1: Research ($0)</div>
              <ul className="text-gray-300 space-y-1 text-xs">
                <li>• Run 5-10 niche research queries</li>
                <li>• Find high-score opportunities (&gt;70)</li>
                <li>• Validate top 3 ideas</li>
                <li>• Analyze competition in your niche</li>
              </ul>
            </div>
            <div className="p-4 bg-black/20 rounded-lg">
              <div className="text-purple-300 font-semibold mb-2">Phase 2: Build ($200-300)</div>
              <ul className="text-gray-300 space-y-1 text-xs">
                <li>• Domain + hosting: ~$50/yr</li>
                <li>• No-code tools (Webflow/Framer): ~$20/mo</li>
                <li>• AI API credits: ~$50/mo</li>
                <li>• Content generation for SEO</li>
              </ul>
            </div>
            <div className="p-4 bg-black/20 rounded-lg">
              <div className="text-green-300 font-semibold mb-2">Phase 3: Revenue ($200)</div>
              <ul className="text-gray-300 space-y-1 text-xs">
                <li>• Paid ads to test conversion: ~$100</li>
                <li>• Email list building tools: ~$30/mo</li>
                <li>• Target: $500/mo passive by month 4</li>
                <li>• Scale winners, cut losers</li>
              </ul>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
