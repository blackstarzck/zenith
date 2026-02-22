-- bot_state 테이블에 KRW 보유 잔고 컬럼 추가
-- Supabase SQL Editor에서 실행하세요.

ALTER TABLE bot_state
ADD COLUMN IF NOT EXISTS krw_balance double precision DEFAULT 0;

COMMENT ON COLUMN bot_state.krw_balance IS '현재 KRW 보유 잔고 (매수 가능 금액)';
