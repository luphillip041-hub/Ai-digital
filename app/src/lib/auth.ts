import { cookies } from 'next/headers';

export interface Session {
  user: {
    id: string;
    email: string;
    name: string;
    plan: string;
    credits: number;
  };
}

// Simple in-memory user store for demo (replace with DB in production)
export const DEMO_USERS: Record<string, {
  id: string;
  email: string;
  name: string;
  password: string;
  plan: string;
  credits: number;
  stripeCustomerId?: string;
}> = {
  'demo@nixor.ai': {
    id: 'user_demo',
    email: 'demo@nixor.ai',
    name: 'Demo User',
    password: 'demo123',
    plan: 'pro',
    credits: 450,
  },
};

export async function getSession(): Promise<Session | null> {
  try {
    const cookieStore = await cookies();
    const sessionCookie = cookieStore.get('session');
    if (!sessionCookie) return null;

    const sessionData = JSON.parse(
      Buffer.from(sessionCookie.value, 'base64').toString()
    );
    return sessionData;
  } catch {
    return null;
  }
}

export function createSessionToken(user: {
  id: string;
  email: string;
  name: string;
  plan: string;
  credits: number;
}): string {
  return Buffer.from(JSON.stringify({ user })).toString('base64');
}
