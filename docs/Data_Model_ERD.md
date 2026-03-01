# 데이터 모델 설계서 (Data Model Design)

## 1. 개요
본 시스템은 Supabase(PostgreSQL)를 사용하여 매매 데이터의 영속성을 유지합니다. 데이터는 크게 '거래 기록', '자산 통계', '시스템 로그' 세 가지 범주로 관리됩니다.

## 2. 테이블 정의

### 2.1 trades (매매 상세 기록)
매수 및 매도의 모든 체결 내역을 기록하는 테이블입니다.
- **id**: UUID (PK)
- **symbol**: VARCHAR (예: KRW-BTC)
- **side**: VARCHAR (bid: 매수, ask: 매도)
- **price**: DECIMAL (체결 가격)
- **volume**: DECIMAL (체결 수량)
- **amount**: DECIMAL (총 거래 금액)
- **fee**: DECIMAL (수수료)
- **slippage**: DECIMAL | NULL (예상 슬리피지 bps, 매수 거래만 기록)
- **created_at**: TIMESTAMP (거래 시간)

### 2.2 daily_stats (일별 성과 지표)
자산의 성장 흐름을 추적하기 위한 테이블입니다.
- **stats_date**: DATE (PK)
- **total_balance**: DECIMAL (총 자산 가치)
- **net_profit**: DECIMAL (당일 순손익)
- **drawdown**: DECIMAL (최대 낙폭 지표)

### 2.3 system_logs (시스템 상태 기록)
오류 추적 및 시스템 상태 모니터링을 위한 기록입니다.
- **id**: BIGINT (PK)
- **level**: VARCHAR (INFO, WARNING, ERROR)
- **message**: TEXT (로그 내용)
- **created_at**: TIMESTAMP
### 2.4 bot_state (봇 실시간 상태)
봇의 현재 운영 상태를 단일 행으로 관리합니다.
- **id**: INTEGER (PK, 항상 1)
- **initial_balance**: DECIMAL (초기 자산)
- **current_balance**: DECIMAL (현재 자산)
- **krw_balance**: DECIMAL (KRW 잔고)
- **top_symbols**: JSONB (감시 종목 목록)
- **symbol_volatilities**: JSONB (종목별 지표)
- **is_active**: BOOLEAN (봇 활성 여부)
- **upbit_status**: VARCHAR (업비트 연결 상태)
- **kakao_status**: VARCHAR (카카오 연결 상태)
- **strategy_params**: JSONB (전략 파라미터)
- **market_regime**: TEXT (시장 레짐 상태 — trending/ranging/volatile, 기본값 'ranging')
- **kelly_fraction**: DECIMAL | NULL (현재 켈리 비중 0.0~1.0, 데이터 부족 시 NULL)
- **updated_at**: TIMESTAMP

### 2.5 sentiment_insights (뉴스 감성 분석)
CryptoPanic 뉴스를 Gemini 2.0 Flash Lite로 분석한 결과를 저장합니다.
- **id**: BIGSERIAL (PK)
- **news_id**: VARCHAR UNIQUE NOT NULL (CryptoPanic 뉴스 ID)
- **title**: TEXT NOT NULL (뉴스 제목)
- **source**: VARCHAR (뉴스 출처)
- **url**: TEXT (원문 링크)
- **currencies**: JSONB DEFAULT '[]' (관련 코인 목록)
- **sentiment_score**: DECIMAL DEFAULT 0.0 (-1.0~1.0, 음수=약세, 양수=강세)
- **sentiment_label**: VARCHAR DEFAULT 'neutral' (bullish/bearish/neutral)
- **decision**: VARCHAR DEFAULT 'WAIT' (BUY/SELL/HOLD/WAIT)
- **confidence**: DECIMAL DEFAULT 0.0 (0~100)
- **reasoning_chain**: TEXT (AI 단계별 추론 과정)
- **keywords**: JSONB DEFAULT '[]' (핵심 키워드)
- **positive_factors**: JSONB DEFAULT '[]' (긍정 요인)
- **negative_factors**: JSONB DEFAULT '[]' (부정 요인)
- **volume_impact**: BOOLEAN DEFAULT FALSE (거래량 영향 여부)
- **verification_result**: VARCHAR | NULL (correct/incorrect, 사후 검증)
- **actual_price_change**: DECIMAL | NULL (실제 가격 변동률 %)
- **created_at**: TIMESTAMPTZ DEFAULT now()
- **인덱스**: created_at DESC, news_id UNIQUE, sentiment_label, currencies (GIN)


## 3. 데이터 보존 정책
- **거래 기록**: 영구 보존 (수익 분석용)
- **시스템 로그**: 30일 경과 시 자동 삭제 또는 백업 (DB 용량 관리)
- **감성 분석 결과**: 7일 경과 시 자동 삭제 (orchestrator daily_reset에서 정리)
- **가격 스냅샷**: 7일 경과 시 자동 삭제
- **잔고 스냅샷**: 7일 경과 시 자동 삭제