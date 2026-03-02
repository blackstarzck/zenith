# Plan: PRD 감성 분석 문서 실제 구현 동기화

> **생성일**: 2026-03-02
> **상태**: ready
> **예상 작업량**: TODO 2개 (Wave 1 병렬 실행)

---

## 배경

`docs/PRD-Crypto-Sentiment-Insight.md`가 실제 구현과 심각하게 괴리됨:
- **PRD**: 4-서비스 파이프라인 (CryptoPanic + Alpha Vantage + DeFiLlama + Ollama/Llama 3) → 감성 기반 자동 매매
- **실제**: 2-서비스 파이프라인 (CryptoPanic + Groq/Llama 3.1 8B) → 대시보드 인사이트 표시용

### 핵심 괴리 (Metis 분석)
1. Alpha Vantage, DeFiLlama — 코드베이스 참조 **0건**, 미구현
2. Ollama(로컬 AI) → Groq(클라우드 API)로 대체됨
3. CCXT → pyupbit 사용 중
4. **감성 분석이 매매 판단에 반영되지 않음** — `engine.py`에 sentiment 참조 0건. 대시보드 정보 표시용
5. SQL 주석에 "Gemini 2.0 Flash Lite" 잔존

### 사용자 결정 사항
- PRD를 **현실 반영**으로 수정 (미래 계획 없이 현재 구현 상태만 서술)
- SQL 주석도 **함께 수정**

---

## Source-of-Truth 파일 (참조 필수)

| 파일 | 역할 |
|------|------|
| `src/strategy/sentiment.py` | Groq API 엔드포인트, 모델명, 프롬프트, 응답 포맷 |
| `src/collector/news_collector.py` | CryptoPanic v2 API, SHA256 ID 생성, regions=ko |
| `src/config.py` → `SentimentConfig` | groq_model, poll_interval_ticks=30, target_currencies, api_timeout_sec=30, max_news_per_poll=10 |
| `src/orchestrator.py` → `_run_sentiment_cycle()` | 2-phase: PENDING 저장 → Groq 분석 → UPDATE |
| `src/storage/client.py` | insert_sentiment_insight, update_sentiment_insight, cleanup_old_sentiment_insights |

---

## Wave 1 — 병렬 실행 (의존성 없음)

### TODO 1: PRD-Crypto-Sentiment-Insight.md 전면 리라이트

- **파일**: `docs/PRD-Crypto-Sentiment-Insight.md`
- **카테고리**: `writing`
- **스킬**: `[]`

#### 핵심 원칙
- **현실만 서술** — 미래 계획, 로드맵, "향후 연동 예정" 등 금지
- **한국어로 작성** (프로젝트 컨벤션)
- 기존 7섹션 구조는 유지하되, 내용은 전면 교체

#### 섹션별 리라이트 가이드

| 섹션 | 변경 수준 | 핵심 변경 내용 |
|------|-----------|---------------|
| **§1 개요** | 경미 수정 | "교차 검증을 통해 매매 신뢰도 극대화" → "뉴스 감성 분석 인사이트를 대시보드에 제공". 핵심 목적이 정보 제공임을 명시 |
| **§2 문제 정의 및 목표** | 전면 리라이트 | "무료 API(Alpha Vantage, DeFiLlama)와 로컬 AI(Llama 3)" 전부 삭제. 목표를 "CryptoPanic 뉴스를 Groq AI(Llama 3.1 8B)로 감성 분석하여 대시보드에 실시간 인사이트 제공"으로 변경 |
| **§3 데이터 소스 및 API 구성** | 전면 리라이트 | 4개 소스 → 2개로 축소: (1) CryptoPanic Developer v2 — 한국어 뉴스 수집, (2) Groq API (Llama 3.1 8B) — 클라우드 기반 감성 분석. Alpha Vantage, DeFiLlama, Ollama 항목 완전 삭제 |
| **§4 주요 기능 요구사항** | 구조 재편 | §4.1 뉴스 수집: "1~5분 간격" → "약 5분 간격(10초 루프 × 30틱)", "한국어 및 영어" → "한국어(regions=ko)", CryptoPanic v2에서 id/url/source 미제공 → SHA256 해시로 고유 ID 생성 명시. §4.2 감성 분석: Alpha Vantage 내용 전부 삭제 → Groq 단일 호출로 sentiment_score(-1.0~1.0), decision(BUY/SELL/HOLD/WAIT), confidence, reasoning_chain, keywords, positive/negative_factors 산출. §4.3 시장 반응: 거래량 필터 미구현이므로 삭제 또는 "미구현 — 거래량 데이터는 기존 기술지표 엔진에서 별도 처리"로 명시. §4.4 AI 논리 검토: "로컬 Llama 3" → "Groq 클라우드 API (Llama 3.1 8B)", "제목과 요약 사이 모순 검증" → "뉴스 제목 기반 감성 분석 및 매수/매도/보류/대기 판정" |
| **§5 매매 판단 로직** | **근본적 리라이트** | ⚠️ 가장 중요한 변경. 현재 3단계 필터 캐스케이드(Alpha Vantage → 거래량 → Llama 3 → CCXT 주문)를 전면 삭제. 대신: "감성 분석 결과는 `sentiment_insights` 테이블에 저장되어 React 대시보드에 실시간 표시됨. **매매 판단은 별도의 기술지표 엔진(engine.py)이 BB/RSI/ATR/ADX 기반으로 수행하며, 감성 분석 결과가 매매 신호에 직접 반영되지 않음.**" CCXT 참조 삭제 (실제는 pyupbit 사용). 2-phase 파이프라인 설명: (1) CryptoPanic에서 뉴스 수집 → decision='PENDING'으로 DB 즉시 저장 → 프론트엔드에 "AI 분석 중" 표시, (2) Groq API로 감성 분석 → 결과로 DB UPDATE → 프론트엔드에 실시간 반영 |
| **§6 시스템 아키텍처 및 흐름도** | 전면 리라이트 | 3-layer 구조 삭제. 새 구조: (1) Data Layer: CryptoPanic(뉴스 텍스트), (2) Analysis Layer: Groq API(감성 분석), (3) Storage Layer: Supabase(sentiment_insights 테이블), (4) Presentation Layer: React 대시보드(Realtime 구독). 매매 실행은 이 파이프라인과 **분리된** 별도 시스템(engine.py + pyupbit)임을 명시 |
| **§7 예외 처리 및 리스크 관리** | 중간 수정 | "무료 플랜 Rate Limit" → Groq 무료 티어 제한(분당 요청 수) + CryptoPanic Developer v2 Rate Limit. "다수 출처 체크" 삭제 (단일 소스인 CryptoPanic만 사용). "CCXT" 참조 삭제. 네트워크 오류 시 `time.sleep(1.0)` 방어 + exponential backoff 언급 |

#### 삭제해야 할 용어 (grep 검증)
- `Alpha Vantage`, `DeFiLlama`, `Ollama`, `CCXT`, `로컬 AI`, `로컬.*Llama`, `로컬.*모델`

#### 추가해야 할 용어
- `Groq`, `Llama 3.1 8B`, `클라우드 API`, `대시보드`, `인사이트`, `PENDING`, `2-phase`

#### QA 시나리오 (실행 필수)
```bash
# QA-1: 제거 대상 용어가 남아있지 않은지 확인
grep -iE "alpha.?vantage|defillama|defi.?llama|ollama|ccxt" docs/PRD-Crypto-Sentiment-Insight.md
# 기대: 매치 없음 (exit code 1)

# QA-2: 새 서비스명이 존재하는지 확인
grep -iE "groq|cryptopanic" docs/PRD-Crypto-Sentiment-Insight.md
# 기대: 여러 매치

# QA-3: "로컬 AI" 참조 제거 확인
grep -E "로컬.*AI|로컬.*Llama|로컬.*모델" docs/PRD-Crypto-Sentiment-Insight.md
# 기대: 매치 없음 (exit code 1)

# QA-4: 대시보드/인사이트 역할 명시 확인
grep -c "대시보드\|인사이트\|정보\|표시" docs/PRD-Crypto-Sentiment-Insight.md
# 기대: 2개 이상 매치

# QA-5: 7개 섹션 구조 유지 확인
grep -c "^\*\*[0-9]\." docs/PRD-Crypto-Sentiment-Insight.md
# 기대: 7개

# QA-6: CCXT 참조 완전 삭제
grep -i "ccxt" docs/PRD-Crypto-Sentiment-Insight.md
# 기대: 매치 없음 (exit code 1)
```

---

### TODO 2: SQL 주석 수정 (Gemini → Groq)

- **파일**: `sql/supabase_add_sentiment_insights.sql`
- **카테고리**: `quick`
- **스킬**: `[]`

#### 변경 내용
- **Line 4**: `-- CryptoPanic 뉴스를 Gemini 2.0 Flash Lite로 감성 분석한` → `-- CryptoPanic 뉴스를 Groq (Llama 3.1 8B)로 감성 분석한`

#### QA 시나리오
```bash
# QA-1: Groq 참조 확인
grep "Groq" sql/supabase_add_sentiment_insights.sql
# 기대: 매치 있음

# QA-2: Gemini 참조 제거 확인
grep -i "gemini" sql/supabase_add_sentiment_insights.sql
# 기대: 매치 없음 (exit code 1)
```

---

## Final Verification Wave

```bash
# 전체 코드베이스에서 Gemini 잔존 참조 확인
grep -ri "gemini" docs/ sql/
# 기대: 매치 없음

# PRD 파일 최종 확인
cat docs/PRD-Crypto-Sentiment-Insight.md
# 기대: 전체 내용이 한국어, 7섹션, Groq/CryptoPanic 기반

# git diff로 변경 범위 확인
git diff --stat
# 기대: 2개 파일만 변경
```

---

## 제약 조건

- ✅ 모든 텍스트 한국어 (AGENTS.md 컨벤션)
- ❌ 미래 계획/로드맵 추가 금지 — 현재 구현 상태만 서술
- ❌ PRD 범위를 벗어나 기술지표 매매 전략(engine.py) 상세 기술 금지
- ❌ docs/ 내 다른 파일 수정 금지 (System-Architecture-Design.md는 이미 정확함)
- ❌ 소스코드 파일(.py, .tsx) 수정 금지
