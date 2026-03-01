-- trades 테이블에 예상 슬리피지(bps) 컬럼 추가
ALTER TABLE trades
ADD COLUMN IF NOT EXISTS slippage DECIMAL(10, 4) DEFAULT NULL;

COMMENT ON COLUMN trades.slippage IS '매수 진입 시 예상 슬리피지 (bps 단위). 매도 거래는 NULL.';

-- bot_state 테이블에 켈리 비중 컬럼 추가
ALTER TABLE bot_state
ADD COLUMN IF NOT EXISTS kelly_fraction DECIMAL(10, 6) DEFAULT NULL;

COMMENT ON COLUMN bot_state.kelly_fraction IS '현재 켈리 공식 기반 포지션 비중 (0.0~1.0). NULL이면 고정비율 사용 중.';
