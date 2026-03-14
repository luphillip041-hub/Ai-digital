import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'NixorAI — AI-Powered Market Research & Revenue Generation',
  description: 'Use AI agents to research profitable niches, generate content, validate business ideas, and build passive income streams. Start free today.',
  keywords: 'AI market research, passive income, niche finder, content generation, business validation',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="bg-gray-950 text-white antialiased">
        {children}
      </body>
    </html>
  );
}
