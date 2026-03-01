-- bot_state 테이블에 종목별 변동성 비율 컬럼 추가
-- Supabase SQL Editor에서 실행하세요.

ALTER TABLE bot_state
ADD COLUMN IF NOT EXISTS symbol_volatilities JSONB DEFAULT '{}'::jsonb;

COMMENT ON COLUMN bot_state.symbol_volatilities IS '종목별 변동성 비율 (예: {"KRW-BTC": 2.58, "KRW-ETH": 2.32})';
