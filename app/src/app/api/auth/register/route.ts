import { NextRequest, NextResponse } from 'next/server';
import { DEMO_USERS, createSessionToken } from '@/lib/auth';

export async function POST(request: NextRequest) {
  const { email, name, password } = await request.json();

  if (DEMO_USERS[email]) {
    return NextResponse.json({ error: 'Email already registered' }, { status: 400 });
  }

  // In production, persist to database
  const newUser = {
    id: `user_${Date.now()}`,
    email,
    name,
    password,
    plan: 'free',
    credits: 5,
  };
  DEMO_USERS[email] = newUser;

  const token = createSessionToken({
    id: newUser.id,
    email: newUser.email,
    name: newUser.name,
    plan: newUser.plan,
    credits: newUser.credits,
  });

  const response = NextResponse.json({
    success: true,
    user: { id: newUser.id, email: newUser.email, name: newUser.name, plan: newUser.plan, credits: newUser.credits },
  });

  response.cookies.set('session', token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    sameSite: 'lax',
    maxAge: 60 * 60 * 24 * 7,
  });

  return response;
}
