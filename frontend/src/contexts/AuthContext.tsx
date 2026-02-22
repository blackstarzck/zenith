import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  type ReactNode,
} from 'react';
import { supabase } from '../lib/supabase';

/* ── Types ──────────────────────────────────────────────── */

export interface KakaoUser {
  nickname: string;
  profileImage: string;
}

interface AuthContextValue {
  user: KakaoUser | null;
  loading: boolean;
  login: () => void;
  logout: () => void;
}

const STORAGE_KEY = 'zenith_auth';
const SESSION_DAYS = 7;

/* ── Context ────────────────────────────────────────────── */

const AuthContext = createContext<AuthContextValue>({
  user: null,
  loading: true,
  login: () => {},
  logout: () => {},
});

export function useAuth() {
  return useContext(AuthContext);
}

/* ── Kakao OAuth helpers ────────────────────────────────── */

const KAKAO_CLIENT_ID = import.meta.env.VITE_KAKAO_REST_API_KEY as string;
const KAKAO_CLIENT_SECRET = import.meta.env.VITE_KAKAO_CLIENT_SECRET as string;
const KAKAO_REDIRECT_URI = import.meta.env.VITE_KAKAO_REDIRECT_URI as string;

function buildKakaoAuthUrl(): string {
  const params = new URLSearchParams({
    client_id: KAKAO_CLIENT_ID,
    redirect_uri: KAKAO_REDIRECT_URI,
    response_type: 'code',
    scope: 'talk_message',
  });
  return `https://kauth.kakao.com/oauth/authorize?${params.toString()}`;
}

/* ── 토큰 교환 (Vite proxy 경유) ─────────────────────────── */

export async function exchangeCodeForTokens(code: string) {
  const body = new URLSearchParams({
    grant_type: 'authorization_code',
    client_id: KAKAO_CLIENT_ID,
    client_secret: KAKAO_CLIENT_SECRET,
    redirect_uri: KAKAO_REDIRECT_URI,
    code,
  });

  const resp = await fetch('/kakao-token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: body.toString(),
  });

  if (!resp.ok) {
    const err = await resp.text();
    throw new Error(`Token exchange failed: ${resp.status} ${err}`);
  }

  return resp.json() as Promise<{
    access_token: string;
    refresh_token: string;
    expires_in: number;
    refresh_token_expires_in: number;
  }>;
}

export async function fetchKakaoUserInfo(accessToken: string): Promise<KakaoUser> {
  const resp = await fetch('/kakao-api/v2/user/me', {
    headers: { Authorization: `Bearer ${accessToken}` },
  });

  if (!resp.ok) {
    throw new Error(`User info fetch failed: ${resp.status}`);
  }

  const data = await resp.json();
  const profile = data.kakao_account?.profile ?? {};

  return {
    nickname: profile.nickname ?? '',
    profileImage: profile.profile_image_url ?? '',
  };
}

export async function saveTokensToSupabase(
  accessToken: string,
  refreshToken: string,
  user: KakaoUser,
) {
  const row = {
    id: 1,
    access_token: accessToken,
    refresh_token: refreshToken,
    nickname: user.nickname,
    profile_image: user.profileImage,
    updated_at: new Date().toISOString(),
  };

  const { error } = await supabase
    .from('kakao_tokens')
    .upsert(row, { onConflict: 'id' });

  if (error) {
    throw new Error(`Supabase save failed: ${error.message}`);
  }
}

/* ── localStorage session ───────────────────────────────── */

interface StoredSession {
  user: KakaoUser;
  expiresAt: number; // epoch ms
}

function loadSession(): KakaoUser | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;

    const session: StoredSession = JSON.parse(raw);
    if (Date.now() > session.expiresAt) {
      localStorage.removeItem(STORAGE_KEY);
      return null;
    }
    return session.user;
  } catch {
    localStorage.removeItem(STORAGE_KEY);
    return null;
  }
}

function saveSession(user: KakaoUser) {
  const session: StoredSession = {
    user,
    expiresAt: Date.now() + SESSION_DAYS * 24 * 60 * 60 * 1000,
  };
  localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
}

function clearSession() {
  localStorage.removeItem(STORAGE_KEY);
}

/* ── Provider ───────────────────────────────────────────── */

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<KakaoUser | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const stored = loadSession();
    setUser(stored);
    setLoading(false);
  }, []);

  const login = useCallback(() => {
    window.location.href = buildKakaoAuthUrl();
  }, []);

  const logout = useCallback(() => {
    clearSession();
    setUser(null);
  }, []);

  const setAuthUser = useCallback((u: KakaoUser) => {
    saveSession(u);
    setUser(u);
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, login, logout }}>
      <AuthSetterContext.Provider value={setAuthUser}>
        {children}
      </AuthSetterContext.Provider>
    </AuthContext.Provider>
  );
}

/* ── Internal setter context (for callback page) ────────── */

const AuthSetterContext = createContext<(u: KakaoUser) => void>(() => {});
export function useAuthSetter() {
  return useContext(AuthSetterContext);
}
