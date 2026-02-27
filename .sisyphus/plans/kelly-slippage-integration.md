# Plan: kelly-slippage-integration

> 켈리 공식 기반 동적 포지션 사이징 + 호가창 슬리피지 분석 통합 구현

## Context

현재 Zenith는 **고정 20% 비율**(`max_position_ratio`)로 포지션 사이징하고, **시장가 주문**을 슬리피지 제어 없이 실행한다. 이 계획은:
1. **Kelly Criterion**: 과거 거래 승률/손익비 기반 동적 포지션 사이징 (Half-Kelly)
2. **Slippage Estimation**: 호가창 데이터로 예상 슬리피지 계산, 임계값 초과 시 진입 거부

두 기능을 하나의 진입 파이프라인으로 통합한다.

### 수정 후 진입 파이프라인

```
_evaluate_entries()
  → regime_filter (기존 — 변경 없음)
  → engine.evaluate() → Signal (기존 — 변경 없음)
  → recent_trades = storage.get_recent_sell_trades(limit=100)
  → kelly_size = risk.calc_position_size(balance, recent_trades)  # 켈리 적용
  → slippage = collector.estimate_slippage(symbol, 'buy', kelly_size)
  → if slippage > threshold: SKIP (진입 거부)
  → executor.buy_market(symbol, kelly_size)  # 슬리피지 값 기록
```

## Scope

### IN
- `src/config.py` — RiskParams에 kelly/slippage 파라미터 추가
- `src/risk/manager.py` — calc_position_size 켈리 확장
- `src/collector/data_collector.py` — estimate_slippage 신규 메서드
- `src/storage/client.py` — get_recent_sell_trades, insert_trade에 slippage, upsert_bot_state에 kelly_fraction
- `src/orchestrator.py` — 파이프라인 통합
- `supabase_add_kelly_slippage.sql` — trades.slippage + bot_state.kelly_fraction 컬럼
- `frontend/src/types/database.ts` — Trade, BotState 타입 확장
- `frontend/src/pages/DashboardPage.tsx` — 켈리 뱃지 + 슬리피지 컬럼
- `docs/` 5개 문서 업데이트

### OUT (명시적 제외)
- ❌ 백테스트 엔진 켈리 통합 (`backtest/engine.py` 기존 고정비율 유지)
- ❌ 분할 주문 (TWAP/VWAP) — 슬리피지 초과 시 거절만
- ❌ 매도(청산) 시 슬리피지 체크 — 청산은 즉시 실행 우선
- ❌ 프론트엔드에서 kelly_multiplier 조절 — 고정 0.5
- ❌ 종목별(per-symbol) 켈리 — 전체(global) 켈리만
- ❌ 실제(post-trade) 슬리피지 기록 — 예상(pre-trade)만 저장
- ❌ 신규 React 훅 — useBotState/useTrades가 select('*')로 자동 포함

## Constraints

- **완전 동기** Python (async/await 금지)
- **@dataclass(frozen=True)** for RiskParams
- **모든 DB 호출** try/except 래핑
- **스키마 변경 = 4곳 동시 수정** (SQL, storage client, TS types, hooks — 단 hooks는 select('*')이므로 변경 불요)
- **인라인 style={{}}** 프론트엔드 스타일링
- **estimate_slippage fail-open** — API 오류 시 0.0 반환 (거래 차단 금지)
- **calc_position_size 하위호환** — recent_sell_trades=None이면 기존 고정비율

## Key Decisions

| 결정 | 선택 | 근거 |
|------|------|------|
| Kelly 배수 | Half-Kelly (0.5배) | 암호화폐 변동성 고려, 기대성장률 75% 유지 |
| 최소 샘플 | 30건 매도 거래 | 통계적 유의성 확보 (미달 시 고정 20% 폴백) |
| 슬리피지 임계값 | 50bps (0.5%) | 수수료(0.05%) 대비 10배, 대부분 알트코인 커버 |
| 초과 시 동작 | 진입 거부 | 단순/안전, 다음 틱에서 재평가 |
| 매도 슬리피지 | 체크 안 함 | 손절/익절 즉시 실행 우선 |
| 켈리 범위 | 글로벌 (전 종목) | 종목별은 30건 임계치 비현실적 |
| 슬리피지 저장 | 예상값 (pre-trade) | 실제값은 복잡도 높음, v1에서 불필요 |
| Kelly → RiskParams | StrategyParams 아닌 RiskParams | 리스크 관리 영역, 핫 리로드 불필요 |

## Dependency Graph

```
Phase 1 (Schema — 사용자가 Supabase SQL Editor에서 실행):
  TODO-01: supabase_add_kelly_slippage.sql

Phase 2 (Backend — 순서 중요):
  TODO-02: config.py (RiskParams 확장)        ← 의존 없음
  TODO-03: storage/client.py (3개 메서드)     ← 의존 없음
  TODO-04: risk/manager.py (켈리 로직)        ← TODO-02에 의존
  TODO-05: collector/data_collector.py (슬리피지) ← 의존 없음
  TODO-06: orchestrator.py (통합)             ← TODO-02~05 전부 의존

Phase 3 (Frontend — Phase 2와 독립):
  TODO-07: frontend 타입 + UI                 ← 의존 없음

Phase 4 (Docs — 코드 완료 후):
  TODO-08: 문서 5개 업데이트                  ← TODO-02~07 완료 후

Phase 5 (Verification):
  Final Verification Wave                     ← 전체 완료 후
```

## Parallel Execution

```
Wave 1: TODO-01 (SQL)
Wave 2: TODO-02, TODO-03, TODO-05, TODO-07 (병렬 가능)
Wave 3: TODO-04 (TODO-02 완료 필요)
Wave 4: TODO-06 (TODO-02~05 전부 완료 필요)
Wave 5: TODO-08 (docs)
Wave 6: Final Verification
```

---

## TODO-01: Supabase 마이그레이션 — trades.slippage + bot_state.kelly_fraction

- **Category**: `quick`
- **Skills**: `[]`
- **Depends**: 없음
- **File**: `supabase_add_kelly_slippage.sql` (신규)

### What

두 테이블에 각각 1개 컬럼 추가하는 마이그레이션 SQL 파일 생성.

### 코드

```sql
-- trades 테이블에 예상 슬리피지(bps) 컬럼 추가
ALTER TABLE trades
ADD COLUMN IF NOT EXISTS slippage DECIMAL(10, 4) DEFAULT NULL;

COMMENT ON COLUMN trades.slippage IS '매수 진입 시 예상 슬리피지 (bps 단위). 매도 거래는 NULL.';

-- bot_state 테이블에 켈리 비중 컬럼 추가
ALTER TABLE bot_state
ADD COLUMN IF NOT EXISTS kelly_fraction DECIMAL(10, 6) DEFAULT NULL;

COMMENT ON COLUMN bot_state.kelly_fraction IS '현재 켈리 공식 기반 포지션 비중 (0.0~1.0). NULL이면 고정비율 사용 중.';
```

### QA

```bash
# 파일 존재 확인
ls supabase_add_kelly_slippage.sql
# 기대: 파일 존재
```

---

## TODO-02: config.py — RiskParams에 켈리/슬리피지 파라미터 추가

- **Category**: `quick`
- **Skills**: `[]`
- **Depends**: 없음
- **File**: `src/config.py`
- **Lines**: RiskParams 클래스 (101~108번줄)

### What

`RiskParams` dataclass에 3개 필드 추가. `@dataclass(frozen=True)` 유지.

### Before (현재 코드)

```python
@dataclass(frozen=True)
class RiskParams:
    max_position_ratio: float = 0.20
    max_concurrent_positions: int = 5
    daily_loss_limit_ratio: float = 0.05
    unfilled_timeout_sec: int = 30
    min_order_amount_krw: int = 5000
```

### After (수정 후)

```python
@dataclass(frozen=True)
class RiskParams:
    max_position_ratio: float = 0.20
    max_concurrent_positions: int = 5
    daily_loss_limit_ratio: float = 0.05
    unfilled_timeout_sec: int = 30
    min_order_amount_krw: int = 5000

    # 켈리 공식 포지션 사이징
    kelly_multiplier: float = 0.5        # Half-Kelly (0.5배)
    kelly_min_trades: int = 30           # 최소 샘플 수 (미달 시 고정비율 폴백)

    # 슬리피지 허용 한도
    slippage_threshold_bps: float = 50.0  # 50bps (0.5%) 초과 시 진입 거부
```

### QA

```bash
python -c "from src.config import RiskParams; p = RiskParams(); print(f'kelly={p.kelly_multiplier}, min={p.kelly_min_trades}, slip={p.slippage_threshold_bps}')"
# 기대: kelly=0.5, min=30, slip=50.0
```

---

## TODO-03: storage/client.py — 거래 내역 조회 + slippage/kelly_fraction 지원

- **Category**: `quick`
- **Skills**: `[]`
- **Depends**: 없음
- **File**: `src/storage/client.py`

### What

3가지 수정:
1. `get_recent_sell_trades(limit=100)` 신규 메서드 — 켈리 계산용 매도 거래 PnL 조회
2. `insert_trade(...)` — `slippage: float | None = None` 파라미터 추가
3. `upsert_bot_state(...)` — `kelly_fraction: float | None = None` 파라미터 추가

### 1. get_recent_sell_trades 신규 메서드

기존 `get_trades` 패턴을 따르되, `side='ask'`이고 `pnl IS NOT NULL`인 거래만 필터링.

```python
def get_recent_sell_trades(self, limit: int = 100) -> list[dict]:
    """켈리 공식 계산용 최근 매도 거래 PnL 목록을 반환합니다.
    
    Returns:
        list[dict]: 각 dict에 'pnl' 키 포함. 빈 리스트면 데이터 없음.
    """
    try:
        result = (
            self._supabase.table('trades')
            .select('pnl')
            .eq('side', 'ask')
            .not_.is_('pnl', 'null')
            .order('created_at', desc=True)
            .limit(limit)
            .execute()
        )
        return result.data or []
    except Exception as e:
        logger.exception('매도 거래 조회 실패: %s', e)
        return []
```

### 2. insert_trade — slippage 파라미터 추가

기존 시그니처에 `slippage: float | None = None` 추가. row dict 구성 시 조건부 포함:

```python
# 기존 파라미터 뒤에 추가
def insert_trade(self, symbol, side, price, volume, amount, fee,
                 pnl=None, remaining_volume=None, reason=None,
                 slippage: float | None = None):  # ← 추가
    ...
    row = { ... }  # 기존 필드들
    if slippage is not None:
        row['slippage'] = round(slippage, 4)
    ...
```

### 3. upsert_bot_state — kelly_fraction 파라미터 추가

기존 `market_regime` 패턴과 동일하게 추가:

```python
def upsert_bot_state(self, *, ..., kelly_fraction: float | None = None):
    ...
    if kelly_fraction is not None:
        row['kelly_fraction'] = round(kelly_fraction, 6)
```

### QA

```bash
# 모듈 임포트 + 메서드 존재 확인
python -c "
from src.storage.client import StorageClient
assert hasattr(StorageClient, 'get_recent_sell_trades')
print('OK: get_recent_sell_trades exists')
"

# insert_trade 시그니처에 slippage 있는지 확인
python -c "
import inspect
from src.storage.client import StorageClient
sig = inspect.signature(StorageClient.insert_trade)
assert 'slippage' in sig.parameters
print('OK: slippage param exists')
"
```

---

## TODO-04: risk/manager.py — 켈리 공식 기반 동적 포지션 사이징

- **Category**: `deep`
- **Skills**: `[]`
- **Depends**: TODO-02 (config.py)
- **File**: `src/risk/manager.py`

### What

`calc_position_size` 메서드를 확장하여 켈리 공식 적용. **하위호환 필수**: `recent_sell_trades=None`이면 기존 고정비율 동작.

### 수정 대상 메서드 (현재 코드, line 66)

```python
def calc_position_size(self, current_balance: float) -> float:
    return current_balance * self._params.max_position_ratio
```

### 수정 후

```python
def calc_position_size(self, current_balance: float,
                       recent_sell_trades: list[dict] | None = None) -> float:
    """포지션 크기(KRW)를 계산합니다.
    
    켈리 공식 기반 동적 사이징: 최근 매도 거래 통계로 최적 비중 산출.
    데이터 부족(< kelly_min_trades) 시 기존 고정비율(max_position_ratio) 폴백.
    
    Args:
        current_balance: 현재 가용 잔고 (KRW)
        recent_sell_trades: 최근 매도 거래 목록 (각 dict에 'pnl' 키 필수). None이면 고정비율.
    
    Returns:
        float: 투입 금액 (KRW). 0.0이면 진입 차단.
    """
    fixed_size = current_balance * self._params.max_position_ratio
    
    # 폴백 조건: 데이터 없음 또는 부족
    if not recent_sell_trades or len(recent_sell_trades) < self._params.kelly_min_trades:
        logger.debug('[Kelly 폴백] 매도 거래 %d건 < 최소 %d건, 고정비율 %.0f%% 사용',
                     len(recent_sell_trades) if recent_sell_trades else 0,
                     self._params.kelly_min_trades,
                     self._params.max_position_ratio * 100)
        return fixed_size
    
    # 승률/손익비 계산
    wins = [t['pnl'] for t in recent_sell_trades if t.get('pnl', 0) > 0]
    losses = [t['pnl'] for t in recent_sell_trades if t.get('pnl', 0) < 0]
    
    # 엣지 케이스: 손실 없음 (전승) → 고정비율 사용 (과신 방지)
    if not losses:
        logger.info('[Kelly 폴백] 손실 거래 0건 (전승), 고정비율 사용')
        return fixed_size
    
    # 엣지 케이스: 승리 없음 (전패) → 진입 차단
    if not wins:
        logger.warning('[Kelly 차단] 승리 거래 0건 (전패), 진입 차단')
        return 0.0
    
    total = len(wins) + len(losses)
    win_rate = len(wins) / total          # p
    avg_win = sum(wins) / len(wins)       # 평균 수익
    avg_loss = abs(sum(losses) / len(losses))  # 평균 손실 (양수)
    
    # 손익비 (b)
    if avg_loss == 0:
        return fixed_size  # 0으로 나누기 방지
    win_loss_ratio = avg_win / avg_loss
    
    # 켈리 공식: f* = p - (1-p)/b
    kelly_f = win_rate - ((1 - win_rate) / win_loss_ratio)
    
    # Half-Kelly 적용
    optimal_f = kelly_f * self._params.kelly_multiplier
    
    # 켈리 ≤ 0 → 기대값 음수, 진입 차단
    if optimal_f <= 0:
        logger.warning('[Kelly 차단] 기대값 음수 (Kelly=%.4f), 진입 차단', kelly_f)
        return 0.0
    
    # max_position_ratio로 캡핑
    capped_f = min(optimal_f, self._params.max_position_ratio)
    kelly_size = current_balance * capped_f
    
    logger.info('[Kelly 사이징] 승률: %.1f%%, 손익비: %.2f, Kelly: %.1f%% → %.0f KRW',
                win_rate * 100, win_loss_ratio, capped_f * 100, kelly_size)
    
    return kelly_size
```

### QA

```bash
# 켈리 계산 검증
python -c "
from src.risk.manager import RiskManager
from src.config import RiskParams
rm = RiskManager(RiskParams(kelly_min_trades=5), 1_000_000)
trades = [{'pnl': 10000}]*7 + [{'pnl': -8000}]*3
size = rm.calc_position_size(1_000_000, trades)
assert 0 < size <= 200_000, f'out of range: {size}'
print(f'OK: Kelly size = {size}')
"

# 폴백 검증 (< min_trades)
python -c "
from src.risk.manager import RiskManager
from src.config import RiskParams
rm = RiskManager(RiskParams(), 1_000_000)
size = rm.calc_position_size(1_000_000, [{'pnl': 100}]*5)
assert size == 200_000, f'Expected 200000, got {size}'
print(f'OK: Fallback = {size}')
"

# 하위호환 검증 (None)
python -c "
from src.risk.manager import RiskManager
from src.config import RiskParams
rm = RiskManager(RiskParams(), 1_000_000)
size = rm.calc_position_size(1_000_000)
assert size == 200_000, f'Expected 200000, got {size}'
print(f'OK: Backward compat = {size}')
"
```

---

## TODO-05: collector/data_collector.py — 호가창 슬리피지 추정 메서드

- **Category**: `deep`
- **Skills**: `[]`
- **Depends**: 없음
- **File**: `src/collector/data_collector.py`

### What

`estimate_slippage(symbol, side, amount_krw)` 메서드 추가. Walk-the-book 알고리즘으로 예상 슬리피지(bps) 계산.

### 핵심 로직

```python
def estimate_slippage(self, symbol: str, side: str, amount_krw: float) -> float:
    """호가창을 시뮬레이션하여 예상 슬리피지를 bps 단위로 반환합니다.
    
    Args:
        symbol: 종목 코드 (예: 'KRW-BTC')
        side: 'buy' 또는 'sell'
        amount_krw: 매수 시 투입 금액 (KRW)
    
    Returns:
        float: 예상 슬리피지 (bps). 오류 시 0.0 (fail-open).
    """
    try:
        orderbook = self.get_orderbook(symbol)
        if not orderbook or 'orderbook_units' not in orderbook:
            logger.warning('[슬리피지] %s 호가 데이터 없음, 0.0 반환', symbol)
            return 0.0
        
        units = orderbook['orderbook_units']
        if not units:
            return 0.0
        
        if side == 'buy':
            # 매수: ask(매도 호가) 아래서부터 위로 소진
            best_price = units[0]['ask_price']
            remaining = amount_krw
            total_volume = 0.0
            total_cost = 0.0
            
            for unit in units:
                price = unit['ask_price']
                size = unit['ask_size']
                level_cost = price * size
                
                if remaining >= level_cost:
                    total_cost += level_cost
                    total_volume += size
                    remaining -= level_cost
                else:
                    volume_at_level = remaining / price
                    total_cost += remaining
                    total_volume += volume_at_level
                    remaining = 0.0
                    break
        else:  # sell
            # 매도: bid(매수 호가) 위에서부터 아래로 소진
            best_price = units[0]['bid_price']
            # 매도 시 amount_krw를 volume으로 변환 필요
            remaining_volume = amount_krw / best_price if best_price > 0 else 0
            total_volume = 0.0
            total_cost = 0.0
            
            for unit in units:
                price = unit['bid_price']
                size = unit['bid_size']
                
                if remaining_volume >= size:
                    total_cost += price * size
                    total_volume += size
                    remaining_volume -= size
                else:
                    total_cost += price * remaining_volume
                    total_volume += remaining_volume
                    remaining_volume = 0.0
                    break
            remaining = remaining_volume  # 남은 수량
        
        # 호가창 깊이 부족
        if remaining > 0 or total_volume == 0:
            logger.warning('[슬리피지] %s 호가 깊이 부족, 전량 소진 불가', symbol)
            return 9999.0  # 극단적 슬리피지 → 진입 거부 유도
        
        avg_price = total_cost / total_volume
        slippage_bps = abs((avg_price - best_price) / best_price) * 10000
        
        logger.debug('[슬리피지] %s | 최우선가: %.0f, 예상평균가: %.0f, 슬리피지: %.1f bps',
                     symbol, best_price, avg_price, slippage_bps)
        
        return round(slippage_bps, 2)
        
    except Exception as e:
        logger.warning('[슬리피지] %s 추정 실패: %s — 0.0 반환 (fail-open)', symbol, e)
        return 0.0  # fail-open: API 오류가 거래를 차단하면 안 됨
```

### QA

```bash
# 모듈 임포트 + 메서드 존재 확인
python -c "
from src.collector.data_collector import UpbitCollector
assert hasattr(UpbitCollector, 'estimate_slippage')
print('OK: estimate_slippage exists')
"
```

---

## TODO-06: orchestrator.py — 켈리 + 슬리피지 파이프라인 통합

- **Category**: `deep`
- **Skills**: `[]`
- **Depends**: TODO-02, TODO-03, TODO-04, TODO-05
- **File**: `src/orchestrator.py`

### What

`_execute_buy` 메서드를 수정하여:
1. 매수 전에 `get_recent_sell_trades` → `calc_position_size`에 전달 (켈리 적용)
2. 매수 전에 `estimate_slippage` 호출 → 임계값 초과 시 진입 거부
3. 매수 성공 시 `insert_trade`에 slippage 값 전달
4. `kelly_fraction`을 `bot_state`에 주기적으로 업데이트

### 수정 포인트

#### 1. _execute_buy 수정 (line ~430-465)

현재 흐름:
```python
amount = self._risk.calc_position_size(current_balance)
result = self._executor.buy_market(symbol, amount)
self._storage.insert_trade(...)
```

수정 후:
```python
# 켈리 기반 사이징
recent_trades = self._storage.get_recent_sell_trades(limit=100)
amount = self._risk.calc_position_size(current_balance, recent_trades)

# 켈리 결과 0이면 진입 차단
if amount < self._risk._params.min_order_amount_krw:
    logger.info('[진입 차단] %s | Kelly 사이징 결과 최소 금액 미달 (%.0f KRW)', symbol, amount)
    return

# 슬리피지 체크
slippage_bps = self._collector.estimate_slippage(symbol, 'buy', amount)
if slippage_bps > self._risk._params.slippage_threshold_bps:
    logger.info('[슬리피지 초과] %s | 예상: %.1f bps > 한도: %.1f bps, 진입 거부',
                symbol, slippage_bps, self._risk._params.slippage_threshold_bps)
    return

result = self._executor.buy_market(symbol, amount)
# ... 기존 로직 ...
self._storage.insert_trade(..., slippage=slippage_bps)  # slippage 추가
```

#### 2. kelly_fraction 업데이트 (throttled)

`_tick()` 메서드에서 일정 주기로 kelly_fraction을 bot_state에 기록.
regime 업데이트와 유사한 패턴 (60틱마다 = ~10분):

```python
# _tick() 내부, regime 업데이트 근처에 추가
if self._loop_count % 60 == 2:  # regime은 %60==1, kelly는 %60==2
    self._update_kelly_fraction()

def _update_kelly_fraction(self):
    """켈리 비중을 계산하여 bot_state에 업데이트합니다."""
    try:
        recent_trades = self._storage.get_recent_sell_trades(limit=100)
        if not recent_trades or len(recent_trades) < self._risk._params.kelly_min_trades:
            kelly_f = None  # 데이터 부족
        else:
            wins = [t['pnl'] for t in recent_trades if t.get('pnl', 0) > 0]
            losses = [t['pnl'] for t in recent_trades if t.get('pnl', 0) < 0]
            if not losses or not wins:
                kelly_f = None
            else:
                total = len(wins) + len(losses)
                win_rate = len(wins) / total
                avg_win = sum(wins) / len(wins)
                avg_loss = abs(sum(losses) / len(losses))
                if avg_loss == 0:
                    kelly_f = None
                else:
                    raw_kelly = win_rate - ((1 - win_rate) / (avg_win / avg_loss))
                    kelly_f = min(raw_kelly * self._risk._params.kelly_multiplier,
                                  self._risk._params.max_position_ratio)
                    if kelly_f <= 0:
                        kelly_f = 0.0
        self._storage.upsert_bot_state(kelly_fraction=kelly_f)
    except Exception as e:
        logger.warning('[Kelly 업데이트 실패] %s', e)
```

### ⚠️ 주의사항

- `_execute_buy` 호출부를 `lsp_find_references`로 확인 후 수정
- `insert_trade` 호출부 4곳 (lines 460, 521, 556, 673) 중 매수 관련만 slippage 전달, 매도 호출은 `slippage=None` 유지
- 기존 `calc_position_size(current_balance)` 호출을 `calc_position_size(current_balance, recent_trades)`로 변경

### QA

```bash
# 모듈 임포트 검증
python -c "
from src.orchestrator import Orchestrator
assert hasattr(Orchestrator, '_update_kelly_fraction')
print('OK: _update_kelly_fraction exists')
"

# pytest 전체 실행
cd src && python -m pytest tests/ -v
# 기대: 기존 테스트 전부 통과
```

---

## TODO-07: Frontend — 타입 확장 + 켈리 뱃지 + 슬리피지 컬럼

- **Category**: `quick`
- **Skills**: `[]`
- **Depends**: 없음 (Phase 2와 독립)
- **Files**: `frontend/src/types/database.ts`, `frontend/src/pages/DashboardPage.tsx`

### 1. database.ts — Trade, BotState 타입 확장

```typescript
// Trade 인터페이스에 추가 (기존 pnl 필드 근처)
slippage: number | null;  // 예상 슬리피지 (bps), 매도 거래는 null

// BotState 인터페이스에 추가 (기존 market_regime 필드 근처)
kelly_fraction: number | null;  // 켈리 비중 (0.0~1.0), null이면 고정비율
```

### 2. DashboardPage.tsx — 켈리 뱃지

기존 `REGIME_DISPLAY` 패턴 (lines 41-46) + Tag 뱃지 패턴 (lines 681-687)을 따름.

```tsx
// 상수 정의 (REGIME_DISPLAY 근처에 추가)
const formatKellyBadge = (fraction: number | null | undefined) => {
  if (fraction == null) return null;
  const pct = (fraction * 100).toFixed(1);
  const color = fraction <= 0 ? 'red' : fraction < 0.1 ? 'orange' : 'blue';
  return { text: `Kelly ${pct}%`, color };
};
```

```tsx
// JSX: 기존 레짐 뱃지 옆에 추가
{botState?.kelly_fraction != null && (() => {
  const badge = formatKellyBadge(botState.kelly_fraction);
  return badge ? (
    <Tooltip title={`켈리 공식 기반 포지션 비중: ${badge.text}`}>
      <Tag color={badge.color}>{badge.text}</Tag>
    </Tooltip>
  ) : null;
})()}
```

### 3. DashboardPage.tsx — 거래 내역 슬리피지 컬럼

기존 `tradeColumns` 배열 (line 80~149)에 슬리피지 컬럼 추가:

```tsx
{
  title: '슬리피지',
  dataIndex: 'slippage',
  key: 'slippage',
  width: 80,
  render: (val: number | null) => 
    val != null ? `${val.toFixed(1)}bp` : '-',
},
```

### QA

```bash
cd frontend && npx tsc --noEmit
# 기대: 에러 0건
```

---

## TODO-08: 문서 업데이트 (5개 파일)

- **Category**: `quick`
- **Skills**: `[]`
- **Depends**: TODO-02~07 완료 후
- **Files**: `docs/` 5개

### What

AGENTS.md docs 매핑 테이블에 따라:

| 문서 | 수정 내용 |
|------|----------|
| `docs/Risk_Security_Protocol.md` | 포지션 사이징 섹션: 고정 20% → 켈리 공식 + 폴백 설명. 슬리피지 임계값 50bps 추가. |
| `docs/Data_Model_ERD.md` | trades 테이블: `slippage` 컬럼 추가. bot_state 테이블: `kelly_fraction` 컬럼 추가. |
| `docs/Algorithm_Specification.md` | 진입 로직 섹션: 켈리 사이징 단계 + 슬리피지 체크 단계 추가 (레짐 감지 후, 주문 전). |
| `docs/System-Architecture-Design.md` | 데이터 흐름: 호가창 → 슬리피지 추정 → 진입 판단 경로 추가. |
| `docs/API_Integration.md` | collector 섹션: `estimate_slippage()` 메서드 + pyupbit orderbook API 활용 설명. |

### QA

```bash
# 문서 내 켈리/슬리피지 언급 확인
grep -l "켈리\|Kelly\|슬리피지\|slippage" docs/*.md
# 기대: 5개 파일 모두 매칭
```

---

## Final Verification Wave

모든 TODO 완료 후:

### Backend
```bash
# 1. pytest 전체 실행
cd src && python -m pytest tests/ -v
# 기대: 기존 테스트 전부 통과 (0 failures)

# 2. 켈리 계산 검증 (known inputs)
python -c "
from src.risk.manager import RiskManager
from src.config import RiskParams
params = RiskParams()
rm = RiskManager(params, 1_000_000)
# 10 trades: 7 wins avg +10000, 3 losses avg -8000
trades = [{'pnl': 10000}]*7 + [{'pnl': -8000}]*3
size = rm.calc_position_size(1_000_000, trades)
assert 0 < size <= 200_000, f'Kelly size {size} out of range'
print(f'OK: Kelly size = {size}')
"

# 3. 켈리 폴백 검증 (< 30 trades)
python -c "
from src.risk.manager import RiskManager
from src.config import RiskParams
rm = RiskManager(RiskParams(), 1_000_000)
size = rm.calc_position_size(1_000_000, [{'pnl': 100}]*5)
assert size == 200_000, f'Expected 200000, got {size}'
print(f'OK: Fallback size = {size}')
"

# 4. 모듈 임포트 검증
python -c "
from src.risk.manager import RiskManager
from src.collector.data_collector import UpbitCollector
from src.storage.client import StorageClient
print('OK: All imports succeed')
"
```

### Frontend
```bash
cd frontend && npx tsc --noEmit
# 기대: 에러 0건
```

### Schema (Supabase SQL Editor)
```sql
SELECT column_name, data_type FROM information_schema.columns
WHERE table_name = 'trades' AND column_name = 'slippage';
-- 기대: 1행 반환

SELECT column_name, data_type FROM information_schema.columns
WHERE table_name = 'bot_state' AND column_name = 'kelly_fraction';
-- 기대: 1행 반환
```

---

## Notes

- **배포 순서**: 봇 정지 → SQL 마이그레이션 → 코드 업데이트 → 봇 재시작. 프론트엔드는 독립 배포 가능.
- **Metis 지적**: backtest/engine.py가 position sizing을 인라인으로 중복 구현 중 → 별도 이슈로 분리
- **Metis 지적**: insert_trade에 remaining_volume, reason 컬럼 마이그레이션이 별도로 존재할 수 있음 → slippage 마이그레이션은 독립적 ALTER TABLE로 안전
