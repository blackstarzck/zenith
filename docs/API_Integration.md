# API 연동 규격서 (API Integration)

## 1. 업비트 (Upbit) API
- **필요 권한:** 자산 조회, 주문 조회, 주문하기 (입출금 권한 제외 권장).
- **인증 방식:** Access Key, Secret Key를 이용한 JWT 토큰 인증.
- **주요 Endpoint:**
    - `GET /v1/accounts` (잔고 확인)
    - `POST /v1/orders` (주문 생성)

## 2. 슈파베이스 (Supabase) DB
- **연동 방식:** `supabase-py` 라이브러리 활용.
- **주요 테이블 구조:**
    - `trades`: id, symbol, side, price, volume, fee, created_at
    - `daily_stats`: date, total_balance, profit_loss

## 3. 카카오톡 알림 (KakaoTalk API)
- **방식:** 카카오톡 메시지 API (나에게 보내기) 활용.
- **인증:** 카카오 개발자 센터의 REST API 키 및 OAuth2.0 Access Token 필요.
- **알림 템플릿:** - [매수 알림] {종목명} | 가격: {가격} | 비중: {비중}%
    - [매도 알림] {종목명} | 수익률: {수익률}% | 손익: {금액}