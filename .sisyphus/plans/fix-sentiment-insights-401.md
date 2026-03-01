# Fix: sentiment_insights 401 Unauthorized + 뉴스 미수집

## 배경

GNB 뉴스 감성 분석 Drawer에 아무것도 표시되지 않는 문제. 진단 결과 2가지 원인 발견:

1. **CryptoPanic API 404** — `news_collector.py`가 v1 엔드포인트 사용 (v2 키로) → ✅ 이미 수정 완료
2. **프론트엔드 401 Unauthorized** — `sentiment_insights` 테이블에 RLS 정책 + GRANT 누락

## 근본 원인

`sql/supabase_add_sentiment_insights.sql`에 다른 테이블(`bot_state`, `balance_snapshots` 등)에는 있는 RLS/권한 설정이 빠져있음:

```
-- 다른 테이블에는 모두 있는 패턴:
ALTER TABLE xxx ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role full access" ON xxx FOR ALL USING (true) WITH CHECK (true);
GRANT SELECT, INSERT, UPDATE, DELETE ON xxx TO anon;
GRANT SELECT, INSERT, UPDATE, DELETE ON xxx TO authenticated;
```

프론트엔드가 `anon` 키로 Supabase에 접근하므로, GRANT 없이는 401이 반환됨.

---

## TODO 목록

### TODO-1: SQL 마이그레이션 파일에 RLS + GRANT 추가
- **파일**: `sql/supabase_add_sentiment_insights.sql`
- **작업**: 파일 끝 (`ALTER PUBLICATION` 라인 다음)에 아래 SQL 추가
- **참조 패턴**: `sql/supabase_add_bot_state.sql` L13-22, `sql/supabase_add_balance_snapshots.sql` L10-22

```sql
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
```

- **QA**: 파일 내용 읽어서 RLS + GRANT + SEQUENCE 구문 존재 확인

### TODO-2: Supabase에 권한 SQL 즉시 적용
- **작업**: 사용자에게 Supabase 대시보드 → SQL Editor에서 아래 쿼리 실행 안내

```sql
-- sentiment_insights 테이블 권한 수정 (즉시 적용)
ALTER TABLE sentiment_insights ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Service role full access" ON sentiment_insights;
CREATE POLICY "Service role full access" ON sentiment_insights
    FOR ALL USING (true) WITH CHECK (true);

GRANT SELECT, INSERT, UPDATE, DELETE ON sentiment_insights TO anon;
GRANT SELECT, INSERT, UPDATE, DELETE ON sentiment_insights TO authenticated;

GRANT USAGE, SELECT ON SEQUENCE sentiment_insights_id_seq TO anon;
GRANT USAGE, SELECT ON SEQUENCE sentiment_insights_id_seq TO authenticated;
```

- **QA**: 프론트엔드 브라우저 콘솔에서 401 에러 사라졌는지 확인

### TODO-3: news_collector.py v2 수정 검증
- **파일**: `src/collector/news_collector.py`
- **작업**: 이미 적용된 v1→v2 수정이 올바른지 최종 확인
- **검증 항목**:
  - L29: endpoint가 `https://cryptopanic.com/api/developer/v2/posts/`인지
  - L48: `"public": "true"` 파라미터 존재하는지
  - L49: `"regions": "ko"`인지
  - `"kind": "news"` 파라미터가 제거되었는지 (v2에서 disabled)
- **참조**: `docs/CryptoPanic_API_.postman_collection.json` L15-83의 정상 URL/파라미터
- **QA**: grep으로 `api/v1` 잔여 참조 없음 확인

## 영향 범위

- `sql/supabase_add_sentiment_insights.sql` — SQL 파일 1개 수정
- `src/collector/news_collector.py` — 이미 수정 완료 (검증만)
- Supabase 대시보드 — SQL 실행 필요 (사용자 수동)

## Final Verification Wave

- [x] `news_collector.py`에 `hashlib` import 존재
- [x] `result.get("id"` 패턴 없음
- [x] `"public"` 파라미터 없음
- [x] 파싱 로직이 v2 응답 구조(title, description, published_at, created_at, kind)에 대응
