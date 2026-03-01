# Learnings — fix-sentiment-insights-401

## 1. Supabase 테이블 생성 시 RLS/GRANT 패턴 필수
- 모든 테이블에 아래 패턴이 있어야 프론트엔드(anon key)에서 접근 가능:
  - `ALTER TABLE xxx ENABLE ROW LEVEL SECURITY;`
  - `CREATE POLICY "Service role full access" ON xxx FOR ALL USING (true) WITH CHECK (true);`
  - `GRANT SELECT, INSERT, UPDATE, DELETE ON xxx TO anon;`
  - `GRANT SELECT, INSERT, UPDATE, DELETE ON xxx TO authenticated;`
- BIGSERIAL 컬럼 사용 시 시퀀스 권한도 필요:
  - `GRANT USAGE, SELECT ON SEQUENCE xxx_id_seq TO anon;`

## 2. CryptoPanic API v1 vs v2
- Developer 플랜 API 키는 `/api/developer/v2/posts/` 엔드포인트 사용
- v2 필수 파라미터: `public=true`
- v2에서 `kind` 파라미터는 disabled (제거해야 함)
- Postman 컬렉션(`docs/CryptoPanic_API_.postman_collection.json`)이 정상 URL의 참조 소스

## 3. 프론트엔드 401 = Supabase RLS/GRANT 문제
- 프론트엔드는 CryptoPanic/Groq API를 직접 호출하지 않음
- 프론트엔드는 Supabase REST API만 호출 (anon key)
- 401은 Supabase 테이블의 GRANT 누락이 원인
