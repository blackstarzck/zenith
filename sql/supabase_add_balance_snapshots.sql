-- balance_snapshots: 시간단위 자산 성장 곡선용 (약 3분 간격 저장)
CREATE TABLE IF NOT EXISTS balance_snapshots (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    total_balance DECIMAL(20, 4) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_balance_snapshots_created_at ON balance_snapshots(created_at DESC);

-- RLS
ALTER TABLE balance_snapshots ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Service role full access" ON balance_snapshots;
CREATE POLICY "Service role full access" ON balance_snapshots
    FOR ALL USING (true) WITH CHECK (true);

-- 권한
GRANT SELECT, INSERT, UPDATE, DELETE ON balance_snapshots TO anon;
GRANT SELECT, INSERT, UPDATE, DELETE ON balance_snapshots TO authenticated;

-- Realtime
ALTER PUBLICATION supabase_realtime ADD TABLE balance_snapshots;
