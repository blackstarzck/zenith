## 프론트엔드 상세 설계 문서 (React & Supabase)

### 1. 서비스 사이트맵 (Sitemap)

시스템의 기능을 논리적으로 분리하여 4개의 주요 페이지로 구성합니다.

* **Dashboard (메인):** 전체 자산 현황, 실시간 수익률, 핵심 지표 요약 및 API 상태 모니터링.
* **Trading (매매):** 현재 보유 종목 상세, 전략 적합도 레이더, 봇 작동 상태 모니터링 및 수동 제어.
* **Analytics (분석):** 과거 매매 이력 리스트, 성과 지표(승률, MDD) 그래프 및 백테스팅 비교 벤치마킹.
* **Settings (설정):** 업비트/슈파베이스 API 설정, 전략 파라미터(, ATR 계수 등) 조정.

---

### 2. 페이지별 레이아웃 및 구성

전체 레이아웃은 **좌측 사이드바(Navigation)**와 **우측 메인 콘텐츠 영역(Main Content)**으로 나뉩니다.

#### 2.1. Dashboard (오버뷰)

* **상단(Summary Cards):** 총 자산, 전일 대비 변동, 현재 운용 중인 종목 수, **리스크 노출도(Risk Exposure)**, **API 쿼터(Rate Limit) 상태**.
* **중앙(Chart Section):** Recharts를 활용한 자산 성장 곡선 및 현재 자산 구성 비율(Donut Chart).
* **하단(Quick View):** 최근 5건의 매매 이력 및 시스템 로그 요약.

#### 2.2. Trading (모니터링 & 제어)

* **좌측(Asset List):** 현재 보유 중인 코인 카드 리스트 및 실시간 미실현 손익률 표시.
* **우측(Detail View):** 선택한 코인의 실시간 호가 정보 및 **전략 적합도 레이더(RSI, BB 위치 등 시각화)**.
* **하단(Terminal):** 봇이 현재 수행 중인 로직(데이터 수집, 조건 검사 등)을 텍스트로 출력하는 실시간 로그 뷰어.

---

### 3. 핵심 컴포넌트 상세 설계

#### 3.1. 탭 컴포넌트 (Tabs)

정보의 밀도가 높은 'Trading'과 'Analytics' 페이지에서 공간 효율을 극대화합니다.

* **Trading Page Tabs:**
* **Active Positions:** 현재 매수 상태인 종목들의 실시간 수익 현황, 평단가, **동적 손절가(ATR 기반)** 표시.
* **Pending Orders:** 전략 필터를 통과하고 매수/매도 타점을 기다리며 감시 중인 종목 리스트.


* **Analytics Page Tabs:**
* **Trade History:** 익절/손절로 마감된 거래 기록 상세 분석.
* **Benchmarking:** 백테스팅 예측 수익과 실제 실전 수익의 괴리율을 비교하는 대조 그래프.



#### 3.2. 모달 컴포넌트 (Modals)

중요도가 높거나 파괴적인 작업 시 사용자 확인을 위해 사용합니다.

* **Emergency Sell Modal:** 특정 종목 또는 전량 시장가 매도 확인을 위한 붉은색 경고 UI.
* **Manual Override Modal:** 봇의 자동 로직을 일시 중단하거나 특정 포지션을 수동으로 즉시 청산하기 위한 제어창.
* **Strategy Edit Modal:** 평균 회귀 전략의 핵심 변수(표준편차 , ATR 손절 계수 등) 수정 및 즉시 반영.
* **API Configuration Modal:** 업비트/슈파베이스 API Key 입력 및 연결 지연 시간(Latency) 테스트.

---

### 4. UI/UX 논리 구조

**4.1. 실시간 데이터 업데이트 (Reactive UI)**

* Supabase의 **Real-time Subscription**을 활용하여 `system_logs` 및 `trades` 테이블의 변화를 실시간으로 반영합니다.
* **API Health 모니터링:** 초당 호출 횟수 제한(Rate Limit)을 시각 게이지로 표시하여 시스템 안정성을 상시 확인합니다.

**4.2. 상태 기반 스타일링**

* **수익률 표현:** 일 경우 텍스트와 보더를 `#FF4D4D`(상승장 레드)로, 일 경우 `#4D94FF`(하락장 블루)로 동적 할당합니다.
* **봇 상태 표시:** 봇이 정상 작동 중일 때는 헤더에 'Heartbeat' 애니메이션(초록색 점)을 배치하고, 오류 발생 시 주황색/빨간색으로 즉시 전환합니다.
* **동적 손절선 시각화:** 실시간 가격 차트 위에 ATR 기반으로 계산된 손절 타겟을 점선으로 표시하여 위험 구간 접근 시 시각적 경고를 제공합니다.

Would you like me to generate the React component code for the **Strategy Health Radar** or the **API Quota Gauge** based on this design?