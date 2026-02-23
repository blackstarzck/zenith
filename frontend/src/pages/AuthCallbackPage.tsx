import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Spin, Typography, Alert, Flex } from 'antd';
import {
  exchangeCodeForTokens,
  fetchKakaoUserInfo,
  saveTokensToSupabase,
  useAuthSetter,
} from '../contexts/AuthContext';

const { Title, Text } = Typography;

type CallbackState = 'loading' | 'success' | 'error';

export default function AuthCallbackPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const setAuthUser = useAuthSetter();
  const [state, setState] = useState<CallbackState>('loading');
  const [step, setStep] = useState('인증 코드 확인 중...');
  const [errorMsg, setErrorMsg] = useState('');

  useEffect(() => {
    const code = searchParams.get('code');
    const error = searchParams.get('error');

    if (error) {
      setErrorMsg(`카카오 인증 실패: ${searchParams.get('error_description') ?? error}`);
      setState('error');
      return;
    }

    if (!code) {
      setErrorMsg('인증 코드가 없습니다. 다시 로그인해주세요.');
      setState('error');
      return;
    }

    processAuth(code);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function processAuth(code: string) {
    try {
      // Step 1: 토큰 교환
      setStep('토큰 교환 중...');
      const tokens = await exchangeCodeForTokens(code);

      // Step 2: 사용자 정보 가져오기
      setStep('사용자 정보 조회 중...');
      const user = await fetchKakaoUserInfo(tokens.access_token);

      // Step 3: Supabase에 토큰 저장
      setStep('토큰 저장 중...');
      await saveTokensToSupabase(tokens.access_token, tokens.refresh_token, user);

      // Step 4: 프론트엔드 세션 저장
      setAuthUser(user);
      setState('success');

      // 대시보드로 리다이렉트
      setTimeout(() => navigate('/', { replace: true }), 1000);
    } catch (err) {
      const msg = err instanceof Error ? err.message : '알 수 없는 오류';
      setErrorMsg(msg);
      setState('error');
    }
  }

  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: '#0a0a0a',
      }}
    >
      <Flex vertical gap={16} align="center">
        <Title level={3} style={{ color: '#fff', letterSpacing: 4, margin: 0 }}>
          ZENITH
        </Title>

        {state === 'loading' && (
          <>
            <Spin size="large" />
            <Text style={{ color: '#999' }}>{step}</Text>
          </>
        )}

        {state === 'success' && (
          <Alert
            type="success"
            title="로그인 성공!"
            description="대시보드로 이동합니다..."
            showIcon
            style={{ maxWidth: 400 }}
          />
        )}

        {state === 'error' && (
          <Alert
            type="error"
            title="로그인 실패"
            description={errorMsg}
            showIcon
            style={{ maxWidth: 400 }}
            action={
              <a href="/" style={{ color: '#1668dc' }}>
                다시 시도
              </a>
            }
          />
        )}
      </Flex>
    </div>
  );
}
