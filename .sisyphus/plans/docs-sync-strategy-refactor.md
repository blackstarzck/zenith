# GPT 전략 리팩터 — docs/ 문서 동기화

## 메타데이터
- **생성일**: 2026-03-02
- **근거**: `gpt-strategy-refactor` 계획 실행 후 docs/ 문서가 코드와 불일치
- **수정 파일**: `docs/Algorithm_Specification.md`, `docs/Strategy-Parameters-Guide.md`, `docs/System-Architecture-Design.md`, `docs/Risk_Security_Protocol.md`
- **Source of Truth**: `src/config.py`, `src/strategy/engine.py`, `src/orchestrator.py`
- **Metis 검토**: 완료 (session: `ses_3561a1da7ffexcEB2g3K2o9j0o`)

## 핵심 원칙
- 코드 수정 절대 없음 — docs only
- 모든 수치는 `src/config.py`, `src/strategy/engine.py`를 source of truth로 사용
- 기존 문서의 한국어 문체와 비유 스타일 유지
- Mermaid 다이어그램 변경 후 문법 유효성 확인 필수

## 사전 결정
- **D1**: 백테스트 표(Strategy-Parameters-Guide.md L115-119)는 수치를 임의 변경하지 않고, 채택 행만 78로 변경 + "파라미터 변경 전 결과" 주석 추가
- **D2**: Risk_Security_Protocol.md Line 6 "5분→30초" 기존 불일치도 함께 수정 (저비용)
- **D3**: System-Architecture-Design.md는 "10분→2분" 1건만 수정 (Metis 확인: 다른 outdated값 없음)

---

## Wave 1: 문서 수정 (ALL PARALLEL — 의존성 없음)

- [x] TODO-1: `docs/Algorithm_Specification.md` 전면 수정 (12개 discrepancy)

**파일**: `docs/Algorithm_Specification.md`

### 값 수정 (6건)

| # | 위치 | 현재 (잘못됨) | 수정값 | 비고 |
|---|------|-------------|--------|------|
| 1 | L15, 산문 | "진입 임계치를 **+15점**" | "진입 임계치를 **+20점**" | regime_trending_offset |
| 2 | L27, BB 복귀 행 | `recovered=100, below=30, none=0` | **3단계**: RSI<15→30, MA데드크로스→30, ADX>25+price<MA50→40, 정상→100, below=30, none=0 | 테이블 행 전체 교체 |
| 3 | L34, 산문 | "기본값: **70.0**" | "기본값: **78.0**" | entry_score_threshold |
| 4 | L77, Mermaid R4 노드 | `"오프셋 +15"` | `"오프셋 +20"` | |
| 5 | L118, 산문 | "ATR의 **2.5배** 이상" | 레짐 적응형 설명으로 교체: "시장 레짐에 따라 ATR의 2.2~2.8배(횡보=2.8, 추세=2.2, 변동성=2.5)를 적용" | |
| 6 | L132, Mermaid H1 노드 | `"현재가 ≤ 진입가 - ATR×2.5?"` | `"현재가 ≤ 진입가 - ATR×레짐배수?\n(횡보2.8/추세2.2/변동2.5)"` | |

### 누락 기능 추가 (4건)

| # | 추가 위치 | 내용 |
|---|----------|------|
| 7 | L29 뒤 (스코어링 테이블 아래) | **RSI slope 감쇠**: RSI < 15일 때 RSI↗ 기울기 스코어에 ×0.6 감쇠 적용 — 극저 RSI에서의 일시적 반등 기울기 신뢰도 하향 |
| 8 | L114 뒤 (2단계 분할 익절 아래) | **1차 익절 후 스코어링 매도 비활성화**: 1차 익절(50%) 후에는 스코어링 기반 매도를 건너뛰고, 오직 하드 룰(동적 손절 + 트레일링 스탑)만 작동. 수익 극대화를 위해 트레일링 스탑이 실효화되도록 보장. |
| 9 | L15 레짐 오프셋 설명에 추가 | **레짐 플래핑 방지**: `regime_lookback_candles=2` 다수결 + 안전 모드 해제 시 최소 **20분** 유지 (단방향 홀드). 안전 모드(추세/변동성) 진입은 즉시, 해제(→횡보)만 20분 대기. |
| 10 | L15 레짐 오프셋 설명에 추가 | `regime_lookback_candles`: 2캔들 히스테리시스 |

### Mermaid 구조 변경 (2건)

| # | 다이어그램 | 변경 |
|---|----------|------|
| 11 | Entry Mermaid (L50-104) | R4 노드: "+15" → "+20" |
| 12 | Exit Mermaid (L123-162) | **구조 변경**: H3(트레일링) "아니오" → 새 분기 `{이미 반매도?}` 추가. "예"→ `HOLD (스코어링 비활성, 트레일링 대기)`, "아니오"→ `EXIT_SCORE`. 기존 H3→EXIT_SCORE 직행 경로를 이 분기로 교체. |

**Exit Mermaid 변경 전:**
```
H3 -->|"아니오"| EXIT_SCORE
```

**Exit Mermaid 변경 후:**
```
H3 -->|"아니오"| H5{"이미 반매도(half_sold)?"}
H5 -->|"예"| H6["⏳ 홀딩 유지\n(스코어링 비활성, 트레일링 대기)"]
H5 -->|"아니오"| EXIT_SCORE
```

**Source of Truth**: `config.py:64-133`, `engine.py:96-100,166-194,260-270`, `orchestrator.py:666-682`

**QA**:
```bash
grep -c "78" docs/Algorithm_Specification.md          # ≥ 1
grep -c "오프셋 +20" docs/Algorithm_Specification.md  # ≥ 1
grep -c "ATR×2.5" docs/Algorithm_Specification.md     # = 0
grep -c "오프셋 +15" docs/Algorithm_Specification.md  # = 0
grep -c "감쇠" docs/Algorithm_Specification.md        # ≥ 1
grep -c "스코어링.*비활성\|비활성.*스코어링" docs/Algorithm_Specification.md  # ≥ 1
grep -c "20분\|min_hold" docs/Algorithm_Specification.md  # ≥ 1
```

---

- [x] TODO-2: `docs/Strategy-Parameters-Guide.md` 전면 수정 (10개 discrepancy)

**파일**: `docs/Strategy-Parameters-Guide.md`

### 값 수정 (8건)

| # | 위치 | 현재 (잘못됨) | 수정값 |
|---|------|-------------|--------|
| 1 | L32 | `atr_stop_multiplier` \| **2.5** | 레짐 적응형으로 확장: 기존 행을 `atr_stop_multiplier` \| **3.0** \| "기본 폴백 값"으로 수정 + 아래 3행 추가: `atr_stop_multiplier_ranging` \| 2.8, `_trending` \| 2.2, `_volatile` \| 2.5 |
| 2 | L54 | `w_volatility` \| **1.0** | **0.8** |
| 3 | L55 | `w_ma_trend` \| **1.0** | **1.2** |
| 4 | L56 | `w_adx` \| **1.0** | **1.1** |
| 5 | L57 | `w_bb_recovery` \| **1.0** + 설명 단순 | **0.9** + 3단계 설명: "3단계 평가: RSI<15→30, MA하락→30, ADX>25+price<MA50→40, 정상→100, 이탈중=30, 해당없음=0" |
| 6 | L58 | `w_rsi_slope` \| **1.0** | **1.2** |
| 7 | L59 | `w_rsi_level` \| **1.0** | **1.3** |
| 8 | L70 | 기본값 **70** (볼드 행) | 기본값 **78** |

### 예시 재계산 (1건)

| # | 위치 | 변경 |
|---|------|------|
| 9 | L86-94 | 예시 제목: "기본 가중치(모두 1.0)" → "현재 가중치 적용 시" |

**변경 후 예시 계산:**
```
총점 = (0.8×90 + 1.2×100 + 1.1×88 + 0.9×100 + 1.2×70 + 1.3×68) / (0.8+1.2+1.1+0.9+1.2+1.3)
     = (72 + 120 + 96.8 + 90 + 84 + 88.4) / 6.5
     = 551.2 / 6.5
     = 84.8점
```
결과: 임계값 78점을 넘었으므로 **매수(BUY)** 신호를 생성한다.

L82 BB 예시: 전제 조건 추가 — "(RSI=28 > 15, MA 상승추세이므로 정상 복귀 100점)"

### 백테스트 표 수정 (1건)

| # | 위치 | 변경 |
|---|------|------|
| 10 | L115-119 | **70** 채택 행 → **78** 채택으로 변경. 표 상단에 주석 추가: "> ⚠️ 아래 수치는 가중치 재조정 전(모두 1.0) 시뮬레이션 결과입니다. 현재 가중치 적용 시 결과가 다를 수 있습니다." |

**Source of Truth**: `config.py:109-118`

**QA**:
```bash
grep "w_volatility.*0.8" docs/Strategy-Parameters-Guide.md    # match
grep "w_ma_trend.*1.2" docs/Strategy-Parameters-Guide.md      # match
grep "w_rsi_level.*1.3" docs/Strategy-Parameters-Guide.md     # match
grep -c "78" docs/Strategy-Parameters-Guide.md                # ≥ 2
grep -c "84.8" docs/Strategy-Parameters-Guide.md              # ≥ 1
```

---

- [x] TODO-3: `docs/System-Architecture-Design.md` 수정 (1건)

**파일**: `docs/System-Architecture-Design.md`

| # | 위치 | 현재 | 수정값 |
|---|------|------|--------|
| 1 | L24 | "**10분마다** 판단하여" | "**2분마다** 판단하여" |

**Source of Truth**: `orchestrator.py:198-200` (`_loop_count % 12 == 1`, 12×10초 = 2분)

**QA**:
```bash
grep -c "10분마다" docs/System-Architecture-Design.md   # = 0
grep -c "2분마다" docs/System-Architecture-Design.md    # ≥ 1
```

---

- [x] TODO-4: `docs/Risk_Security_Protocol.md` 수정 (3건)

**파일**: `docs/Risk_Security_Protocol.md`

### 기존 불일치 수정 (1건)
| # | 위치 | 현재 | 수정값 |
|---|------|------|--------|
| 1 | L6 | "주문 후 **5분** 내 체결되지 않은 주문은 자동 취소" | "주문 후 **30초** 내 체결되지 않은 주문은 자동 취소" |

### 신규 섹션 추가 (2건)
§1.1 (Kelly) 아래, §1.2 (슬리피지) 앞에 삽입:

**§1.3 레짐 적응형 ATR 손절 (신규)**:
```markdown
### 1.3. 레짐 적응형 ATR 손절 (Regime-Adaptive Stop Loss)
- **동적 배수 적용:** 시장 레짐(횡보/추세/변동성)에 따라 ATR 손절 배수를 차등 적용하여 레짐별 최적 방어선을 유지.
  - 횡보장(ranging): ATR × 2.8 — 노이즈 허용 여유
  - 추세장(trending): ATR × 2.2 — 역추세 빠른 탈출
  - 변동성 폭발(volatile): ATR × 2.5 — 중립
  - 미분류: ATR × 3.0 — 안전 폴백
- **단방향 레짐 홀드:** 안전 모드(추세/변동성) 진입은 즉시 허용하되, 해제(→횡보)는 최소 20분 유지하여 레짐 플래핑 방지.
```

**§1.4 연속 손절 브레이커 (신규)**:
```markdown
### 1.4. 연속 손절 브레이커 (Consecutive Stop-Loss Breaker)
- **연쇄 손실 방지:** 30분 내 2건 이상 손절 발생 시 신규 매수를 30분간 차단.
- **기존 포지션 영향 없음:** 이미 보유 중인 포지션의 손절/익절은 정상 작동하며, 신규 진입만 차단.
- **자동 해제:** 차단 시간(30분) 경과 후 자동으로 매수 허용 복구.
```

기존 §1.2 슬리피지 → §1.4로 번호 이동, 기존 §2 보안 → §2 유지 (번호 재정렬)

**Source of Truth**: `config.py:66-70,134-142`, `orchestrator.py:65-67,756-781`

**QA**:
```bash
grep -c "브레이커" docs/Risk_Security_Protocol.md      # ≥ 1
grep -c "2.8" docs/Risk_Security_Protocol.md           # ≥ 1
grep -c "30초" docs/Risk_Security_Protocol.md          # ≥ 1
grep -c "5분 내" docs/Risk_Security_Protocol.md        # = 0
```

---

## Wave 2: 최종 검증

- [x] TODO-5: 최종 QA — grep 기반 전수 검증

**모든 Wave 1 작업 완료 후 실행.**

```bash
# 구 값 완전 제거 확인
grep -rn "ATR×2\.5" docs/Algorithm_Specification.md docs/Strategy-Parameters-Guide.md  # 0 matches
grep -rn "오프셋 +15" docs/Algorithm_Specification.md  # 0 matches
grep -rn "10분마다 판단" docs/System-Architecture-Design.md  # 0 matches
grep -rn "5분 내 체결" docs/Risk_Security_Protocol.md  # 0 matches

# 신규 값 존재 확인
grep -c "78" docs/Algorithm_Specification.md docs/Strategy-Parameters-Guide.md  # each ≥ 1
grep -c "0\.8" docs/Strategy-Parameters-Guide.md  # ≥ 1 (w_volatility)
grep -c "2분마다" docs/System-Architecture-Design.md   # ≥ 1
grep -c "브레이커" docs/Risk_Security_Protocol.md  # ≥ 1
grep -c "레짐" docs/Risk_Security_Protocol.md  # ≥ 1
```

---

## MUST NOT

- ❌ 코드 파일 수정 금지 (docs only)
- ❌ 백테스트 수치(거래수/승률/수익률)를 임의 변경 금지
- ❌ PRD.md, Data_Model_ERD.md 등 범위 외 문서 수정 금지
- ❌ Mermaid 문법 깨뜨리기 금지 — 구조 변경 시 특히 주의
- ❌ 기존 문서의 비유/문체 변경 금지 (해사 비유, 온도계 비유 등 유지)
