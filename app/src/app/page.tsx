import Link from 'next/link';
import { Brain, TrendingUp, FileText, CheckCircle, Zap, Shield, BarChart3, ArrowRight, Star } from 'lucide-react';
import Navbar from '@/components/Navbar';
import { getSession } from '@/lib/auth';
import { PLANS } from '@/lib/plans';

const FEATURES = [
  {
    icon: TrendingUp,
    title: 'Market Research Agent',
    description: 'AI analyzes any niche in seconds — market size, competition level, revenue potential, and exact action plans.',
    color: 'bg-indigo-600',
  },
  {
    icon: FileText,
    title: 'Content Generation Agent',
    description: 'Generate SEO-optimized blog posts, landing pages, email sequences, and social content at scale.',
    color: 'bg-purple-600',
  },
  {
    icon: CheckCircle,
    title: 'Business Validation Agent',
    description: 'Get honest AI feedback on your business idea with SWOT analysis, revenue projections, and MVP roadmap.',
    color: 'bg-green-600',
  },
  {
    icon: BarChart3,
    title: 'Competitor Intelligence Agent',
    description: 'Map out your entire competitive landscape, find market gaps, and build winning differentiation strategies.',
    color: 'bg-orange-600',
  },
  {
    icon: Zap,
    title: 'Trend Research Agent',
    description: 'Spot emerging opportunities before the crowd. Get hot keywords, investment areas, and timing insights.',
    color: 'bg-yellow-600',
  },
  {
    icon: Shield,
    title: 'Multi-Agent Deep Research',
    description: 'Chain multiple AI agents together for comprehensive research reports — the same quality as an agency.',
    color: 'bg-blue-600',
  },
];

const TESTIMONIALS = [
  {
    name: 'Sarah Chen',
    role: 'Solo Founder',
    text: 'Found my profitable niche in 10 minutes. NixorAI\'s research agent saved me months of manual work. Now making $3,200/month.',
    rating: 5,
  },
  {
    name: 'Marcus Williams',
    role: 'Digital Entrepreneur',
    text: 'The business validation agent told me my first idea was flawed and suggested a pivot. Best advice I ever got — doubled my revenue.',
    rating: 5,
  },
  {
    name: 'Priya Patel',
    role: 'Content Agency Owner',
    text: 'We use NixorAI for all our client research. Saved 15 hours per week and improved our deliverable quality dramatically.',
    rating: 5,
  },
];

const STATS = [
  { value: '12,400+', label: 'Niches Analyzed' },
  { value: '$2.1M+', label: 'Revenue Generated' },
  { value: '3,200+', label: 'Active Users' },
  { value: '94%', label: 'Satisfaction Rate' },
];

export default async function HomePage() {
  const session = await getSession();

  return (
    <div className="min-h-screen bg-gray-950">
      <Navbar user={session?.user} />

      {/* Hero */}
      <section className="hero-gradient pt-32 pb-20 px-4">
        <div className="max-w-5xl mx-auto text-center">
          <div className="inline-flex items-center gap-2 px-4 py-2 bg-indigo-950 border border-indigo-800 rounded-full text-indigo-300 text-sm mb-8">
            <Zap className="w-4 h-4" />
            <span>AI-powered passive income research — $500 budget strategy inside</span>
          </div>

          <h1 className="text-5xl md:text-7xl font-extrabold text-white mb-6 leading-tight">
            Find Profitable Niches<br />
            <span className="gradient-text">With AI Agents</span>
          </h1>

          <p className="text-xl text-gray-400 max-w-2xl mx-auto mb-10">
            Our AI agents research markets, validate ideas, generate content, and map competitors
            — so you can build passive income streams faster than ever.
          </p>

          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <Link
              href="/register"
              className="px-8 py-4 bg-indigo-600 hover:bg-indigo-500 text-white font-semibold rounded-xl text-lg transition-all flex items-center justify-center gap-2 shadow-lg shadow-indigo-500/25"
            >
              Start Free — 5 Credits Included
              <ArrowRight className="w-5 h-5" />
            </Link>
            <Link
              href="/demo"
              className="px-8 py-4 bg-gray-800 hover:bg-gray-700 text-white font-semibold rounded-xl text-lg transition-all"
            >
              Try Demo (No Login)
            </Link>
          </div>

          <p className="text-gray-500 text-sm mt-4">No credit card required • Free tier forever • Cancel anytime</p>
        </div>
      </section>

      {/* Stats */}
      <section className="py-12 border-y border-gray-800">
        <div className="max-w-5xl mx-auto px-4 grid grid-cols-2 md:grid-cols-4 gap-8">
          {STATS.map((stat) => (
            <div key={stat.label} className="text-center">
              <div className="text-3xl font-extrabold text-white mb-1">{stat.value}</div>
              <div className="text-gray-400 text-sm">{stat.label}</div>
            </div>
          ))}
        </div>
      </section>

      {/* How It Works */}
      <section id="how-it-works" className="py-20 px-4">
        <div className="max-w-5xl mx-auto">
          <div className="text-center mb-16">
            <h2 className="text-4xl font-bold text-white mb-4">From $500 Budget to Passive Revenue</h2>
            <p className="text-gray-400 text-lg">Our proven framework, powered by AI agents</p>
          </div>

          <div className="grid md:grid-cols-4 gap-6">
            {[
              { step: '01', title: 'Research Niches', desc: 'Run the Market Research Agent to find high-potential niches with low competition' },
              { step: '02', title: 'Validate Ideas', desc: 'Business Validation Agent scores your idea and gives honest SWOT analysis' },
              { step: '03', title: 'Analyze Competitors', desc: 'Map the competitive landscape and find market gaps to exploit' },
              { step: '04', title: 'Generate Content', desc: 'AI creates SEO content to drive organic traffic and conversions' },
            ].map((item) => (
              <div key={item.step} className="relative p-6 bg-gray-900 rounded-xl border border-gray-800">
                <div className="text-indigo-400 font-bold text-4xl mb-4 opacity-30">{item.step}</div>
                <h3 className="text-white font-semibold mb-2">{item.title}</h3>
                <p className="text-gray-400 text-sm">{item.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Features */}
      <section id="features" className="py-20 px-4 bg-gray-900/50">
        <div className="max-w-5xl mx-auto">
          <div className="text-center mb-16">
            <h2 className="text-4xl font-bold text-white mb-4">5 AI Agents, Infinite Opportunities</h2>
            <p className="text-gray-400 text-lg">Each agent specializes in a critical part of your business intelligence workflow</p>
          </div>

          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
            {FEATURES.map((feature) => (
              <div key={feature.title} className="p-6 bg-gray-900 rounded-xl border border-gray-800 hover:border-gray-600 transition-colors">
                <div className={`w-12 h-12 ${feature.color} rounded-xl flex items-center justify-center mb-4`}>
                  <feature.icon className="w-6 h-6 text-white" />
                </div>
                <h3 className="text-white font-semibold mb-2">{feature.title}</h3>
                <p className="text-gray-400 text-sm">{feature.description}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Pricing Preview */}
      <section className="py-20 px-4">
        <div className="max-w-5xl mx-auto text-center">
          <h2 className="text-4xl font-bold text-white mb-4">Simple, Transparent Pricing</h2>
          <p className="text-gray-400 text-lg mb-8">Start free, scale as you grow</p>

          <div className="grid md:grid-cols-4 gap-6 mb-8">
            {PLANS.map((plan) => (
              <div
                key={plan.id}
                className={`p-6 rounded-xl border text-left ${
                  plan.popular
                    ? 'bg-indigo-950 border-indigo-500'
                    : 'bg-gray-900 border-gray-800'
                }`}
              >
                <div className="text-white font-bold mb-1">{plan.name}</div>
                <div className="text-3xl font-extrabold text-white mb-1">
                  ${plan.price}
                  {plan.price > 0 && <span className="text-sm font-normal text-gray-400">/mo</span>}
                </div>
                <div className="text-yellow-400 text-sm mb-4">{plan.credits} credits</div>
                <Link
                  href={plan.price === 0 ? '/register' : '/pricing'}
                  className={`block text-center py-2 rounded-lg text-sm font-medium transition-colors ${
                    plan.popular
                      ? 'bg-indigo-600 hover:bg-indigo-500 text-white'
                      : 'bg-gray-800 hover:bg-gray-700 text-white'
                  }`}
                >
                  {plan.price === 0 ? 'Start Free' : 'Get Started'}
                </Link>
              </div>
            ))}
          </div>

          <Link href="/pricing" className="text-indigo-400 hover:text-indigo-300 text-sm">
            View full pricing & feature comparison →
          </Link>
        </div>
      </section>

      {/* Testimonials */}
      <section className="py-20 px-4 bg-gray-900/50">
        <div className="max-w-5xl mx-auto">
          <div className="text-center mb-16">
            <h2 className="text-4xl font-bold text-white mb-4">Built by Founders, For Founders</h2>
          </div>

          <div className="grid md:grid-cols-3 gap-6">
            {TESTIMONIALS.map((testimonial) => (
              <div key={testimonial.name} className="p-6 bg-gray-900 rounded-xl border border-gray-800">
                <div className="flex gap-1 mb-4">
                  {Array.from({ length: testimonial.rating }).map((_, i) => (
                    <Star key={i} className="w-4 h-4 text-yellow-400 fill-yellow-400" />
                  ))}
                </div>
                <p className="text-gray-300 text-sm mb-4 leading-relaxed">&ldquo;{testimonial.text}&rdquo;</p>
                <div>
                  <div className="text-white font-semibold text-sm">{testimonial.name}</div>
                  <div className="text-gray-500 text-xs">{testimonial.role}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="py-20 px-4">
        <div className="max-w-3xl mx-auto text-center">
          <div className="p-12 bg-indigo-950 border border-indigo-800 rounded-2xl">
            <h2 className="text-4xl font-bold text-white mb-4">Start Building Today</h2>
            <p className="text-indigo-300 mb-8">
              Join 3,200+ entrepreneurs using AI to find profitable niches and build passive income.
              Your first 5 credits are free.
            </p>
            <Link
              href="/register"
              className="inline-flex items-center gap-2 px-8 py-4 bg-indigo-600 hover:bg-indigo-500 text-white font-bold rounded-xl text-lg transition-all"
            >
              <Brain className="w-5 h-5" />
              Create Free Account
            </Link>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="py-12 px-4 border-t border-gray-800">
        <div className="max-w-5xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 bg-indigo-600 rounded-md flex items-center justify-center">
              <Brain className="w-4 h-4 text-white" />
            </div>
            <span className="text-white font-bold">NixorAI</span>
          </div>
          <div className="flex gap-6 text-gray-500 text-sm">
            <Link href="/pricing" className="hover:text-gray-300">Pricing</Link>
            <Link href="/dashboard" className="hover:text-gray-300">Dashboard</Link>
            <span>© 2025 NixorAI</span>
          </div>
        </div>
      </footer>
    </div>
  );
}
