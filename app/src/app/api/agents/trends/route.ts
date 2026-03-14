import { NextRequest, NextResponse } from 'next/server';
import { runTrendResearchAgent } from '@/lib/claude';
import { getSession } from '@/lib/auth';
import { CREDIT_COSTS } from '@/lib/plans';

export async function POST(request: NextRequest) {
  const session = await getSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const { industry } = await request.json();
  if (!industry?.trim()) {
    return NextResponse.json({ error: 'Industry is required' }, { status: 400 });
  }

  const cost = CREDIT_COSTS.market_research;
  if (session.user.credits < cost) {
    return NextResponse.json(
      { error: `Insufficient credits. This action costs ${cost} credits.` },
      { status: 402 }
    );
  }

  try {
    const raw = await runTrendResearchAgent(industry);
    const jsonMatch = raw.match(/\{[\s\S]*\}/);
    const data = jsonMatch ? JSON.parse(jsonMatch[0]) : JSON.parse(raw);

    return NextResponse.json({
      success: true,
      data: {
        ...data,
        id: `trends_${Date.now()}`,
        createdAt: new Date().toISOString(),
      },
      creditsUsed: cost,
      creditsRemaining: session.user.credits - cost,
    });
  } catch (error) {
    console.error('Trends agent error:', error);
    return NextResponse.json({ error: 'Agent failed to process request' }, { status: 500 });
  }
}
