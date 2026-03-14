'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Brain, Menu, X, Zap } from 'lucide-react';

interface NavbarProps {
  user?: { name: string; plan: string; credits: number } | null;
}

export default function Navbar({ user }: NavbarProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const router = useRouter();

  const handleLogout = async () => {
    await fetch('/api/auth/logout', { method: 'POST' });
    router.push('/');
    router.refresh();
  };

  return (
    <nav className="fixed top-0 w-full z-50 bg-gray-950/90 backdrop-blur-md border-b border-gray-800">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          <Link href="/" className="flex items-center gap-2">
            <div className="w-8 h-8 bg-indigo-600 rounded-lg flex items-center justify-center">
              <Brain className="w-5 h-5 text-white" />
            </div>
            <span className="text-xl font-bold text-white">NixorAI</span>
          </Link>

          <div className="hidden md:flex items-center gap-8">
            <Link href="/#features" className="text-gray-400 hover:text-white text-sm transition-colors">Features</Link>
            <Link href="/pricing" className="text-gray-400 hover:text-white text-sm transition-colors">Pricing</Link>
            <Link href="/#how-it-works" className="text-gray-400 hover:text-white text-sm transition-colors">How It Works</Link>
          </div>

          <div className="hidden md:flex items-center gap-3">
            {user ? (
              <>
                <div className="flex items-center gap-2 text-sm text-gray-400">
                  <Zap className="w-4 h-4 text-yellow-400" />
                  <span>{user.credits} credits</span>
                </div>
                <Link
                  href="/dashboard"
                  className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white text-sm rounded-lg transition-colors"
                >
                  Dashboard
                </Link>
                <button
                  onClick={handleLogout}
                  className="px-4 py-2 text-gray-400 hover:text-white text-sm transition-colors"
                >
                  Logout
                </button>
              </>
            ) : (
              <>
                <Link href="/login" className="px-4 py-2 text-gray-400 hover:text-white text-sm transition-colors">
                  Login
                </Link>
                <Link
                  href="/register"
                  className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white text-sm rounded-lg transition-colors"
                >
                  Start Free
                </Link>
              </>
            )}
          </div>

          <button
            className="md:hidden text-gray-400"
            onClick={() => setMenuOpen(!menuOpen)}
          >
            {menuOpen ? <X /> : <Menu />}
          </button>
        </div>
      </div>

      {menuOpen && (
        <div className="md:hidden bg-gray-950 border-t border-gray-800 px-4 py-4 space-y-3">
          <Link href="/#features" className="block text-gray-400 hover:text-white text-sm py-2">Features</Link>
          <Link href="/pricing" className="block text-gray-400 hover:text-white text-sm py-2">Pricing</Link>
          {user ? (
            <>
              <Link href="/dashboard" className="block text-indigo-400 text-sm py-2">Dashboard</Link>
              <button onClick={handleLogout} className="block text-gray-400 text-sm py-2">Logout</button>
            </>
          ) : (
            <>
              <Link href="/login" className="block text-gray-400 text-sm py-2">Login</Link>
              <Link href="/register" className="block text-indigo-400 text-sm py-2">Start Free</Link>
            </>
          )}
        </div>
      )}
    </nav>
  );
}
