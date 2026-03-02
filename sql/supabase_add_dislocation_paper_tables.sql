-- ============================================================
-- Cross-Exchange 괴리 자동 모의매매 데이터 저장 테이블
-- - dislocation_paper_trades: 매수/매도 체결 로그
-- - dislocation_paper_metrics: 전략 검증용 지표 스냅샷
-- ============================================================

CREATE TABLE IF NOT EXISTS dislocation_paper_trades (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id UUID NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    side VARCHAR(10) NOT NULL,                     -- BUY | SELL
    reason TEXT,                                   -- 체결 사유

    price DECIMAL(20, 8) NOT NULL,                 -- 체결가 (업비트)
    quantity DECIMAL(30, 12) NOT NULL,
    amount DECIMAL(20, 8) NOT NULL,
    fee DECIMAL(20, 8) NOT NULL,
    pnl DECIMAL(20, 8),                            -- SELL 시 실현손익

    upbit_price DECIMAL(20, 8) NOT NULL,
    binance_price_usdt DECIMAL(20, 8) NOT NULL,
    usdt_krw_rate DECIMAL(20, 8) NOT NULL,
    foreign_price_krw DECIMAL(20, 8) NOT NULL,
    dislocation_pct DECIMAL(10, 6) NOT NULL,

    entry_threshold_pct DECIMAL(10, 6),
    exit_threshold_pct DECIMAL(10, 6),
    take_profit_pct DECIMAL(10, 6),
    stop_loss_pct DECIMAL(10, 6),
    max_hold_minutes INTEGER,
    order_amount DECIMAL(20, 8),
    entry_slice_index INTEGER,
    entry_slices INTEGER,
    exit_slice_index INTEGER,
    exit_slices INTEGER,

    upbit_momentum_1m DECIMAL(10, 6),
    upbit_momentum_5m DECIMAL(10, 6),
    binance_momentum_1m DECIMAL(10, 6),
    lead_gap_pct DECIMAL(10, 6),
    upbit_bid_pressure DECIMAL(10, 6),
    binance_bid_pressure DECIMAL(10, 6),
    chart_filter_pass BOOLEAN,
    lead_filter_pass BOOLEAN,
    dislocation_filter_pass BOOLEAN,
    orderbook_filter_pass BOOLEAN,

    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_dislocation_paper_trades_created_at
    ON dislocation_paper_trades (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_dislocation_paper_trades_symbol_time
    ON dislocation_paper_trades (symbol, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_dislocation_paper_trades_run_id
    ON dislocation_paper_trades (run_id);


CREATE TABLE IF NOT EXISTS dislocation_paper_metrics (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id UUID NOT NULL,
    symbol VARCHAR(20) NOT NULL,

    upbit_price DECIMAL(20, 8) NOT NULL,
    binance_price_usdt DECIMAL(20, 8) NOT NULL,
    usdt_krw_rate DECIMAL(20, 8) NOT NULL,
    foreign_price_krw DECIMAL(20, 8) NOT NULL,
    dislocation_pct DECIMAL(10, 6) NOT NULL,

    auto_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    has_position BOOLEAN NOT NULL DEFAULT FALSE,
    avg_entry_price DECIMAL(20, 8),
    unrealized_pnl_pct DECIMAL(10, 6),

    entry_threshold_pct DECIMAL(10, 6),
    exit_threshold_pct DECIMAL(10, 6),
    take_profit_pct DECIMAL(10, 6),
    stop_loss_pct DECIMAL(10, 6),
    max_hold_minutes INTEGER,
    entry_slices INTEGER,
    next_entry_slice INTEGER,
    next_exit_slice INTEGER,

    upbit_momentum_1m DECIMAL(10, 6),
    upbit_momentum_5m DECIMAL(10, 6),
    binance_momentum_1m DECIMAL(10, 6),
    lead_gap_pct DECIMAL(10, 6),
    upbit_bid_pressure DECIMAL(10, 6),
    binance_bid_pressure DECIMAL(10, 6),
    chart_filter_pass BOOLEAN,
    lead_filter_pass BOOLEAN,
    dislocation_filter_pass BOOLEAN,
    orderbook_filter_pass BOOLEAN,
    all_filters_pass BOOLEAN,

    decision VARCHAR(30),                          -- BUY | SELL | HOLD | WAIT | SKIP
    reason TEXT,

    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_dislocation_paper_metrics_created_at
    ON dislocation_paper_metrics (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_dislocation_paper_metrics_symbol_time
    ON dislocation_paper_metrics (symbol, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_dislocation_paper_metrics_run_id
    ON dislocation_paper_metrics (run_id);


-- Realtime 활성화
ALTER PUBLICATION supabase_realtime ADD TABLE dislocation_paper_trades;
ALTER PUBLICATION supabase_realtime ADD TABLE dislocation_paper_metrics;

-- RLS
ALTER TABLE dislocation_paper_trades ENABLE ROW LEVEL SECURITY;
ALTER TABLE dislocation_paper_metrics ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Service role full access" ON dislocation_paper_trades;
CREATE POLICY "Service role full access" ON dislocation_paper_trades
    FOR ALL USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "Service role full access" ON dislocation_paper_metrics;
CREATE POLICY "Service role full access" ON dislocation_paper_metrics
    FOR ALL USING (true) WITH CHECK (true);

GRANT SELECT, INSERT, UPDATE, DELETE ON dislocation_paper_trades TO anon, authenticated, service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON dislocation_paper_metrics TO anon, authenticated, service_role;
