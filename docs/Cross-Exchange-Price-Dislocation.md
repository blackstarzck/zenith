# Cross-Exchange Price Dislocation PRD

## 1. 문서 목적
국내(업비트)와 해외 거래소 간 단기 가격 괴리(역프/김프)와 체결 수급 변화를 결합해, 초단기 진입/청산 신호를 생성하는 기능의 제품 요구사항을 정의한다.  
본 문서는 설명형 전략 노트를 개발 가능한 수준의 명세(PRD)로 변환한 문서다.

---

## 2. 배경 및 문제 정의
- 현재 시스템은 기술지표 기반 평균회귀/리스크 관리가 중심이며, 거래소 간 선행-후행 반응을 직접 활용하는 규칙은 부족하다.
- 실제 시장에서는 해외 선행 상승/하락이 국내에 지연 반영되며, 이때 괴리와 수급이 동시에 발생하면 짧은 시간의 유의미한 기회가 생긴다.
- 수동 트레이딩에서는 차트, 괴리율, 호가창을 동시에 보고 빠르게 대응하지만, 자동화 파이프라인에는 해당 판단 구조가 체계화되어 있지 않다.

---

## 3. 목표 / 비목표
### 3.1 목표
- 해외-국내 가격 괴리 기반 진입 신호를 자동 계산한다.
- 신호 생성 시 차트 자리(단기 구조), 괴리율, 수급(호가/체결 강도) 3요소를 모두 검증한다.
- 신호 발생 후 3~10분 내 청산하는 초단기 전략을 백테스트/실거래 모드에서 동일 규칙으로 운영한다.
- 대시보드에서 신호 근거(괴리율, 선행시장, 수급 점수, 진입/청산 이유)를 이해 가능하게 보여준다.

### 3.2 비목표
- 장기 포지션 운용(수 시간~수일) 전략 구현
- 모든 거래소 동시 지원(1차는 업비트 + 바이낸스 기준)
- 호가창 조작/유도와 같은 시장 영향형 전략

---

## 4. 핵심 가설
- 가설 A: 해외 선행 추세 + 국내 지연 반응 + 비정상 괴리(역프/김프)가 겹치면, 단기 평균복귀 확률이 높다.
- 가설 B: 괴리율만으로는 오탐이 많고, 국내 체결 수급 강도(매수 잔량/체결 속도) 필터를 추가하면 승률이 개선된다.
- 가설 C: 신호 유효시간은 짧고(3~10분), 시간 초과 보유는 손익비를 악화시킨다.

---

## 5. 사용자 시나리오
### 5.1 운영자(전략 관리자)
- 전략 파라미터(괴리 임계치, 수급 임계치, 최대 보유 시간)를 UI에서 수정
- 신호별 성과와 실패 사유를 대시보드에서 확인

### 5.2 모니터링 사용자
- “왜 진입했는지”를 수치와 상태 태그로 확인
- 뉴스/이벤트 시점 이후 시장 반응(차트 하이라이트 포함) 확인

---

## 6. 기능 요구사항
## 6.1 데이터 수집
- 업비트 실시간 체결가/호가 데이터 수집
- 해외 기준 거래소(1차: 바이낸스) 시세 수집
- 환율(USDT-KRW 또는 내부 기준 환산값) 반영하여 비교 가능한 KRW 기준 가격 계산
- 최소 1분봉 기준 OHLCV 생성, 신호 구간 상세 검증용으로 1초~5초 틱 버퍼 유지

## 6.2 신호 생성 필터(4중 필터)
아래 4개 조건이 모두 참일 때만 진입 후보를 생성한다.
1. 차트 구조 필터: 업비트 1분/5분 모멘텀이 최소 기준 이상
2. 해외 선행 필터: 바이낸스 1분 모멘텀이 업비트 1분 모멘텀보다 최소 갭 이상 선행
3. 괴리율 필터: 업비트-바이낸스 환산 괴리율이 진입 임계치 이하(역프 심화)
4. 수급 필터: 업비트/바이낸스 호가 매수압이 각각 최소 기준 이상

## 6.3 진입/청산 규칙
- 진입: 4중 필터 통과 시 1차 진입, 이후 괴리 추가 확대 시 분할 추가 진입
- 청산: 1/2/3차 목표 수익률 분할 청산 + 최대 보유 시간 강제 청산
- 손절: 반대 방향 이탈, 괴리 확대 지속, 수급 급반전 중 하나 발생 시 즉시 청산

## 6.4 대시보드 표출
- 신호 카드 필수 항목:
  - 발생 시각, 코인, 방향(BUY/SELL), 신뢰도
  - 괴리율(%), 해외 선행 강도, 국내 수급 점수
  - 진입 근거 요약, 청산 근거 요약
- 차트 요구사항:
  - 신호 발생 시점 ~ 검증 종료 시점 하이라이트
  - 해당 구간 전후(예: -10분, +20분) 시세 흐름 표시
  - AI 인사이트(예: BUY 판단 후 N분간 상승폭) 함께 표기

---

## 7. 파라미터 정의 (초기안)
- `dislocation_min_pct`: 1.5%
- `dislocation_extreme_pct`: 3.0%
- `lead_lag_window_sec`: 30~120초
- `orderbook_pressure_min`: 0.60
- `trade_imbalance_min`: 0.55
- `max_holding_minutes`: 10
- `take_profit_levels`: [0.6%, 1.2%, 1.8%]
- `stop_loss_pct`: 0.8%

주의: 위 값은 기본값이며, 백테스트 결과로 최종 확정한다.

---

## 8. 성공 지표(KPI)
- 신호 정확도(중립 제외): 55% 이상
- 기대값(수수료/슬리피지 반영 후): 0 초과
- 평균 보유 시간: 10분 이하
- MDD(전략 단독): 내부 리스크 한도 이하
- 오탐률(신호 후 1분 내 역행 급발생): 지속 감소 추세

---

## 9. 데이터 모델 및 스키마 영향
본 기능은 DB 스키마 변경 가능성이 높다. 변경 시 아래 4곳 동시 반영 필수:
1. `supabase_*.sql`
2. `src/storage/client.py`
3. `frontend/src/types/database.ts`
4. `frontend/src/hooks/useSupabase.ts`

### 9.1 신규/확장 테이블(안)
- `dislocation_paper_trades` (현재 반영)
  - `run_id`, `symbol`, `side`, `reason`
  - `price`, `quantity`, `amount`, `fee`, `pnl`
  - `upbit_price`, `binance_price_usdt`, `usdt_krw_rate`, `foreign_price_krw`, `dislocation_pct`
  - `entry_threshold_pct`, `exit_threshold_pct`, `take_profit_pct`, `stop_loss_pct`, `max_hold_minutes`, `order_amount`
  - `entry_slice_index`, `entry_slices`, `exit_slice_index`, `exit_slices`
  - `upbit_momentum_1m`, `upbit_momentum_5m`, `binance_momentum_1m`, `lead_gap_pct`
  - `upbit_bid_pressure`, `binance_bid_pressure`
  - `chart_filter_pass`, `lead_filter_pass`, `dislocation_filter_pass`, `orderbook_filter_pass`
- `dislocation_paper_metrics` (현재 반영)
  - `run_id`, `symbol`
  - `upbit_price`, `binance_price_usdt`, `usdt_krw_rate`, `foreign_price_krw`, `dislocation_pct`
  - `auto_enabled`, `has_position`, `avg_entry_price`, `unrealized_pnl_pct`
  - `entry_threshold_pct`, `exit_threshold_pct`, `take_profit_pct`, `stop_loss_pct`, `max_hold_minutes`
  - `entry_slices`, `next_entry_slice`, `next_exit_slice`
  - `upbit_momentum_1m`, `upbit_momentum_5m`, `binance_momentum_1m`, `lead_gap_pct`
  - `upbit_bid_pressure`, `binance_bid_pressure`
  - `chart_filter_pass`, `lead_filter_pass`, `dislocation_filter_pass`, `orderbook_filter_pass`, `all_filters_pass`
  - `decision`, `reason`, `created_at`
- `cross_exchange_signals`
  - `id`, `created_at`, `asset`, `direction`
  - `upbit_price`, `foreign_price_krw`, `dislocation_pct`
  - `lead_strength`, `orderbook_pressure`, `trade_imbalance`
  - `entry_reason`, `exit_reason`, `result`, `pnl_pct`
- `cross_exchange_snapshots`
  - `signal_id`, `ts`, `upbit_price`, `foreign_price_krw`, `dislocation_pct`, `volume`

---

## 10. 시스템 아키텍처 반영
- 백엔드
  - 수집: `src/collector/data_collector.py` 확장
  - 전략: `src/strategy/engine.py` 내 모듈 분리(`dislocation.py` 권장)
  - 실행: `src/executor/order_executor.py` 연동
  - 저장: `src/storage/client.py` CRUD 추가
- 프론트엔드
  - 페이지: `frontend/src/pages/SentimentImpactPage.tsx` 또는 전용 페이지 신설
  - 컴포넌트: 하이라이트 차트/신호 근거 패널 추가

---

## 11. 리스크 및 제약
- 환율/환산 기준 차이로 괴리율 오차 가능
- 거래소 API 지연/장애 시 오탐 가능
- 슬리피지가 높은 장에서 기대값 급감 가능
- 특정 알트코인 저유동성 구간에서 체결 리스크 확대

대응:
- API 지연 감지 시 신호 무효화
- 유동성 하한(거래대금/호가 깊이) 미달 종목 제외
- 리스크 매니저(`src/risk/manager.py`)의 일일 손실 한도와 연동

---

## 12. 개발 단계(권장)
1. 데이터 계층 구현: 해외 시세 + 환산 + 괴리 계산 파이프라인
2. 오프라인 검증: 백필 데이터로 괴리/수급 특징량 생성
3. 신호 엔진 구현: 4중 필터 + 진입/청산 규칙
4. 백테스트: 수수료/슬리피지 포함 성능 평가
5. 대시보드: 신호 근거 + 하이라이트 차트 노출
6. 페이퍼 트레이딩: 1~2주 검증 후 실거래 제한 오픈

### 12.1 사전 검증 UI (현재 반영)
- 페이지: `frontend/src/pages/DislocationPaperPage.tsx` (`/dislocation-paper`)
- 목적: 실거래 전, 전략 실행 흐름을 UI에서 안전하게 검증
- 규칙:
  - 초기 자산 `1,000,000 KRW`
  - 업비트 실시간 현재가 + 바이낸스 환산가 기준으로 괴리율 계산
  - 4중 필터(차트/해외선행/괴리/호가) 통과 시 자동 진입
  - 분할 진입(최대 N차) + 분할 익절(3차) + 강제 청산(손절/시간/괴리회복)
  - 수수료 `0.05%` 반영
  - 매수/매도 체결 기록, 보유 포지션, 실현/평가 손익 표시
  - 코인별 실시간 괴리율 테이블 제공 (종목 선택 시 자동매매 대상 변경)
- 제약:
  - 체결/지표는 DB에 저장되지만 실제 주문은 실행하지 않음
  - 실제 주문 API 호출 없음
  - 백엔드 주문 엔진과는 분리된 UI 레벨 사전 검증 모드
  - `dislocation_paper_trades`: 자동 체결 로그 영구 저장
  - `dislocation_paper_metrics`: 괴리/환산/임계치/판정 근거 스냅샷 저장

---

## 13. 수용 기준(Definition of Done)
- 기능
  - 4중 필터 기반 신호가 DB에 누락 없이 저장된다.
  - 신호별 진입/청산 근거와 결과가 대시보드에서 조회된다.
  - 사전 검증용 모의매매 페이지에서 초기 자산/체결/손익 계산이 정상 동작한다.
  - 모의매매 체결 로그(`dislocation_paper_trades`)와 검증 지표(`dislocation_paper_metrics`)가 DB에 누락 없이 적재된다.
- 품질
  - 백테스트 리포트에 KPI 항목이 자동 계산된다.
  - 주요 모듈에 단위 테스트/통합 테스트가 추가된다.
- 운영
  - 전략 파라미터를 UI에서 조정 가능하다.
  - 장애/지연 시 안전 중단 로직이 동작한다.

---

## 14. 오픈 이슈
- 해외 기준 거래소를 바이낸스 단일로 고정할지, 멀티 거래소 가중 평균으로 확장할지 결정 필요
- 환율 소스(실시간/지연 허용) 확정 필요
- SELL(공매도 성격) 신호를 현행 시스템에서 허용할지 정책 확정 필요
