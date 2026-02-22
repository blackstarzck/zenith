-- Zenith: kakao_tokens 테이블 추가 마이그레이션
-- 기존 테이블(trades, daily_stats, system_logs)이 이미 생성된 상태에서 실행하세요.
-- supabase_migration.sql을 이미 실행했다면 이 파일은 실행할 필요 없습니다.
-- Supabase SQL Editor에서 이 파일 내용을 붙여넣고 실행하면 됩니다.

-- 1. kakao_tokens 테이블 생성 (단일 행만 허용)
CREATE TABLE IF NOT EXISTS kakao_tokens (
    id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    access_token TEXT NOT NULL DEFAULT '',
    refresh_token TEXT NOT NULL DEFAULT '',
    nickname VARCHAR(100) DEFAULT '',
    profile_image TEXT DEFAULT '',
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- 2. RLS 활성화
ALTER TABLE kakao_tokens ENABLE ROW LEVEL SECURITY;

-- 3. 기존 정책 제거 후 재생성 (멱등성 보장)
DROP POLICY IF EXISTS "Service role full access" ON kakao_tokens;
CREATE POLICY "Service role full access" ON kakao_tokens
    FOR ALL USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "Anon kakao_tokens access" ON kakao_tokens;
CREATE POLICY "Anon kakao_tokens access" ON kakao_tokens
    FOR ALL TO anon USING (true) WITH CHECK (true);

-- 4. 테이블 권한 부여
GRANT SELECT, INSERT, UPDATE, DELETE ON kakao_tokens TO anon;
GRANT SELECT, INSERT, UPDATE, DELETE ON kakao_tokens TO authenticated;
