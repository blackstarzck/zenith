-- Zenith 봇 상태 테이블 추가 마이그레이션
-- Supabase SQL Editor에서 실행하세요.

-- 1. bot_state: 봇 실시간 상태 (단일 행 패턴)
CREATE TABLE IF NOT EXISTS bot_state (
    id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    initial_balance DECIMAL(20, 4) DEFAULT 0,
    current_balance DECIMAL(20, 4) DEFAULT 0,
    top_symbols JSONB DEFAULT '[]'::jsonb,
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- RLS 활성화
ALTER TABLE bot_state ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Service role full access" ON bot_state;
CREATE POLICY "Service role full access" ON bot_state
    FOR ALL USING (true) WITH CHECK (true);

-- 프론트엔드 anon 키로 조회 허용
GRANT SELECT, INSERT, UPDATE, DELETE ON bot_state TO anon;
GRANT SELECT, INSERT, UPDATE, DELETE ON bot_state TO authenticated;

-- Realtime 활성화
ALTER PUBLICATION supabase_realtime ADD TABLE bot_state;

-- 2. system_logs level 제약에 CRITICAL 추가
ALTER TABLE system_logs DROP CONSTRAINT IF EXISTS system_logs_level_check;
ALTER TABLE system_logs ADD CONSTRAINT system_logs_level_check
    CHECK (level IN ('INFO', 'WARNING', 'ERROR', 'CRITICAL'));

-- 3. 초기 행 삽입 (없을 때만)
INSERT INTO bot_state (id, initial_balance, current_balance, top_symbols)
VALUES (1, 0, 0, '[]'::jsonb)
ON CONFLICT (id) DO NOTHING;
