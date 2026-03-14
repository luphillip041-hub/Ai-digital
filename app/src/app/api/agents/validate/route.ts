import { NextRequest, NextResponse } from 'next/server';
import { runBusinessValidationAgent } from '@/lib/claude';
import { getSession } from '@/lib/auth';
import { CREDIT_COSTS } from '@/lib/plans';

export async function POST(request: NextRequest) {
  const session = await getSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const { idea } = await request.json();
  if (!idea?.trim()) {
    return NextResponse.json({ error: 'Business idea is required' }, { status: 400 });
  }

  const cost = CREDIT_COSTS.business_validation;
  if (session.user.credits < cost) {
    return NextResponse.json(
      { error: `Insufficient credits. This action costs ${cost} credits.` },
      { status: 402 }
    );
  }

  try {
    const raw = await runBusinessValidationAgent(idea);
    const jsonMatch = raw.match(/\{[\s\S]*\}/);
    const data = jsonMatch ? JSON.parse(jsonMatch[0]) : JSON.parse(raw);

    return NextResponse.json({
      success: true,
      data: {
        ...data,
        id: `validate_${Date.now()}`,
        createdAt: new Date().toISOString(),
      },
      creditsUsed: cost,
      creditsRemaining: session.user.credits - cost,
    });
  } catch (error) {
    console.error('Validation agent error:', error);
    return NextResponse.json({ error: 'Agent failed to process request' }, { status: 500 });
  }
}
