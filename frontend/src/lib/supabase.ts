import { createClient } from '@supabase/supabase-js';

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL as string;
const supabaseKey = import.meta.env.VITE_SUPABASE_ANON_KEY as string;

// Supabase Auth를 사용하지 않음 (Kakao OAuth 직접 구현)
// GoTrueClient 중복 인스턴스 경고 및 navigator.locks 타임아웃 방지
const noopStorage = {
  getItem: () => null,
  setItem: () => {},
  removeItem: () => {},
};

export const supabase = createClient(supabaseUrl, supabaseKey, {
  auth: {
    persistSession: false,
    autoRefreshToken: false,
    detectSessionInUrl: false,
    storage: noopStorage,
    lock: async <R>(_name: string, _acquireTimeout: number, fn: () => Promise<R>) => fn(),
  },
});
