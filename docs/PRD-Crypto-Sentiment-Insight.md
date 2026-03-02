**실시간 뉴스 감성 기반 가상자산 인사이트 시스템 PRD**

**1. 개요**
가상자산 시장의 실시간 뉴스를 수집하고, Groq AI를 활용한 감성 분석을 통해 대시보드에 실시간 인사이트를 제공하는 시스템을 구축한다. 이 시스템은 사용자에게 시장의 심리적 상태를 시각화하여 제공하는 것을 주 목적으로 한다.

**2. 문제 정의 및 목표**

* **문제:** CryptoPanic Developer v2 API는 투표(Votes) 데이터를 제공하지 않아 뉴스의 시장 영향력을 정량적으로 판단하기 어려움.
* **목표:** CryptoPanic 뉴스를 Groq AI(Llama 3.1 8B)로 분석하여 감성 점수와 투자 판단 인사이트를 도출하고, 이를 대시보드에 실시간으로 표시함.

**3. 데이터 소스 및 API 구성**

* **CryptoPanic (Developer v2):** 한국어 뉴스 데이터 수집 (`regions=ko`). 대상 코인: BTC, ETH, XRP, SOL, DOGE, ADA.
* **Groq API (Llama 3.1 8B Instant):** 클라우드 기반 AI를 활용한 고속 감성 분석 및 추론 (OpenAI 호환 엔드포인트).

**4. 주요 기능 요구사항**

**4.1 뉴스 수집 및 전처리 (News Ingestion)**

* 약 5분 간격(10초 루프 × 30틱)으로 CryptoPanic API를 폴링하여 최신 뉴스를 수집한다.
* CryptoPanic v2 API가 고유 ID를 제공하지 않으므로, `hashlib.sha256(title:created_at)[:16]`을 사용하여 고유 ID를 생성하고 중복 수집을 방지한다.
* 수집된 뉴스는 즉시 DB에 저장되며, 분석 전 상태인 `PENDING`으로 표시된다.

**4.2 감성 분석 (Sentiment Analysis)**

* Groq API를 호출하여 뉴스 제목과 관련 코인을 바탕으로 감성 분석을 수행한다.
* 산출 지표: `sentiment_score`(-1.0~1.0), `sentiment_label`(bullish/bearish/neutral), `decision`(BUY/SELL/HOLD/WAIT), `confidence`(0~100), `reasoning_chain`, `keywords`, `positive_factors`, `negative_factors`.
* 응답 형식은 `json_object`를 사용하여 정형화된 데이터를 확보한다.

**4.3 시장 반응 확인 (Market Response Filter)**

* 본 파이프라인에서는 뉴스 텍스트 분석에 집중하며, 거래량 등 시장 데이터와의 결합은 미구현 상태임.
* 실제 시장 반응 및 기술적 지표는 별도의 매매 엔진(`engine.py`)에서 처리된다.

**4.4 AI 논리 검토 (AI Reasoning)**

* Groq 클라우드 API의 Llama 3.1 8B 모델을 사용하며, `temperature=0.2`, `max_completion_tokens=1024` 설정을 통해 일관된 분석 결과를 도출한다.
* 분석 결과는 단계별 추론 과정(`reasoning_chain`)을 포함하여 사용자에게 분석 근거를 제공한다.

**5. 매매 판단 로직**

* **인사이트 제공 중심:** 감성 분석 결과는 `sentiment_insights` 테이블에 저장되어 React 대시보드에 실시간으로 표시된다.
* **매매 분리:** 실제 매매 판단은 별도의 기술지표 엔진(`engine.py`)이 BB, RSI, ATR, ADX 등을 기반으로 수행하며, 감성 분석 결과가 매매 신호에 직접적으로 반영되지 않는다.
* **2-Phase 파이프라인:**
    1. **Phase 1 (수집):** 뉴스 수집 즉시 `decision='PENDING'`으로 DB에 저장하여 대시보드에 "AI 분석 중" 상태를 노출한다.
    2. **Phase 2 (분석):** Groq API 분석 완료 후 결과를 DB에 `UPDATE`하며, Supabase Realtime을 통해 대시보드에 즉시 반영한다.

**6. 시스템 아키텍처 및 흐름도**

1. **Data Layer:** CryptoPanic API (뉴스 텍스트 수집)
2. **Analysis Layer:** Groq API (Llama 3.1 8B 기반 감성 분석 및 추론)
3. **Storage Layer:** Supabase (`sentiment_insights` 테이블 저장 및 관리)
4. **Presentation Layer:** React 대시보드 (Supabase Realtime 구독을 통한 실시간 표시)

* 매매 실행 시스템(pyupbit 기반)은 본 인사이트 파이프라인과 독립적으로 운영된다.

**7. 예외 처리 및 리스크 관리**

* **Rate Limit 대응:** Groq 무료 티어 및 CryptoPanic API의 호출 제한을 준수하기 위해 `time.sleep` 및 폴링 간격 조절을 통한 방어 로직을 적용한다.
* **네트워크 오류:** API 호출 실패 시 Exponential Backoff 전략을 사용하여 재시도하며, 지속적인 실패 시 로그를 기록한다.
* **데이터 정리:** 시스템 부하 방지를 위해 7일 이상 경과한 오래된 인사이트 데이터는 자동으로 삭제(`cleanup_old_sentiment_insights`)한다.
