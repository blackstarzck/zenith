# Blockers — fix-sentiment-insights-401

## BLOCKED: 사용자 수동 작업 대기 (2개)

### 1. Supabase SQL 실행 필요
- **상태**: 코드 수정 완료, SQL 마이그레이션 파일 업데이트 완료
- **블로커**: 사용자가 Supabase 대시보드 → SQL Editor에서 RLS/GRANT SQL을 실행해야 함
- **실행할 SQL**:
```sql
ALTER TABLE sentiment_insights ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Service role full access" ON sentiment_insights;
CREATE POLICY "Service role full access" ON sentiment_insights
    FOR ALL USING (true) WITH CHECK (true);
GRANT SELECT, INSERT, UPDATE, DELETE ON sentiment_insights TO anon;
GRANT SELECT, INSERT, UPDATE, DELETE ON sentiment_insights TO authenticated;
GRANT USAGE, SELECT ON SEQUENCE sentiment_insights_id_seq TO anon;
GRANT USAGE, SELECT ON SEQUENCE sentiment_insights_id_seq TO authenticated;
```
- **검증**: F12 Console에서 401 에러 사라지면 성공

### 2. 봇 재시작 필요
- **상태**: `news_collector.py` v2 엔드포인트 수정 완료 (커밋 f02497b)
- **블로커**: 사용자가 Python 봇을 재시작해야 수정된 코드가 적용됨
- **검증**: 5분 후 `sentiment_insights` 테이블에 데이터 쌓이고, Drawer에 뉴스 표시되면 성공
