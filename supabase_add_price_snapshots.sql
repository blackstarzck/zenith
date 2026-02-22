-- Zenith 가격 스냅샷 테이블 추가 마이그레이션
-- Supabase SQL Editor에서 실행하세요.

-- 1. price_snapshots: 종목별 가격 + 손절선 + 익절선 스냅샷
CREATE TABLE IF NOT EXISTS price_snapshots (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    price DECIMAL(20, 8) NOT NULL,
    stop_loss DECIMAL(20, 8),
    take_profit DECIMAL(20, 8),
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_price_snapshots_symbol ON price_snapshots(symbol);
CREATE INDEX idx_price_snapshots_created_at ON price_snapshots(created_at DESC);
CREATE INDEX idx_price_snapshots_symbol_time ON price_snapshots(symbol, created_at DESC);

-- 2. RLS 활성화
ALTER TABLE price_snapshots ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Service role full access" ON price_snapshots;
CREATE POLICY "Service role full access" ON price_snapshots
    FOR ALL USING (true) WITH CHECK (true);

-- 3. 권한 부여 (프론트엔드 anon 키로 조회 가능)
GRANT SELECT, INSERT, UPDATE, DELETE ON price_snapshots TO anon;
GRANT SELECT, INSERT, UPDATE, DELETE ON price_snapshots TO authenticated;

-- 4. Realtime 활성화
ALTER PUBLICATION supabase_realtime ADD TABLE price_snapshots;

-- 5. 7일 초과 스냅샷 자동 삭제 (pg_cron 사용 시)
-- SELECT cron.schedule(
--     'cleanup-old-price-snapshots',
--     '0 4 * * *',  -- 매일 새벽 4시
--     $$DELETE FROM price_snapshots WHERE created_at < now() - interval '7 days'$$
-- );
