-- bot_state 테이블에 시장 레짐 필드 추가
-- 값: 'trending' | 'ranging' | 'volatile'
ALTER TABLE bot_state
ADD COLUMN IF NOT EXISTS market_regime TEXT DEFAULT 'ranging';

COMMENT ON COLUMN bot_state.market_regime IS '시장 레짐 상태 (trending/ranging/volatile)';
