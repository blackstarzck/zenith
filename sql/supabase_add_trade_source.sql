-- Zenith: trades 테이블에 trade_source(거래 출처) 컬럼 추가 마이그레이션
-- Supabase SQL Editor에서 실행하세요.

-- 거래의 출처를 구분합니다: 'bot' (자동), 'manual' (수동), 'sync' (동기화)
ALTER TABLE trades ADD COLUMN IF NOT EXISTS trade_source VARCHAR(10) DEFAULT 'bot';

COMMENT ON COLUMN trades.trade_source IS '거래 출처: bot=자동매매, manual=수동매매, sync=포지션동기화';
