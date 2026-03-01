-- Zenith 트레이딩 봇 Supabase 테이블 생성 스크립트
-- Supabase SQL Editor에서 실행하세요.

-- 1. trades: 매매 상세 기록
CREATE TABLE IF NOT EXISTS trades (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    side VARCHAR(10) NOT NULL CHECK (side IN ('bid', 'ask')),
    price DECIMAL(20, 8) NOT NULL,
    volume DECIMAL(20, 8) NOT NULL,
    amount DECIMAL(20, 4) NOT NULL,
    fee DECIMAL(20, 4) DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_trades_symbol ON trades(symbol);
CREATE INDEX idx_trades_created_at ON trades(created_at DESC);
CREATE INDEX idx_trades_side ON trades(side);

-- 2. daily_stats: 일별 성과 지표
CREATE TABLE IF NOT EXISTS daily_stats (
    stats_date DATE PRIMARY KEY,
    total_balance DECIMAL(20, 4) NOT NULL,
    net_profit DECIMAL(20, 4) DEFAULT 0,
    drawdown DECIMAL(10, 4) DEFAULT 0
);

-- 3. system_logs: 시스템 상태 기록
CREATE TABLE IF NOT EXISTS system_logs (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    level VARCHAR(10) NOT NULL CHECK (level IN ('INFO', 'WARNING', 'ERROR')),
    message TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_system_logs_created_at ON system_logs(created_at DESC);
CREATE INDEX idx_system_logs_level ON system_logs(level);

-- 4. 30일 초과 로그 자동 삭제 정책 (pg_cron 사용 시)
-- SELECT cron.schedule(
--     'cleanup-old-logs',
--     '0 3 * * *',  -- 매일 새벽 3시
--     $$DELETE FROM system_logs WHERE created_at < now() - interval '30 days'$$
-- );

-- 5. kakao_tokens: 카카오 OAuth 토큰 저장
CREATE TABLE IF NOT EXISTS kakao_tokens (
    id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),  -- 단일 행만 허용
    access_token TEXT NOT NULL,
    refresh_token TEXT NOT NULL,
    nickname VARCHAR(100) DEFAULT '',
    profile_image TEXT DEFAULT '',
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- 6. RLS (Row Level Security) 활성화
ALTER TABLE trades ENABLE ROW LEVEL SECURITY;
ALTER TABLE daily_stats ENABLE ROW LEVEL SECURITY;
ALTER TABLE system_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE kakao_tokens ENABLE ROW LEVEL SECURITY;

-- service_role 키로 접근 시 모든 작업 허용 (멱등성 보장)
DROP POLICY IF EXISTS "Service role full access" ON trades;
CREATE POLICY "Service role full access" ON trades
    FOR ALL USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "Service role full access" ON daily_stats;
CREATE POLICY "Service role full access" ON daily_stats
    FOR ALL USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "Service role full access" ON system_logs;
CREATE POLICY "Service role full access" ON system_logs
    FOR ALL USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "Service role full access" ON kakao_tokens;
CREATE POLICY "Service role full access" ON kakao_tokens
    FOR ALL USING (true) WITH CHECK (true);

-- anon 키로 프론트엔드에서 kakao_tokens 읽기/쓰기 허용
DROP POLICY IF EXISTS "Anon kakao_tokens access" ON kakao_tokens;
CREATE POLICY "Anon kakao_tokens access" ON kakao_tokens
    FOR ALL USING (true) WITH CHECK (true);

-- 테이블 권한 부여 (프론트엔드 anon 키로 조회/기록 가능)
GRANT SELECT, INSERT, UPDATE, DELETE ON trades TO anon;
GRANT SELECT, INSERT, UPDATE, DELETE ON trades TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON daily_stats TO anon;
GRANT SELECT, INSERT, UPDATE, DELETE ON daily_stats TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON system_logs TO anon;
GRANT SELECT, INSERT, UPDATE, DELETE ON system_logs TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON kakao_tokens TO anon;
GRANT SELECT, INSERT, UPDATE, DELETE ON kakao_tokens TO authenticated;

-- Realtime 활성화
ALTER PUBLICATION supabase_realtime ADD TABLE trades;
ALTER PUBLICATION supabase_realtime ADD TABLE system_logs;
ALTER PUBLICATION supabase_realtime ADD TABLE daily_stats;
