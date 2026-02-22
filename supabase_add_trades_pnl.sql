-- Zenith: trades 테이블에 pnl(손익) 컬럼 추가 마이그레이션
-- Supabase SQL Editor에서 실행하세요.

-- 매도 시 실현 손익을 기록합니다. 매수(bid) 시에는 NULL.
ALTER TABLE trades ADD COLUMN IF NOT EXISTS pnl DECIMAL(20, 4) DEFAULT NULL;
