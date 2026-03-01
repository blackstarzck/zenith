-- ============================================================
-- sentiment_insights: 뉴스 감성 분석 결과 테이블
-- 
-- CryptoPanic 뉴스를 Gemini 2.0 Flash Lite로 감성 분석한
-- 결과를 저장합니다. 프론트엔드에서 Realtime 구독으로 표시.
-- ============================================================

CREATE TABLE IF NOT EXISTS sentiment_insights (
    id              BIGSERIAL PRIMARY KEY,
    news_id         TEXT NOT NULL UNIQUE,            -- CryptoPanic 뉴스 고유 ID (중복 방지)
    title           TEXT NOT NULL,                    -- 뉴스 제목
    source          TEXT,                             -- 출처 (예: CoinDesk, CoinTelegraph)
    url             TEXT,                             -- 원문 링크
    currencies      TEXT[] DEFAULT '{}',              -- 관련 코인 목록 (예: {'BTC', 'ETH'})
    sentiment_score REAL DEFAULT 0.0,                 -- 감성 점수 (-1.0 ~ 1.0, 음수=약세, 양수=강세)
    sentiment_label TEXT DEFAULT 'neutral',           -- 감성 라벨 (bullish, bearish, neutral)
    decision        TEXT DEFAULT 'WAIT',              -- AI 최종 판단 (BUY, SELL, HOLD, WAIT)
    confidence      REAL DEFAULT 0.0,                 -- AI 신뢰도 (0 ~ 100)
    reasoning_chain TEXT,                             -- AI 추론 과정 (단계별 텍스트)
    keywords        TEXT[] DEFAULT '{}',              -- 핵심 키워드 목록
    positive_factors TEXT[] DEFAULT '{}',             -- 긍정 요인 목록
    negative_factors TEXT[] DEFAULT '{}',             -- 부정 요인 목록
    volume_impact   BOOLEAN DEFAULT FALSE,            -- 뉴스 발생 후 거래량 급증 여부
    verification_result TEXT,                         -- 사후 검증 (correct, incorrect, null=미검증)
    actual_price_change REAL,                         -- 1시간 후 실제 가격 변동률 (%)
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- 인덱스: 최신순 조회 최적화
CREATE INDEX IF NOT EXISTS idx_sentiment_created_at
    ON sentiment_insights (created_at DESC);

-- 인덱스: 코인별 필터링 (GIN for array containment)
CREATE INDEX IF NOT EXISTS idx_sentiment_currencies
    ON sentiment_insights USING GIN (currencies);

-- 인덱스: 뉴스 ID 중복 확인 (UNIQUE 제약이 이미 인덱스 생성하지만 명시)
-- news_id UNIQUE constraint가 이미 인덱스 역할

-- Supabase Realtime 활성화
ALTER PUBLICATION supabase_realtime ADD TABLE sentiment_insights;

-- RLS 활성화
ALTER TABLE sentiment_insights ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Service role full access" ON sentiment_insights;
CREATE POLICY "Service role full access" ON sentiment_insights
    FOR ALL USING (true) WITH CHECK (true);

-- 프론트엔드 anon 키로 조회/삽입 허용
GRANT SELECT, INSERT, UPDATE, DELETE ON sentiment_insights TO anon;
GRANT SELECT, INSERT, UPDATE, DELETE ON sentiment_insights TO authenticated;

-- BIGSERIAL 시퀀스 권한 (INSERT 시 id 자동 생성 필요)
GRANT USAGE, SELECT ON SEQUENCE sentiment_insights_id_seq TO anon;
GRANT USAGE, SELECT ON SEQUENCE sentiment_insights_id_seq TO authenticated;
