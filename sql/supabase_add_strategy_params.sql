-- Zenith 전략 파라미터 핫리로드 마이그레이션
-- bot_state 테이블에 strategy_params JSONB 컬럼을 추가합니다.
-- Supabase SQL Editor에서 실행하세요.

-- 1. strategy_params 컬럼 추가 (NULL = 기본값 사용)
ALTER TABLE bot_state ADD COLUMN IF NOT EXISTS strategy_params JSONB DEFAULT NULL;

-- 2. 코멘트
COMMENT ON COLUMN bot_state.strategy_params IS '프론트엔드에서 설정한 전략 파라미터 (NULL이면 코드 기본값 사용)';


-- 3. 프론트엔드에서 전략 파라미터를 저장하는 RPC 함수
-- anon 키의 RLS 우회를 위해 SECURITY DEFINER 사용
CREATE OR REPLACE FUNCTION update_strategy_params(p_params JSONB)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
  UPDATE bot_state
  SET strategy_params = p_params,
      updated_at = now()
  WHERE id = 1;
  RETURN FOUND;
END;
$$;

-- anon, authenticated 역할에 실행 권한 부여
GRANT EXECUTE ON FUNCTION update_strategy_params(JSONB) TO anon;
GRANT EXECUTE ON FUNCTION update_strategy_params(JSONB) TO authenticated;