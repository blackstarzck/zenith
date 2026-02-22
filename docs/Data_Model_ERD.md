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

## 3. 데이터 보존 정책
- **거래 기록**: 영구 보존 (수익 분석용)
- **시스템 로그**: 30일 경과 시 자동 삭제 또는 백업 (DB 용량 관리)