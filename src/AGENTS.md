# Backend (Python) 가이드라인

> 상위 `/AGENTS.md`의 6가지 원칙을 따릅니다.

## 기술 스택
- Python 3.10+, **완전 동기** (async/await 절대 금지)
- 의존성: `pyupbit`, `pandas`, `numpy`, `ta`, `supabase`, `httpx`

---

## 모듈 구조 + 데이터 흐름

오케스트레이터가 호출하는 순서:
```
collector/ → strategy/ → executor/ → storage/ → notifier/
+ risk/ (횡단), report/ (일일), backtest/ (오프라인)
```

### 각 모듈 역할
- `collector/data_collector.py`: Upbit API 시세/호가 수집 + rate limiting
- `strategy/engine.py`: 평균 회귀 신호 생성 + 상태 복구
- `strategy/indicators.py`: 기술 지표 계산 (BB, RSI, ATR)
- `executor/order_executor.py`: 주문 집행 + 타임아웃 + 쿨다운
- `risk/manager.py`: 포지션 사이징 + 일일 손실 한도
- `storage/client.py`: Supabase CRUD + 에러 차폐
- `notifier/kakao.py`: 카카오톡 알림 (동기 HTTP)
- `report/generator.py`: 일일 리포트 마크다운 생성
- `orchestrator.py`: 중앙 조율자 — 메인 루프, 모듈 초기화, 에러 복구

### 운영 스크립트
- `scripts/kakao_auth.py`, `scripts/preflight_check.py`, `scripts/watchdog.py`

---

## 필수 패턴

### 설정
`@dataclass(frozen=True)` for ALL config classes (참조: `config.py`)
```python
@dataclass(frozen=True)
class StrategyParams:
    bb_window: int = 20
```

### 에러 핸들링
모든 DB 호출은 try/except로 래핑 — DB 장애가 봇을 죽이면 안 됨 (참조: `storage/client.py`)
```python
try:
    result = self._supabase.table('trades').insert(data).execute()
except Exception as e:
    logger.exception('DB insert 실패: %s', e)
```

### 알림 안전
`_safe_notify()` 패턴 — 알림 실패가 메인 루프를 죽이면 안 됨 (참조: `orchestrator.py`)

### 복구 전략
exponential backoff — `min(interval * 2^consecutive_errors, 300s)` (참조: `orchestrator.py`)

### 핫 리로드
`_reload_strategy_params()` — `bot_state` 테이블에서 ~1분 간격 poll (참조: `orchestrator.py`)

### 로깅
- `logger = logging.getLogger(__name__)` 표준 사용
- 레벨 가이드:
  - `critical`: 초기화 실패, 일일 손실 한도 도달
  - `error`: API 장애, 예상 외 로직 오류
  - `warning`: 일시적 네트워크 문제, 알림 실패
  - `info`: 상태 변경 (주문 체결, 일일 리셋)
  - `debug`: 고빈도 노이즈 (틱 스킵, 지표 상세)
- 로그 메시지에 컨텍스트 포함: `[매수 진입] {symbol} | 사유: {reason}`

### 임포트 순서
1. `from __future__ import annotations` + `TYPE_CHECKING`
2. 표준 라이브러리 (`logging`, `time`, `datetime`)
3. 서드파티 (`pyupbit`, `pandas`, `supabase`)
4. 로컬 모듈 (`from src.config import ...`)

### 네이밍
- 클래스: PascalCase (`OrderExecutor`)
- 함수/변수: snake_case (`fetch_ticker`)
- 상수: UPPER_SNAKE_CASE (`_SNAPSHOT_INTERVAL`)
- private: 단일 언더스코어 (`self._config`, `self._execute_buy()`)

### Supabase 패턴
- `upsert`: 단일 행 상태성 데이터 (`bot_state`, `kakao_tokens`)
- `insert`: 시계열/이벤트 데이터 (`trades`, `balance_snapshots`, `system_logs`)
- `cleanup`: 7일 이상 오래된 스냅샷 자동 삭제

---

## 금지 사항
- ❌ `async/await`, `asyncio`, FastAPI 도입 금지 — 완전 동기 아키텍처
- ❌ 새 외부 패키지 추가 시 반드시 `requirements.txt` 업데이트
- ❌ `orchestrator.py`의 메인 루프 구조 변경 시 각별히 주의 (단일 장애점)
- ❌ rate limiting 제거/완화 금지 (거래소 API 차단 위험)
