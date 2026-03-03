# CryptoPanic Quota/Error 로그 분기 정교화

## TL;DR
> **Summary**: CryptoPanic 실패 로그를 quota 초과/인증 오류/기타 오류로 명확히 분기하고, 응답 `info` 원문을 운영 로그에 포함해 원인 식별 시간을 단축합니다.
> **Deliverables**:
> - `src/collector/news_collector.py` 오류 분기 개선
> - `tests/test_news_collector.py` 에러 응답 분기 테스트 추가
> - 동작 계약(`None`/`[]` 반환) 및 재시도 정책 유지 검증
> **Effort**: Short
> **Parallel**: YES - 2 waves
> **Critical Path**: T1 구현 → T2 테스트 보강 → T3 회귀 검증

## Context
### Original Request
- quota 초과 응답(`status: api_error`, `info: API monthly quota exceeded - upgrade your API plan`)을 일반 API 키 오류와 다르게 로그로 표현
- `info` 값을 그대로 로그에 노출

### Interview Summary
- 사용자 관측값(Postman) 기준으로 quota 초과시 `info` 메시지가 명시적으로 제공됨
- 현재 구현은 4xx를 단일 로그("API 키/파라미터")로 축약하여 원인 식별이 어려움

### Metis Review (gaps addressed)
- 비JSON/빈본문/HTML 본문에서도 예외 없이 동작하도록 방어 파싱 적용
- 기존 반환 계약(`_fetch_posts_json -> None`, `fetch_latest_news -> []`) 유지
- 재시도/백오프 정책(네트워크/429/5xx) 불변 유지

## Work Objectives
### Core Objective
- CryptoPanic 실패 원인을 운영 로그에서 즉시 구분 가능하게 만드는 것(quota vs 인증/키 vs 기타).

### Deliverables
- `src/collector/news_collector.py`에서 응답 바디 파싱 기반의 에러 분기 로깅
- `tests/test_news_collector.py`에 분기별 테스트(Quota/API키/비JSON/빈본문)
- 회귀 확인(기존 테스트 + 신규 테스트)

### Definition of Done (verifiable conditions with commands)
- `python -m pytest tests/test_news_collector.py -v` 통과
- `python -m pytest tests/test_sentiment_analyzer.py tests/test_news_collector.py tests/test_sentiment_verifier.py` 통과
- 로그 분기 테스트에서 quota/info 원문 포함 확인

### Must Have
- quota 케이스에서 `info` 원문 포함 로그 출력
- API 키 오류 케이스에서 별도 로그 문구 출력
- 예외 응답(비JSON/빈본문)에서도 크래시 없이 기존 반환 유지

### Must NOT Have (guardrails, AI slop patterns, scope boundaries)
- 오케스트레이터 동작/폴링 주기/fallback 정책 변경 금지
- DB 스키마/프론트엔드 타입/화면 변경 금지
- 신규 패키지 추가 금지

## Verification Strategy
> ZERO HUMAN INTERVENTION — all verification is agent-executed.
- Test decision: tests-after + `pytest`
- QA policy: 모든 TODO에 happy + failure 시나리오 포함
- Evidence: `.sisyphus/evidence/task-{N}-{slug}.{ext}`

## Execution Strategy
### Parallel Execution Waves
> Wave 1은 구현 기반 작업, Wave 2는 검증/회귀 작업으로 구성.

Wave 1: 오류 분기 구현, 테스트 케이스 추가
Wave 2: 회귀 검증, 로그 문구 및 가드레일 점검

### Dependency Matrix (full, all tasks)
- T1 blocks: T2, T3
- T2 blocks: T3
- T3 blocks: T4
- T4 blocks: Final Verification Wave

### Agent Dispatch Summary (wave → task count → categories)
- Wave 1 → 2 tasks → `quick`, `unspecified-low`
- Wave 2 → 2 tasks → `quick`, `unspecified-low`

## TODOs
> Implementation + Test = ONE task. Never separate.
> EVERY task MUST have: Agent Profile + Parallelization + QA Scenarios.

- [ ] 1. CryptoPanic 에러 분기 로깅 로직 정교화

  **What to do**: `src/collector/news_collector.py`의 `_fetch_posts_json`에서 `status < 200 or status >= 300` 분기를 확장해 (a) quota 초과, (b) 인증/키 오류, (c) 기타 오류를 구분 로그로 출력한다. 우선 `response.json()` 시도 후 실패 시 `response.text`를 fallback으로 사용하고, `info` 또는 `error` 필드가 있으면 그대로 로그 메시지에 포함한다.
  **Must NOT do**: 반환 타입/흐름(`None`) 변경 금지, 429/5xx 재시도 정책 변경 금지, v1 fallback 호출 조건 변경 금지.

  **Recommended Agent Profile**:
  - Category: `quick` — Reason: 단일 함수 중심의 국소 로직 수정
  - Skills: `[]` — 별도 스킬 불필요
  - Omitted: [`git-master`] — 커밋 작업 범위가 아님

  **Parallelization**: Can Parallel: NO | Wave 1 | Blocks: [2, 3] | Blocked By: []

  **References** (executor has NO interview context — be exhaustive):
  - Pattern: `src/collector/news_collector.py:81` — 429 전용 처리 및 backoff 패턴 유지 기준
  - Pattern: `src/collector/news_collector.py:109` — 기존 4xx 통합 처리 지점
  - Pattern: `src/notifier/kakao.py:126` — `status_code + resp.text` 로그 스타일
  - External: `docs/CryptoPanic_API_.postman_collection.json:15` — 현재 사용 중 v2 endpoint/쿼리 패턴

  **Acceptance Criteria** (agent-executable only):
  - [ ] `_fetch_posts_json`에서 quota 시나리오 로그에 `info` 원문 포함
  - [ ] 인증/키 오류 로그 문구가 quota 문구와 구분
  - [ ] 비JSON/빈본문 응답에서도 예외 없이 `None` 반환

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```
  Scenario: Quota 초과 응답 분기
    Tool: Bash
    Steps: python -m pytest tests/test_news_collector.py -k quota -v
    Expected: quota 관련 테스트가 pass하고 로그 assertion에 info 원문 포함
    Evidence: .sisyphus/evidence/task-1-cryptopanic-quota.txt

  Scenario: 비JSON 오류 응답 분기
    Tool: Bash
    Steps: python -m pytest tests/test_news_collector.py -k non_json -v
    Expected: 예외 없이 pass, 함수 반환 None 유지
    Evidence: .sisyphus/evidence/task-1-cryptopanic-non-json-error.txt
  ```

  **Commit**: NO | Message: `fix(collector): classify cryptopanic error logs` | Files: [`src/collector/news_collector.py`]

- [ ] 2. 뉴스 수집기 에러 분기 테스트 케이스 추가

  **What to do**: `tests/test_news_collector.py`에 `_fetch_posts_json` 단위 테스트를 추가해 quota/info, 인증 오류, 비JSON 본문, 빈본문 케이스를 검증한다. `httpx.Client`/Response mocking 패턴을 사용해 외부 네트워크 의존성을 제거한다.
  **Must NOT do**: 실제 CryptoPanic 네트워크 호출 테스트 작성 금지, flaky sleep 타이밍 의존 테스트 금지.

  **Recommended Agent Profile**:
  - Category: `unspecified-low` — Reason: 테스트 설계/목킹 중심 작업
  - Skills: `[]` — 별도 스킬 불필요
  - Omitted: [`playwright`] — 백엔드 단위 테스트 범위

  **Parallelization**: Can Parallel: NO | Wave 1 | Blocks: [3] | Blocked By: [1]

  **References** (executor has NO interview context — be exhaustive):
  - Test pattern: `tests/test_news_collector.py:14` — 기존 테스트 파일 구조 및 스타일
  - API contract: `src/collector/news_collector.py:53` — `_fetch_posts_json` 시그니처/반환 타입
  - Guardrail: `src/collector/news_collector.py:128` — 실패 시 None 반환 계약

  **Acceptance Criteria** (agent-executable only):
  - [ ] quota/info 분기 테스트 pass
  - [ ] API 키 오류 분기 테스트 pass
  - [ ] 비JSON/빈본문 안전 처리 테스트 pass

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```
  Scenario: 신규 분기 테스트 전체 실행
    Tool: Bash
    Steps: python -m pytest tests/test_news_collector.py -v
    Expected: 신규 + 기존 테스트 모두 pass
    Evidence: .sisyphus/evidence/task-2-news-collector-tests.txt

  Scenario: 회귀 실패 유도 확인
    Tool: Bash
    Steps: python -m pytest tests/test_news_collector.py -k "quota or auth" -v
    Expected: 핵심 분기 테스트가 독립 실행에서도 안정 pass
    Evidence: .sisyphus/evidence/task-2-news-collector-branch-tests.txt
  ```

  **Commit**: NO | Message: `test(collector): add cryptopanic error branch coverage` | Files: [`tests/test_news_collector.py`]

- [ ] 3. 감성 관련 회귀 테스트 및 부수효과 점검

  **What to do**: 감성 분석 관련 회귀 세트를 실행해 이번 변경이 `NewsCollector` 외 흐름에 영향을 주지 않았음을 확인한다.
  **Must NOT do**: 테스트 실패를 우회하기 위한 코드 완화/skip 처리 금지.

  **Recommended Agent Profile**:
  - Category: `quick` — Reason: 실행/검증 중심의 짧은 작업
  - Skills: `[]` — 별도 스킬 불필요
  - Omitted: [`git-master`] — 커밋 단계 아님

  **Parallelization**: Can Parallel: YES | Wave 2 | Blocks: [4] | Blocked By: [1, 2]

  **References** (executor has NO interview context — be exhaustive):
  - Test suite: `tests/test_sentiment_analyzer.py` — 감성 게이트/정규화 회귀
  - Test suite: `tests/test_news_collector.py` — 수집/통화 추론 + 신규 분기 회귀
  - Test suite: `tests/test_sentiment_verifier.py` — 사후 검증 로직 회귀

  **Acceptance Criteria** (agent-executable only):
  - [ ] 3개 감성 테스트 파일 전체 pass
  - [ ] 실패 시 로그 분기 변경 외 추가 사이드이펙트 없음 확인

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```
  Scenario: 감성 회귀 풀 스위트
    Tool: Bash
    Steps: python -m pytest tests/test_sentiment_analyzer.py tests/test_news_collector.py tests/test_sentiment_verifier.py -v
    Expected: 전체 pass, 실패 0
    Evidence: .sisyphus/evidence/task-3-sentiment-regression.txt

  Scenario: 최소 단위 재검증
    Tool: Bash
    Steps: python -m pytest tests/test_news_collector.py -v
    Expected: 뉴스 수집기 단위 테스트 단독 pass
    Evidence: .sisyphus/evidence/task-3-news-collector-regression.txt
  ```

  **Commit**: NO | Message: `test(sentiment): validate collector error-branch regression` | Files: [`tests/test_sentiment_analyzer.py`, `tests/test_news_collector.py`, `tests/test_sentiment_verifier.py`]

- [ ] 4. 로그 메시지 품질/운영 가독성 점검

  **What to do**: 새 로그 문구가 운영자가 즉시 판단 가능한 형태인지 검증한다(상태코드, 유형, info 원문, fallback 본문 요약 포함 여부). 메시지는 한국어 기반 + 원문 병기로 통일한다.
  **Must NOT do**: 민감정보(auth_token 등) 로그 노출 금지.

  **Recommended Agent Profile**:
  - Category: `unspecified-low` — Reason: 로그 품질 규칙 검증 중심
  - Skills: `[]` — 별도 스킬 불필요
  - Omitted: [`playwright`] — UI 범위 아님

  **Parallelization**: Can Parallel: YES | Wave 2 | Blocks: [F1, F4] | Blocked By: [3]

  **References** (executor has NO interview context — be exhaustive):
  - Logging rule: `AGENTS.md` — 한국어 로그/컨텍스트 포함 원칙
  - Logging pattern: `src/notifier/kakao.py:126` — 상태코드+본문 병기
  - Target module: `src/collector/news_collector.py:53` — CryptoPanic 요청/응답 로깅 맥락

  **Acceptance Criteria** (agent-executable only):
  - [ ] quota 로그가 `info` 원문을 포함
  - [ ] 인증 오류 로그가 quota 로그와 명확히 구분
  - [ ] 비JSON/빈본문 로그가 traceback 없이 안전 출력

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```
  Scenario: 로그 문자열 assertion 검증
    Tool: Bash
    Steps: python -m pytest tests/test_news_collector.py -k "log or quota or auth" -v
    Expected: 메시지 assertion pass, 민감정보 노출 없음
    Evidence: .sisyphus/evidence/task-4-log-quality-assertions.txt

  Scenario: 예외 응답 메시지 검증
    Tool: Bash
    Steps: python -m pytest tests/test_news_collector.py -k "non_json or empty" -v
    Expected: 파싱 실패로 인한 크래시 없음, fallback 메시지 출력
    Evidence: .sisyphus/evidence/task-4-log-fallback.txt
  ```

  **Commit**: NO | Message: `chore(logging): improve cryptopanic error observability` | Files: [`src/collector/news_collector.py`, `tests/test_news_collector.py`]

## Final Verification Wave (4 parallel agents, ALL must APPROVE)
- [ ] F1. Plan Compliance Audit — oracle
- [ ] F2. Code Quality Review — unspecified-high
- [ ] F3. Real Manual QA — unspecified-high (+ playwright if UI)
- [ ] F4. Scope Fidelity Check — deep

## Commit Strategy
- 단일 커밋 권장: `fix(sentiment): distinguish cryptopanic quota vs auth errors in logs`
- 포함 파일: `src/collector/news_collector.py`, `tests/test_news_collector.py`

## Success Criteria
- 운영 로그에서 quota 초과와 API 키 오류를 즉시 구분 가능
- `info` 원문 로그 포함으로 원인 재현/대응 시간 단축
- 기존 수집 흐름/반환 계약/재시도 정책 무손상
