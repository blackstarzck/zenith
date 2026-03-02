# API 키 및 환경 변수 가이드

## 1. 백엔드 환경 파일
- 파일명: `.env.backend`
- 템플릿: `.env.example`

### 1.1 거래/저장소
- `UPBIT_ACCESS_KEY`: 업비트 거래 API Access Key
- `UPBIT_SECRET_KEY`: 업비트 거래 API Secret Key
- `SUPABASE_URL`: Supabase 프로젝트 URL
- `SUPABASE_SECRET_KEY`: Supabase Service Role Key

### 1.2 알림/인증
- `KAKAO_REST_API_KEY`: 카카오 REST API 키
- `KAKAO_CLIENT_SECRET`: 카카오 Client Secret
- `KAKAO_ACCESS_TOKEN`: 카카오 Access Token
- `KAKAO_REFRESH_TOKEN`: 카카오 Refresh Token

### 1.3 뉴스/AI
- `GROQ_API_KEY`: Groq API 키
- `CRYPTOPANIC_API_KEY`: CryptoPanic API 키

### 1.4 거래소 괴리(Cross-Exchange)
- `BINANCE_API_KEY`: 바이낸스 API Key (공개 시세 조회만 사용할 경우 비워도 동작 가능)
- `BINANCE_SECRET_KEY`: 바이낸스 Secret Key (공개 시세 조회만 사용할 경우 비워도 동작 가능)
- `USDT_KRW_SOURCE`: 환산 소스 (`upbit` 권장)
- `UPBIT_USDT_MARKET`: 업비트 USDT 마켓 코드 (기본 `KRW-USDT`)
- `USDT_KRW_FALLBACK_RATE`: 환율 조회 실패 시 대체 환산값
- `USDT_KRW_REFRESH_INTERVAL_SEC`: 환율 캐시 갱신 주기(초)

## 2. 프론트엔드 환경 파일
- 파일명: `frontend/.env`
- 템플릿: `frontend/.env.example`

### 2.1 Supabase
- `VITE_SUPABASE_URL`
- `VITE_SUPABASE_ANON_KEY`

### 2.2 Kakao OAuth
- `VITE_KAKAO_REST_API_KEY`
- `VITE_KAKAO_CLIENT_SECRET`
- `VITE_KAKAO_REDIRECT_URI`
