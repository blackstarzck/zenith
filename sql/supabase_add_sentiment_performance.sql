-- ============================================================
-- sentiment_insights 확장 + sentiment_performance_daily 추가
-- AI 감성 판단의 사후 검증 데이터를 저장하고, 일일 집계를 관리합니다.
-- ============================================================

-- 1) sentiment_insights 확장 컬럼
ALTER TABLE sentiment_insights
    ADD COLUMN IF NOT EXISTS verification_horizon_min INTEGER DEFAULT 10,
    ADD COLUMN IF NOT EXISTS baseline_price DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS evaluation_price DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS evaluated_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS direction_match BOOLEAN,
    ADD COLUMN IF NOT EXISTS pending_reason TEXT,
    ADD COLUMN IF NOT EXISTS verification_window_start_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS verification_window_end_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS window_open_price DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS window_close_price DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS window_high_price DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS window_low_price DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS window_return_pct REAL,
    ADD COLUMN IF NOT EXISTS window_max_rise_pct REAL,
    ADD COLUMN IF NOT EXISTS window_max_drop_pct REAL,
    ADD COLUMN IF NOT EXISTS verification_explanation TEXT,
    ADD COLUMN IF NOT EXISTS analysis_insight TEXT;

-- 검증 대기/완료 조회 최적화
CREATE INDEX IF NOT EXISTS idx_sentiment_verification_pending
    ON sentiment_insights (verification_result, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_sentiment_evaluated_at
    ON sentiment_insights (evaluated_at DESC);

-- 2) 일일 집계 테이블
CREATE TABLE IF NOT EXISTS sentiment_performance_daily (
    id BIGSERIAL PRIMARY KEY,
    stats_date DATE NOT NULL,
    currency TEXT NOT NULL,
    decision TEXT NOT NULL,
    verification_horizon_min INTEGER NOT NULL DEFAULT 10,
    sample_count INTEGER NOT NULL DEFAULT 0,
    verified_count INTEGER NOT NULL DEFAULT 0,
    correct_count INTEGER NOT NULL DEFAULT 0,
    direction_match_count INTEGER NOT NULL DEFAULT 0,
    avg_price_change REAL,
    avg_abs_price_change REAL,
    avg_confidence REAL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(stats_date, currency, decision, verification_horizon_min)
);

CREATE INDEX IF NOT EXISTS idx_sentiment_perf_daily_date
    ON sentiment_performance_daily (stats_date DESC);

CREATE INDEX IF NOT EXISTS idx_sentiment_perf_daily_currency
    ON sentiment_performance_daily (currency, stats_date DESC);

-- Realtime
ALTER PUBLICATION supabase_realtime ADD TABLE sentiment_performance_daily;

-- RLS
ALTER TABLE sentiment_performance_daily ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Service role full access" ON sentiment_performance_daily;
CREATE POLICY "Service role full access" ON sentiment_performance_daily
    FOR ALL USING (true) WITH CHECK (true);

GRANT ALL PRIVILEGES ON sentiment_performance_daily TO anon, authenticated, service_role;
GRANT ALL PRIVILEGES ON SEQUENCE sentiment_performance_daily_id_seq TO anon, authenticated, service_role;
