-- Zenith 서비스 상태 컬럼 추가 마이그레이션
-- Supabase SQL Editor에서 실행하세요.

-- bot_state 테이블에 서비스 상태 컬럼 추가
ALTER TABLE bot_state
    ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT false,
    ADD COLUMN IF NOT EXISTS upbit_status TEXT DEFAULT 'unknown',
    ADD COLUMN IF NOT EXISTS kakao_status TEXT DEFAULT 'unknown';

-- is_active: 봇이 실제로 실행 중인지 (true=실행, false=중지/크래시)
-- upbit_status: 'connected' | 'auth_failed' | 'rate_limited' | 'error' | 'unknown'
-- kakao_status: 'connected' | 'token_expired' | 'send_failed' | 'no_token' | 'unknown'

COMMENT ON COLUMN bot_state.is_active IS '봇 실행 상태 (true=실행 중, false=중지)';
COMMENT ON COLUMN bot_state.upbit_status IS '업비트 API 상태 (connected/auth_failed/rate_limited/error/unknown)';
COMMENT ON COLUMN bot_state.kakao_status IS '카카오 API 상태 (connected/token_expired/send_failed/no_token/unknown)';
