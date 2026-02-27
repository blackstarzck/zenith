# 시장 레짐(Regime) 감지기 도입

## 목표
BTC-KRW를 시장 대표로 사용하여 시장 레짐(trending/ranging/volatile)을 분류하고, orchestrator에서 상위 필터로 매매 진입을 제어한다. 레짐 상태는 bot_state에 저장하여 프론트엔드 대시보드에 실시간 표시한다.

## 핵심 설계 결정 (확정)

| 항목 | 결정 |
|------|------|
| 레짐 범위 | **시장 전체** (BTC-KRW 대표) |
| 레짐 종류 | **3개**: `trending`, `ranging`, `volatile` |
| 기존 게이트와의 관계 | **레이어 추가** — engine.py의 기존 3개 게이트(ADX, vol, MA)는 그대로 유지. 레짐은 orchestrator에서 상위 필터로 추가 |
| 추세장 행동 | 신규 진입 차단 + 기존 포지션은 청산 조건까지 유지 |
| 변동성폭발 행동 | 기존 MARKET_PAUSE와 동일 — 신규 진입 차단 |
| 횡보장 행동 | 정상 매매 (평균 회귀 최적 구간) |
| 프론트엔드 | bot_state.market_regime 필드에 저장 → 대시보드 Tag 뱃지로 표시 |
| 히스테리시스 | 캔들 룩백 기반 (최근 N개 캔들의 다수결) — stateless, 재시작 안전 |

## 아키텍처 개요

```
orchestrator._tick()
  ├── _update_market_regime()     ← [NEW] BTC OHLCV → 레짐 분류
  │     ├── collector.get_ohlcv("KRW-BTC")
  │     ├── regime.classify_regime(df, params) → "trending" | "ranging" | "volatile"
  │     └── storage.upsert_bot_state(market_regime=regime)
  ├── _evaluate_exits()           ← 변경 없음
  └── _evaluate_entries()         ← 레짐이 "trending" 또는 "volatile"이면 진입 건너뜀
```

## 범위

### IN (구현 대상)
- `src/strategy/regime.py` — 레짐 분류 모듈 (신규)
- `src/config.py` — StrategyParams에 레짐 관련 파라미터 추가
- `src/orchestrator.py` — 레짐 감지 호출 + 진입 필터링
- `src/storage/client.py` — upsert_bot_state에 market_regime 파라미터 추가
- `supabase_add_market_regime.sql` — bot_state 테이블 컬럼 추가 마이그레이션
- `frontend/src/types/database.ts` — BotState에 market_regime 필드 추가
- `frontend/src/pages/DashboardPage.tsx` — 레짐 뱃지 표시
- `docs/Algorithm_Specification.md` — 레짐 감지기 문서화
- `docs/System-Architecture-Design.md` — 신규 모듈 추가 문서화
- `docs/Data_Model_ERD.md` — bot_state 스키마 변경 문서화

### OUT (범위 밖)
- 레짐 기반 포지션 사이징 조절 (켈리 공식 — 별도 플랜)
- 레짐 히스토리 테이블 (별도 기록/차트 없음)
- 레짐 기반 알림/카카오톡 통보
- 청산 로직 변경 (레짐이 바뀌어도 기존 포지션 청산 로직은 불변)
- 백테스트에 레짐 감지기 통합
- 레짐 시각화 차트 (뱃지 표시만)

## 참조 파일 (읽기 전용 — 패턴 참고)

| 파일 | 참고 이유 |
|------|-----------|
| `src/strategy/indicators.py` | 지표 함수 시그니처 패턴, compute_snapshot() 구조 |
| `src/strategy/engine.py:84-111` | 기존 ADX/vol/MA 게이트 로직 (중복 회피 확인) |
| `src/orchestrator.py:156-220` | _tick() 구조, 에러 차폐 패턴, bot_state 갱신 패턴 |
| `src/config.py:36-96` | StrategyParams frozen dataclass 패턴, from_dict() |
| `src/storage/client.py:188-232` | upsert_bot_state() kwargs 패턴 |
| `frontend/src/types/database.ts:43-55` | BotState 인터페이스 |
| `frontend/src/hooks/useSupabase.ts:131-169` | useBotState() 훅 — realtime 자동 수신 확인 |
| `frontend/src/pages/DashboardPage.tsx:663-681` | 대시보드 헤더 영역 (레짐 뱃지 삽입 위치) |

## 구현 태스크

<!-- TASKS_START -->

### TODO-01: `src/strategy/regime.py` 신규 모듈 생성

**목적**: BTC-KRW의 OHLCV 데이터를 받아 시장 레짐을 분류하는 순수 함수 모듈

**생성할 파일**: `src/strategy/regime.py`

**구현 상세**:

```python
"""
시장 레짐(Regime) 감지 모듈.
BTC-KRW를 시장 대표 지표로 사용하여 현재 시장이
추세장(trending), 횡보장(ranging), 변동성 폭발(volatile) 중
어느 상태인지 분류합니다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum

import pandas as pd

from src.strategy.indicators import calc_adx, calc_volatility_ratio, calc_ma_trend

logger = logging.getLogger(__name__)


class MarketRegime(Enum):
    """시장 레짐 유형."""
    TRENDING = "trending"      # 강한 추세 — 평균 회귀 부적합
    RANGING = "ranging"        # 횡보 — 평균 회귀 최적
    VOLATILE = "volatile"      # 변동성 폭발 — 매매 중단


@dataclass(frozen=True)
class RegimeResult:
    """레짐 분류 결과."""
    regime: MarketRegime
    adx: float
    volatility_ratio: float
    ma_trend: bool | None  # True=상승, False=하락, None=데이터 부족
    reason: str


def classify_regime(
    df: pd.DataFrame,
    adx_trending_threshold: float = 25.0,
    vol_overload_ratio: float = 2.0,
    adx_period: int = 14,
    vol_short_window: int = 16,
    vol_long_window: int = 192,
    ma_short_period: int = 20,
    ma_long_period: int = 50,
    lookback_candles: int = 3,
) -> RegimeResult:
    """OHLCV DataFrame으로부터 시장 레짐을 분류합니다.

    분류 우선순위:
    1. volatile: 변동성 비율 >= vol_overload_ratio
    2. trending: ADX >= adx_trending_threshold
    3. ranging: 위 조건 미충족

    히스테리시스: lookback_candles 개수만큼 과거 캔들에서도 분류하여
    다수결로 최종 레짐을 결정합니다 (잦은 전환 방지).

    Args:
        df: BTC-KRW의 OHLCV DataFrame (open, high, low, close, volume)
        adx_trending_threshold: ADX가 이 값 이상이면 추세장
        vol_overload_ratio: 변동성 비율이 이 값 이상이면 변동성 폭발
        adx_period: ADX 계산 기간
        vol_short_window: 변동성 단기 윈도우
        vol_long_window: 변동성 장기 윈도우
        ma_short_period: MA 단기 기간
        ma_long_period: MA 장기 기간
        lookback_candles: 히스테리시스 룩백 캔들 수

    Returns:
        RegimeResult
    """
```

**히스테리시스 로직**:
- `lookback_candles` (기본값 3) 개의 과거 시점에서 각각 레짐을 분류
- 현재 시점 포함 총 `lookback_candles + 1`개의 레짐 판단
- 다수결로 최종 레짐 결정 (동점 시 현재 시점 우선)
- 이 방식은 캔들 데이터에서 직접 계산하므로 **stateless** — 봇 재시작에도 안전

**분류 로직 (우선순위 순)**:
1. `vol_ratio >= vol_overload_ratio` → `VOLATILE`
2. `adx >= adx_trending_threshold` → `TRENDING`
3. 그 외 → `RANGING`

**임포트 순서**: `from __future__ import annotations` → `logging` → `dataclasses, enum` → `pandas` → `src.strategy.indicators`

**로깅**: `logger = logging.getLogger(__name__)`, 레짐 변경 시 `logger.info("시장 레짐 변경: %s → %s | 사유: %s")` — 한국어

**금지사항**:
- async/await 사용 금지
- orchestrator.py 임포트 금지 (역방향 의존성)
- 인메모리 타이머/상태 사용 금지 (stateless 필수)

**QA**:
```bash
python -c "from src.strategy.regime import MarketRegime, classify_regime, RegimeResult; print('OK')"
# Assert: "OK"
```

---

### TODO-02: `src/config.py` — StrategyParams에 레짐 파라미터 추가

**목적**: 레짐 감지기의 임계값을 핫리로드 가능한 설정으로 관리

**수정할 파일**: `src/config.py`

**수정 위치**: `StrategyParams` 클래스 (line 37~96)

**추가할 필드** (기존 필드 아래에 섹션 추가):
```python
    # 시장 레짐 감지기
    regime_adx_trending_threshold: float = 25.0  # ADX ≥ 이 값이면 추세장
    regime_vol_overload_ratio: float = 2.0       # 변동성 비율 ≥ 이 값이면 변동성 폭발
    regime_lookback_candles: int = 3             # 히스테리시스 룩백 (다수결 캔들 수)
```

**중요 결정**: 기존 `adx_trend_threshold` (25.0)와 `volatility_overload_ratio` (2.0)와 **별도 필드**로 추가. 이유:
- 기존 필드는 engine.py의 종목별 게이트용
- 새 필드는 BTC 대표 시장 레짐용
- 초기에는 같은 기본값이지만, 독립적으로 조정 가능해야 함
- Metis 지시: "기존 threshold 이름을 다른 의미로 재사용하지 말 것"

**기본값 설계**: 기존 값과 동일하게 시작 → 기존 동작에 영향 없음 (backward compatible)

**from_dict() 호환**: `from_dict()`에서 `valid_names` 자동 감지되므로 추가 수정 불필요. `frozen=True`도 유지.

**QA**:
```bash
python -c "from src.config import StrategyParams; p = StrategyParams(); print(p.regime_adx_trending_threshold, p.regime_vol_overload_ratio, p.regime_lookback_candles)"
# Assert: "25.0 2.0 3"

# 기존 기본값 불변 확인
python -c "from src.config import StrategyParams; p = StrategyParams(); print(p.adx_trend_threshold, p.volatility_overload_ratio)"
# Assert: "25.0 2.0"
```

---

### TODO-03: `supabase_add_market_regime.sql` — DB 마이그레이션

**목적**: bot_state 테이블에 market_regime 컬럼 추가

**생성할 파일**: `supabase_add_market_regime.sql` (프로젝트 루트)

**내용**:
```sql
-- bot_state 테이블에 시장 레짐 필드 추가
-- 값: 'trending' | 'ranging' | 'volatile'
ALTER TABLE bot_state
ADD COLUMN IF NOT EXISTS market_regime TEXT DEFAULT 'ranging';

COMMENT ON COLUMN bot_state.market_regime IS '시장 레짐 상태 (trending/ranging/volatile)';
```

**DEFAULT 'ranging' 이유**: 봇이 레짐을 아직 계산하지 않았을 때 기본값은 "횡보장" → 정상 매매 허용 (가장 안전한 기본 동작)

**QA**:
```bash
# 파일 존재 확인
ls supabase_add_market_regime.sql
# Assert: 파일 존재

# market_regime 포함 확인
grep -c "market_regime" supabase_add_market_regime.sql
# Assert: >= 1
```

---

### TODO-04: `src/storage/client.py` — upsert_bot_state에 market_regime 파라미터 추가

**목적**: Python 백엔드에서 레짐 상태를 DB에 저장

**수정할 파일**: `src/storage/client.py`

**수정 위치**: `upsert_bot_state()` 메서드 (line 188~232)

**변경 내용**:
1. 함수 시그니처에 `market_regime: str | None = None` 파라미터 추가 (기존 kwargs 패턴 따름)
2. body에 조건부 row 추가:
```python
        if market_regime is not None:
            row["market_regime"] = market_regime
```

**삽입 위치**: 기존 `strategy_params` 블록 바로 아래 (line 225-226 이후)

**QA**:
```bash
python -c "
import inspect
from src.storage.client import StorageClient
sig = inspect.signature(StorageClient.upsert_bot_state)
print('market_regime' in sig.parameters)
"
# Assert: "True"
```

---

### TODO-05: `src/orchestrator.py` — 레짐 감지 통합

**목적**: 메인 루프에서 레짐을 주기적으로 판단하고, 진입 평가 시 필터링

**수정할 파일**: `src/orchestrator.py`

**변경 1 — 임포트 추가** (line 16 부근):
```python
from src.strategy.regime import classify_regime, MarketRegime
```

**변경 2 — `__init__`에 레짐 상태 필드 추가** (line 57 부근):
```python
        self._current_regime: str = "ranging"  # 현재 시장 레짐
```

**변경 3 — `_tick()`에 레짐 감지 호출 추가** (line 164, `_evaluate_exits()` 호출 전):
```python
        # 1.5. 시장 레짐 감지 (10분마다, 종목 목록 갱신과 동일 주기)
        if self._loop_count % 60 == 1:
            self._update_market_regime()
```

**위치 중요**: `_evaluate_exits()` 전에 호출. 이유: 레짐은 청산에 영향 안 줌 (설계 결정), 하지만 진입 전에 최신 레짐이 반영되어야 함

**변경 4 — `_update_market_regime()` 신규 메서드**:
```python
    def _update_market_regime(self) -> None:
        """BTC-KRW 데이터로 시장 레짐을 판단하고 bot_state에 저장합니다."""
        try:
            df = self._collector.get_ohlcv(
                "KRW-BTC",
                interval=self._config.candle_interval,
                count=self._config.candle_count,
            )
            if df.empty:
                logger.warning("BTC-KRW OHLCV 데이터 없음 — 레짐 판단 건너뜀")
                return

            params = self._config.strategy
            result = classify_regime(
                df,
                adx_trending_threshold=params.regime_adx_trending_threshold,
                vol_overload_ratio=params.regime_vol_overload_ratio,
                adx_period=params.adx_period,
                vol_short_window=params.vol_short_window,
                vol_long_window=params.vol_long_window,
                ma_short_period=params.ma_short_period,
                ma_long_period=params.ma_long_period,
                lookback_candles=params.regime_lookback_candles,
            )

            new_regime = result.regime.value
            if new_regime != self._current_regime:
                logger.info(
                    "[레짐 변경] %s → %s | ADX=%.1f, Vol=%.2f | 사유: %s",
                    self._current_regime, new_regime,
                    result.adx, result.volatility_ratio, result.reason,
                )
                self._current_regime = new_regime

            self._storage.upsert_bot_state(market_regime=self._current_regime)

        except Exception:
            logger.warning("시장 레짐 판단 실패 — 기존 레짐 유지 (%s)", self._current_regime)
```

**변경 5 — `_evaluate_entries()`에 레짐 필터 추가** (line 272, for 루프 진입 전):
```python
        # 레짐 기반 진입 필터 (trending/volatile → 신규 진입 차단)
        if self._current_regime in ("trending", "volatile"):
            if self._loop_count % 60 == 1:  # 10분에 1번만 로그
                logger.info(
                    "[진입 차단] 시장 레짐 '%s' — 신규 진입 대기 중",
                    self._current_regime,
                )
            return
```

**삽입 위치**: `_evaluate_entries()` 메서드의 잔고 조회 **전**에 추가. 이유: 불필요한 API 호출 방지

**BTC 캔들 API 중복 호출 방지**: BTC-KRW가 `_target_symbols`에 이미 포함되어 있을 수 있지만, 레짐 판단은 10분마다만 호출 (`_loop_count % 60 == 1`)하므로 추가 API 부하 무시 가능. `time.sleep(0.2)` 후 호출.

**에러 차폐**: `try/except`로 감싸서 레짐 판단 실패가 봇을 죽이지 않도록 함 (기존 orchestrator 에러 차폐 패턴 준수)

**QA**:
```bash
# 임포트 확인
python -c "from src.orchestrator import Orchestrator; print('OK')"
# Assert: "OK"

# 레짐 관련 메서드 존재 확인
python -c "
from src.orchestrator import Orchestrator
print(hasattr(Orchestrator, '_update_market_regime'))
"
# Assert: "True"
```

---

### TODO-06: `frontend/src/types/database.ts` — BotState에 market_regime 추가

**목적**: TypeScript 타입에 새 필드 반영

**수정할 파일**: `frontend/src/types/database.ts`

**수정 위치**: `BotState` 인터페이스 (line 43~55)

**추가할 필드** (line 54, `updated_at` 바로 위에):
```typescript
  market_regime: 'trending' | 'ranging' | 'volatile' | null;
```

**`null` 허용 이유**: 마이그레이션 전 또는 봇이 아직 첫 레짐 계산을 하지 않은 경우

**QA**:
```bash
grep -c "market_regime" frontend/src/types/database.ts
# Assert: >= 1
```

---

### TODO-07: `frontend/src/pages/DashboardPage.tsx` — 레짐 뱃지 표시

**목적**: 대시보드 헤더에 현재 시장 레짐을 Tag 뱃지로 표시

**수정할 파일**: `frontend/src/pages/DashboardPage.tsx`

**삽입 위치**: Dashboard 헤더 영역 (line 666~681), `displayPreset` Tag 옆에 추가

**구현 상세**:

먼저 레짐 → 표시 정보 매핑 상수를 모듈 레벨에 추가 (line 40 부근, 색상 상수 아래):
```typescript
/* ── 시장 레짐 표시 매핑 ──────────────────────────────── */
const REGIME_DISPLAY: Record<string, { label: string; color: string }> = {
  ranging: { label: '횡보장', color: 'green' },
  trending: { label: '추세장', color: 'orange' },
  volatile: { label: '변동성 폭발', color: 'red' },
};
```

그 다음 JSX에서 botState?.market_regime을 읽어 Tag 표시:
```tsx
{botState?.market_regime && REGIME_DISPLAY[botState.market_regime] && (
  <Tooltip destroyOnHidden title="BTC 기준 시장 상태 (10분 간격 갱신)">
    <Tag color={REGIME_DISPLAY[botState.market_regime].color} style={{ margin: 0 }}>
      {REGIME_DISPLAY[botState.market_regime].label}
    </Tag>
  </Tooltip>
)}
```

**삽입 위치**: 기존 `displayPreset` Tag 바로 뒤 (line 672~673 이후)

**스타일 규칙**:
- 인라인 style 사용 (프로젝트 컨벤션)
- AntD `Tag` + `Tooltip` 컴포넌트 사용
- `Tooltip`에 `destroyOnHidden` prop 사용 (DashboardPage의 기존 Tooltip 패턴과 동일)
- 다크 테마에서 가독성 확인: AntD Tag의 기본 색상은 다크 테마 호환
- `null` 또는 미인식 값일 때 아무것도 표시하지 않음 (graceful handling)

**AntD 문서 확인 필수**: 구현 전 `context7_query-docs`로 AntD v6의 `Tag` 컴포넌트 API 확인. `color` prop이 여전히 유효한지 검증.

**QA**:
```bash
# TypeScript 컴파일 확인
npx tsc --noEmit --project frontend/tsconfig.app.json
# Assert: exit code 0

# ESLint 확인
npx eslint frontend/src/ --ext .ts,.tsx
# Assert: no errors
```

---

### TODO-08: 문서 업데이트

**목적**: 변경된 아키텍처와 알고리즘을 문서에 반영

**수정할 파일 3개**:

#### 8-1. `docs/Algorithm_Specification.md`
기존 "1단계: 시장 필터링" 섹션 (line 11~14) 뒤에 레짐 감지기 섹션 추가:

```markdown
### 0단계: 시장 레짐 감지 (상위 필터)

모든 진입 판단에 앞서, BTC-KRW 데이터를 기반으로 시장의 현재 성격을 분류합니다.

* **횡보장 (Ranging):** ADX < 25이고 변동성 비율 < 2.0일 때. 평균 회귀 전략이 가장 잘 작동하는 구간으로, 정상적으로 매매를 진행합니다.
* **추세장 (Trending):** ADX ≥ 25일 때. 강한 추세에서는 평균 회귀가 역효과를 낼 수 있으므로 신규 진입을 차단하고, 기존 보유 종목은 기존 청산 조건에 따라 관리합니다.
* **변동성 폭발 (Volatile):** 변동성 비율 ≥ 2.0일 때. 시장이 비정상적으로 혼란스러운 상태이므로 매매를 일시 중단합니다.
* **히스테리시스:** 최근 3개 캔들의 다수결로 레짐을 확정하여, 캔들 하나의 노이즈로 잦은 레짐 전환이 발생하지 않도록 합니다.
```

#### 8-2. `docs/System-Architecture-Design.md`
모듈 목록에 `src/strategy/regime.py` 추가 (기존 모듈 목록 섹션에):
```markdown
- `strategy/regime.py`: BTC 기반 시장 레짐 감지 (trending/ranging/volatile)
```

데이터 흐름에 레짐 감지 추가:
```markdown
collector/ → **regime(BTC)** → strategy/ → executor/ → storage/ → notifier/
```

#### 8-3. `docs/Data_Model_ERD.md`
bot_state 테이블 설명에 market_regime 컬럼 추가:
```markdown
| market_regime | TEXT | 'ranging' | 시장 레짐 상태 (trending/ranging/volatile) |
```

**QA**: 각 문서 파일에 새 내용이 포함되었는지 grep 확인

---

<!-- TASKS_END -->

## Final Verification Wave

모든 태스크 완료 후 아래 검증을 순서대로 실행:

```bash
# 1. 모듈 임포트 정상 확인
python -c "from src.strategy.regime import MarketRegime, classify_regime, RegimeResult; print('OK')"

# 2. config 기본값 불변 + 새 필드 확인
python -c "
from src.config import StrategyParams
p = StrategyParams()
assert p.adx_trend_threshold == 25.0, 'adx_trend_threshold 기본값 변경됨!'
assert p.volatility_overload_ratio == 2.0, 'volatility_overload_ratio 기본값 변경됨!'
assert p.regime_adx_trending_threshold == 25.0
assert p.regime_vol_overload_ratio == 2.0
assert p.regime_lookback_candles == 3
print('Config OK')
"

# 3. storage client 파라미터 확인
python -c "
import inspect
from src.storage.client import StorageClient
sig = inspect.signature(StorageClient.upsert_bot_state)
assert 'market_regime' in sig.parameters
print('Storage OK')
"

# 4. orchestrator 임포트 + 메서드 확인
python -c "
from src.orchestrator import Orchestrator
assert hasattr(Orchestrator, '_update_market_regime')
print('Orchestrator OK')
"

# 5. 마이그레이션 파일 확인
# (Windows) type supabase_add_market_regime.sql | findstr "market_regime"
# Assert: 출력 존재

# 6. 프론트엔드 타입 확인
# grep "market_regime" frontend/src/types/database.ts
# Assert: 출력 존재

# 7. TypeScript 빌드
# cd frontend && npx tsc --noEmit --project tsconfig.app.json

# 8. pytest (기존 테스트 회귀 방지)
pytest tests/ -v --tb=short 2>&1 || echo "테스트 없으면 무시"
```

## 주의사항 (구현자용)

1. **`src/AGENTS.md` 준수**: 모든 주석·docstring·로그는 한국어. async 금지. 표준 임포트 순서.
2. **에러 차폐**: `_update_market_regime()`은 반드시 try/except로 감싸서 레짐 판단 실패가 봇을 죽이지 않도록.
3. **Rate Limiting**: BTC OHLCV는 10분마다만 조회 (loop_count % 60 == 1). 추가 `time.sleep(0.2)` 불필요 (기존 top_symbols 갱신과 같은 틱에서 실행).
4. **기존 게이트 유지**: `engine.py`의 ADX/vol/MA 게이트를 절대 제거하지 말 것. 레짐은 상위 필터 (이중 방어).
5. **evaluate_exit() 불변**: 레짐이 바뀌어도 청산 로직은 변경하지 않음.
6. **DB 4곳 동시 수정**: SQL → Python → TypeScript → React 순서. 하나라도 누락 시 런타임 에러.
7. **AntD v6 문서 확인**: `Tag`, `Tooltip` 컴포넌트 사용 전 `context7_query-docs`로 현재 API 확인 필수.
