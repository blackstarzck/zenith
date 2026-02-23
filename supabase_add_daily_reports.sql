-- Zenith: daily_reports 테이블 + trades.reason 컬럼 추가 마이그레이션
-- Supabase SQL Editor에서 실행하세요.

-- 1. trades 테이블에 매매 사유(reason) 컬럼 추가
ALTER TABLE trades ADD COLUMN IF NOT EXISTS reason TEXT DEFAULT NULL;

-- 2. daily_reports: 일일 분석 리포트 (마크다운)
CREATE TABLE IF NOT EXISTS daily_reports (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    report_date DATE NOT NULL UNIQUE,
    content TEXT NOT NULL,
    total_balance DECIMAL(20, 4),
    net_profit DECIMAL(20, 4),
    trade_count INTEGER DEFAULT 0,
    win_count INTEGER DEFAULT 0,
    loss_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_daily_reports_date ON daily_reports(report_date DESC);

-- 3. RLS 활성화
ALTER TABLE daily_reports ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Service role full access" ON daily_reports;
CREATE POLICY "Service role full access" ON daily_reports
    FOR ALL USING (true) WITH CHECK (true);

-- 4. 권한 부여
GRANT SELECT, INSERT, UPDATE, DELETE ON daily_reports TO anon;
GRANT SELECT, INSERT, UPDATE, DELETE ON daily_reports TO authenticated;

-- 5. Realtime 활성화
ALTER PUBLICATION supabase_realtime ADD TABLE daily_reports;
