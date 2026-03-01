# 사용법 가이드 페이지 구현

## 목표
매매 전략, 매수/매도 조건, 파라미터, 트레일링, 시장 레짐 등 서비스의 핵심 로직을 사용자가 이해할 수 있도록 설명하는 가이드 페이지를 추가한다. AntD Collapse 기반의 접이식 구조와 매수 스코어 시뮬레이터를 포함한다.

## 배경
- 현재 서비스에 도움말/가이드 페이지가 없음. 지표 설명이 DashboardPage의 Tooltip에 산재되어 있음.
- `docs/Strategy-Parameters-Guide.md` (119줄)와 `docs/Algorithm_Specification.md` (80줄)에 이미 한국어로 작성된 전략 설명이 존재 → 콘텐츠 소스로 활용
- `StrategyEditModal.tsx`에 가중치 기반 시뮬레이터가 이미 존재하나, 가이드 시뮬레이터는 **원시 지표값 입력 → 점수 변환**으로 차별화

## 변경 파일 목록
| # | 파일 | 변경 유형 |
|---|------|-----------|
| 1 | `frontend/src/lib/guideContent.ts` | **신규 생성** |
| 2 | `frontend/src/pages/GuidePage.tsx` | **신규 생성** |
| 3 | `frontend/src/App.tsx` | 라우트 등록 |
| 4 | `frontend/src/components/AppLayout.tsx` | 메뉴 항목 추가 |
| 5 | `docs/frontend-design.md` | 문서 업데이트 |

## Scope Boundary
### IN
- 가이드 페이지 생성 (6개 Collapse 섹션 + 매수 스코어 시뮬레이터)
- 라우트 및 네비게이션 등록
- 콘텐츠는 docs/ 기반으로 하드코딩 (DB 연동 없음)
- frontend-design.md 문서 업데이트

### OUT (절대 금지)
- `StrategyEditModal.tsx` 수정 금지 — 기존 시뮬레이터 리팩토링 하지 않음
- 새 npm 의존성 추가 금지
- Supabase 쿼리/훅 생성 금지 (정적 페이지)
- 매도(exit) 스코어 시뮬레이터 금지 — 매수 시뮬레이터만 구현
- CSS Modules, Tailwind, styled-components 사용 금지

## 콘텐츠 섹션 구조 (6개 Collapse 패널)

| # | 섹션 제목 | 콘텐츠 소스 | 핵심 내용 |
|---|----------|------------|----------|
| 1 | 전략 개요 | Strategy-Parameters-Guide §1 + Algorithm_Spec intro | 확증 기반 변동성 조절형 평균 회귀, 2단계 구조 비유 (온도계/에어컨) |
| 2 | 매수 진입 조건 | Strategy-Parameters-Guide §3-4 + Algorithm_Spec §1 | 6 factors 테이블, 스코어링 공식, 임계치, 실전 예시 + **스코어 시뮬레이터 임베드** |
| 3 | 매도/청산 규칙 | Algorithm_Spec §2 | 분할 익절 (50% at 중앙선, 50% at 상단), 동적 ATR 손절, 트레일링 스탑 |
| 4 | 시장 레짐 | Algorithm_Spec §1.1 | ADX 추세장 판정, 변동성 폭발 판정, 하이브리드 오프셋 (+15/+25), 99 캡 |
| 5 | 파라미터 상세 | Strategy-Parameters-Guide §2, §5 | BB/RSI/ATR 파라미터 테이블, 프리셋 4종 비교, 한눈에 비교표 |
| 6 | 리스크 관리 | Algorithm_Spec §3 | Kelly Criterion, Half-Kelly, 동시 5종목, 일일 5% 손실 한도, 슬리피지 50bps |

## 스코어 시뮬레이터 상세

### 입력 (6개 raw indicator 값)
| 입력 필드 | UI 컴포넌트 | 범위 | 기본값 | 설명 |
|----------|-----------|------|-------|------|
| 변동성 비율 (vol_ratio) | InputNumber | 0~5, step=0.1 | 1.2 | 단기/장기 변동성 비율 |
| MA 추세 | Select | 상승/하락/데이터부족 | 상승 | 20일선 vs 50일선 |
| ADX | InputNumber | 0~100, step=1 | 18 | 추세 강도 지수 |
| BB 상태 | Select | 하단이탈후복귀/하단이탈중/해당없음 | 하단이탈후복귀 | 볼린저밴드 포지션 |
| RSI 기울기 | InputNumber | -5~10, step=0.1 | 2.1 | RSI 변화 기울기 |
| RSI 레벨 | InputNumber | 0~100, step=1 | 28 | 현재 RSI 값 |

### 추가 입력
| 입력 필드 | UI 컴포넌트 | 범위 | 기본값 | 설명 |
|----------|-----------|------|-------|------|
| 진입 임계치 | InputNumber | 0~100, step=1 | 70 | entry_score_threshold |
| 시장 레짐 | Select | 횡보/추세장/변동성폭발 | 횡보 | regime 선택 → offset 적용 |

### 출력
- 각 요소별 개별 점수 (0~100) — 색상으로 시각화
- 총점 (가중 평균, 가중치 모두 1.0 기본)
- effective threshold (임계치 + 레짐 오프셋, max 99)
- **BUY** (`#52c41a`) / **HOLD** (`#ff4d4f`) 판정

### 스코어링 공식 (engine.py 139-181행과 정확히 동일)
```
volatility_score = max(0, min(100, (3.0 - vol_ratio) / 2.0 * 100))
ma_trend_score = 100 (상승) | 0 (하락) | 50 (데이터부족)
adx_score = max(0, min(100, (40 - adx) / 25 * 100))
bb_recovery_score = 100 (복귀) | 30 (이탈중) | 0 (해당없음)
rsi_slope_score = max(0, min(100, slope / 3.0 * 100))
rsi_level_score = max(0, min(100, (45 - rsi) / 25 * 100))

total_score = (v_score + ma_score + adx_score + bb_score + slope_score + rsi_score) / 6
effective_threshold = min(entry_threshold + regime_offset, 99)
verdict = total_score >= effective_threshold ? "BUY" : "HOLD"
```

---

## TODO

### TODO-1: `frontend/src/lib/guideContent.ts` — 콘텐츠 데이터 파일 생성
- **파일**: `frontend/src/lib/guideContent.ts` (신규 생성)
- **목적**: GuidePage.tsx가 비대해지는 것을 방지하기 위해 콘텐츠 데이터를 별도 파일로 분리
- **작업**: 6개 섹션의 콘텐츠를 구조화된 상수 객체 배열로 내보내기
- **구조**:
```typescript
// 각 섹션의 타입 정의
export interface GuideSection {
  key: string;         // Collapse 패널 key
  title: string;       // 패널 헤더 제목 (한국어)
  content: {
    paragraphs: string[];        // 설명 문단들
    tables?: {                   // 선택적 테이블 데이터
      title?: string;
      columns: { title: string; dataIndex: string; key: string }[];
      data: Record<string, string | number>[];
    }[];
    highlights?: string[];       // Alert/강조 박스 텍스트
    formulas?: string[];         // 공식 설명 (코드블록으로 렌더링)
  };
}

export const GUIDE_SECTIONS: GuideSection[] = [...]
```

- **섹션 1** `key: 'overview'` — 전략 개요
  - `docs/Strategy-Parameters-Guide.md` §1 기반
  - 핵심: 확증 기반 변동성 조절형 평균 회귀 전략
  - 비유 재사용: "온도계 눈금 조정" vs "에어컨 설정 온도 변경"
  - 2단계 구조: 파라미터 설정(지표 계산 방식) → 매수 진입 조건(스코어링)
  - highlight: "이 전략은 가격이 통계적 정상 범위를 벗어났을 때 평균으로 회귀하려는 성질을 이용합니다."

- **섹션 2** `key: 'entry'` — 매수 진입 조건
  - `docs/Strategy-Parameters-Guide.md` §3-4 + `docs/Algorithm_Specification.md` §1 기반
  - 6개 스코어링 요소 테이블 (변동성/MA추세/ADX/BB복귀/RSI기울기/RSI레벨)
  - 가중 평균 공식: `총점 = Σ(w_i × score_i) / Σ(w_i)`
  - 임계치 비교표 (55/70/90) + 백테스트 결과
  - 실전 예시 (RSI=28, ADX=18 → 총점 86점)
  - **⚠️ 이 섹션에 스코어 시뮬레이터 임베드 (GuidePage.tsx에서 렌더링)**

- **섹션 3** `key: 'exit'` — 매도/청산 규칙
  - `docs/Algorithm_Specification.md` §2 기반
  - 분할 익절: 1차 (중앙선 50%), 2차 (상단선 나머지)
  - 동적 손절: ATR × 2.5 기반
  - 트레일링 스탑: 1차 익절 후 최고가 대비 ATR × 2.0 하락 시 전량 매도
  - highlight: "고정 -3% 손절 대신, 시장의 평균적인 흔들림 폭(ATR)을 활용합니다."

- **섹션 4** `key: 'regime'` — 시장 레짐
  - `docs/Algorithm_Specification.md` §1.1 기반
  - 3가지 분류: 횡보(Ranging) / 추세(Trending) / 변동성 폭발(Volatile)
  - 분류 기준: Trending=ADX≥25, Volatile=변동성비율≥2.0, Ranging=나머지
  - 하이브리드 오프셋: 횡보 0 / 추세 +15 / 변동성 +25
  - effective_threshold = min(threshold + offset, 99)
  - highlight: "이전에는 추세/변동성 장세에서 매수를 완전 차단했으나, 현재는 임계치만 높여 더 확실한 기회만 포착합니다."

- **섹션 5** `key: 'params'` — 파라미터 상세
  - `docs/Strategy-Parameters-Guide.md` §2, §5 기반
  - BB/RSI/ATR 파라미터 테이블
  - 프리셋 4종 비교 테이블 (보수적/공격적/횡보장/변동성장세)
  - 한눈에 비교표 (파라미터 설정 vs 매수 진입 조건)

- **섹션 6** `key: 'risk'` — 리스크 관리
  - `docs/Algorithm_Specification.md` §3 기반
  - Kelly Criterion (Half-Kelly 50%), 30회 미만 시 고정 20%
  - 포지션 제한: 종목당 최대 20%, 동시 최대 5종목
  - 일일 손실 한도: 5% → 자동 매매 중단
  - 슬리피지: >50bps(0.5%) → 매매 포기
  - highlight: "봇은 수학적으로 파산 확률을 최소화하도록 설계되었습니다."

- **TOOL**: AntD 6 컴포넌트 사용 전 `context7_query-docs`로 API 확인 필수
- **주의**: 모든 텍스트 한국어. 주석도 한국어.
- **주의**: `docs/Strategy-Parameters-Guide.md`의 비유와 표현을 최대한 재사용

---

### TODO-2: `frontend/src/pages/GuidePage.tsx` — 가이드 페이지 컴포넌트 생성
- **파일**: `frontend/src/pages/GuidePage.tsx` (신규 생성)
- **TOOL**: 구현 전 반드시 `context7_query-docs`로 AntD v6의 Collapse, InputNumber, Select, Card, Table, Alert, Typography, Tag 등 API 확인

#### 작업 A: 페이지 레이아웃
- **참조**: `frontend/src/pages/ReportsPage.tsx` 29-38행 — 페이지 헤더 구조
- 임포트 순서: React → AntD → Icons → 로컬 (`frontend/AGENTS.md` 따르기)
```tsx
import { useState, useMemo } from 'react';
import { Typography, Collapse, Card, Alert, Table, InputNumber, Select, Tag, Divider, Row, Col, Flex, Space } from 'antd';
import { BookOutlined, ... } from '@ant-design/icons';
import { GUIDE_SECTIONS } from '../lib/guideContent';

const { Title, Text, Paragraph } = Typography;
```
- 페이지 헤더: `<Flex align="center" gap={8}>` + `<BookOutlined />` + `<Title level={4}>사용법 가이드</Title>`
- 전체 래퍼: `<div style={{ padding: 24, maxWidth: 960, margin: '0 auto' }}>`

#### 작업 B: Collapse 섹션 렌더링
- `GUIDE_SECTIONS` 순회하여 Collapse items 생성
- 각 패널 내부:
  - `paragraphs` → `<Paragraph>` 컴포넌트
  - `tables` → AntD `<Table>` (columns + dataSource 매핑, `pagination={false}`, `size="small"`)
  - `highlights` → `<Alert type="info" showIcon />` 또는 배경색 카드
  - `formulas` → `<pre style={{ background: '#1a1a1a', padding: 12, borderRadius: 6, overflow: 'auto' }}>` 코드 블록
- `defaultActiveKey={['overview']}` — 전략 개요 패널만 열린 상태로 시작
- 스타일: 다크 테마 일관성 유지 (배경 `#141414`, 패널 헤더 `#1a1a1a`)

#### 작업 C: 스코어 시뮬레이터 (섹션 2 'entry' 패널 내부에 임베드)
- **위치**: 매수 진입 조건 패널의 콘텐츠 아래에 `<Divider>스코어 시뮬레이터</Divider>` 후 렌더링
- **상태 관리**:
```tsx
const [simInputs, setSimInputs] = useState({
  volRatio: 1.2,
  maTrend: 'up' as 'up' | 'down' | 'insufficient',
  adx: 18,
  bbStatus: 'recovered' as 'recovered' | 'below' | 'none',
  rsiSlope: 2.1,
  rsiLevel: 28,
  entryThreshold: 70,
  regime: 'ranging' as 'ranging' | 'trending' | 'volatile',
});
```
- **스코어 계산 (useMemo)** — `engine.py` 139-181행과 정확히 동일:
```tsx
const simResult = useMemo(() => {
  // engine.py line 145: 변동성 스코어
  const volScore = Math.max(0, Math.min(100, (3.0 - simInputs.volRatio) / 2.0 * 100));
  // engine.py line 149: MA 추세 스코어
  const maScore = simInputs.maTrend === 'up' ? 100 : simInputs.maTrend === 'down' ? 0 : 50;
  // engine.py line 153: ADX 스코어
  const adxScore = Math.max(0, Math.min(100, (40 - simInputs.adx) / 25 * 100));
  // engine.py line 157: BB 복귀 스코어
  const bbScore = simInputs.bbStatus === 'recovered' ? 100 : simInputs.bbStatus === 'below' ? 30 : 0;
  // engine.py line 165: RSI 기울기 스코어
  const slopeScore = Math.max(0, Math.min(100, simInputs.rsiSlope / 3.0 * 100));
  // engine.py line 173: RSI 레벨 스코어
  const rsiScore = Math.max(0, Math.min(100, (45 - simInputs.rsiLevel) / 25 * 100));

  const scores = [
    { name: '변동성', score: volScore },
    { name: 'MA 추세', score: maScore },
    { name: 'ADX', score: adxScore },
    { name: 'BB 복귀', score: bbScore },
    { name: 'RSI 기울기', score: slopeScore },
    { name: 'RSI 레벨', score: rsiScore },
  ];
  const totalScore = scores.reduce((a, b) => a + b.score, 0) / 6;

  // engine.py line 114: 레짐 오프셋
  const regimeOffset = simInputs.regime === 'trending' ? 15 :
    simInputs.regime === 'volatile' ? 25 : 0;
  const effectiveThreshold = Math.min(simInputs.entryThreshold + regimeOffset, 99);
  const isBuy = totalScore >= effectiveThreshold;

  return { scores, totalScore, effectiveThreshold, regimeOffset, isBuy };
}, [simInputs]);
```
- **⚠️ 공식 코멘트 필수**: 각 공식 옆에 `// engine.py line XXX` 주석
- **UI 레이아웃**:
  - Card: `<Card size="small" title="매수 스코어 시뮬레이터" style={{ marginTop: 16 }}>`
  - 입력 3행: `<Row gutter={[16, 16]}>`
    - Row 1: 변동성 비율 (InputNumber 0~5 step=0.1) | MA 추세 (Select 상승/하락/데이터부족)
    - Row 2: ADX (InputNumber 0~100 step=1) | BB 상태 (Select 복귀/이탈중/해당없음)
    - Row 3: RSI 기울기 (InputNumber -5~10 step=0.1) | RSI 레벨 (InputNumber 0~100 step=1)
  - `<Divider />`
  - 추가 입력 1행: 진입 임계치 (InputNumber) | 시장 레짐 (Select 횡보/추세장/변동성폭발)
  - 결과 표시:
    - 각 요소별 점수: 6개 Tag 색상 (score≥70: `#52c41a`, ≥40: `#faad14`, <40: `#ff4d4f`)
    - 총점: `<Text style={{ fontSize: 32, fontWeight: 700 }}>`
    - effective threshold: `기본 {threshold} + 레짐 +{offset} = {effective}` 형식
    - 판정: `<Tag color={isBuy ? '#52c41a' : '#ff4d4f'}>` BUY / HOLD

#### 작업 D: default export
```tsx
export default function GuidePage() { ... }
```
- **주의**: `StrategyEditModal.tsx` 수정 금지
- **주의**: 새 npm 의존성 금지
- **주의**: Supabase 훅/쿼리 없음 — 순수 정적 페이지
- **주의**: 파일 400줄 초과 시 시뮬레이터를 `frontend/src/components/ScoreSimulator.tsx`로 분리 고려

---

### TODO-3: `frontend/src/App.tsx` + `frontend/src/components/AppLayout.tsx` — 라우트 및 메뉴 등록

**파일 1**: `frontend/src/App.tsx`
- **작업 A**: lazy import 추가 (line 15 `ReportsPage` 바로 아래)
```tsx
const GuidePage = lazy(() => import('./pages/GuidePage'));
```
- **작업 B**: Route 추가 (line 70 `reports` 라우트 바로 아래)
```tsx
<Route path="guide" element={<GuidePage />} />
```

**파일 2**: `frontend/src/components/AppLayout.tsx`
- **작업 C**: 아이콘 import 추가 (line 19 `FileTextOutlined` 옆에 `BookOutlined` 추가)
```tsx
import { ..., FileTextOutlined, BookOutlined } from '@ant-design/icons';
```
- **작업 D**: menuItems 배열 끝에 항목 추가 (line 36 Reports 항목 바로 아래)
```tsx
{ key: '/guide', icon: <BookOutlined />, label: 'Guide' },
```
- **주의**: 메뉴 label은 영어 `'Guide'` — 기존 메뉴 컨벤션(Dashboard, Trading 등)과 일관성
- **주의**: `BookOutlined` 사용 — `InfoCircleOutlined`은 로그 Tooltip에서 이미 사용 중이므로 시각적 혼동 방지
- **주의**: `QuestionCircleOutlined`도 후보였으나 가이드/문서 의미가 더 명확한 `BookOutlined` 선택

---

### TODO-4: `docs/frontend-design.md` — 문서 업데이트
- **파일**: `docs/frontend-design.md`
- **목적**: AGENTS.md 매핑 테이블에 따라, 신규 페이지 추가 시 `docs/frontend-design.md` 업데이트 필수
- **작업 A**: §1 사이트맵 (line 5-10)에 Guide 페이지 항목 추가
```markdown
* **Guide (가이드):** 매매 전략 설명, 매수/매도 조건 해설, 파라미터 상세, 스코어 시뮬레이터, 시장 레짐, 리스크 관리 규정.
```
- **작업 B**: §2 페이지별 레이아웃에 Guide 섹션 추가 (§2.2 Trading 아래 또는 문서 끝)
```markdown
#### 2.6. Guide (사용법 가이드)

* **구조:** AntD Collapse 기반 접이식 6개 섹션 (전략 개요, 매수 조건, 매도/청산, 시장 레짐, 파라미터 상세, 리스크 관리)
* **인터랙티브:** 매수 스코어 시뮬레이터 — 6개 원시 지표값 입력 → 개별 점수 → 총점 → BUY/HOLD 판정
* **특징:** DB 연동 없는 순수 정적 페이지. 콘텐츠는 하드코딩.
```

---

## Final Verification Wave

### QA-1: TypeScript 컴파일
```bash
npx tsc --noEmit --project frontend/tsconfig.app.json
# Assert: 에러 0개
```

### QA-2: ESLint 검사
```bash
npx eslint frontend/src/pages/GuidePage.tsx frontend/src/lib/guideContent.ts
# Assert: 에러 0개
```

### QA-3: 빌드 성공
```bash
npm run build
# Assert: 빌드 성공, GuidePage lazy chunk 생성
```

### QA-4: 라우트 등록 확인
```bash
grep -n "GuidePage" frontend/src/App.tsx
# Assert: lazy import + Route 존재
```

### QA-5: 메뉴 항목 확인
```bash
grep -n "guide" frontend/src/components/AppLayout.tsx
# Assert: menuItems에 '/guide' 항목 존재
```

### QA-6: 시뮬레이터 공식 정합성 확인
```bash
grep -c "engine.py" frontend/src/pages/GuidePage.tsx
# Assert: 최소 6개 이상 (각 공식 출처 주석)
```

### QA-7: Playwright 페이지 렌더링 검증
- `/guide` 경로로 이동 → 페이지 로드 확인 (에러 없음)
- 6개 Collapse 패널 열기/닫기 동작 확인
- 시뮬레이터 InputNumber에 값 입력 시 총점 실시간 갱신 확인
- 레짐 선택 변경 시 effective threshold 변경 확인
- BUY/HOLD 판정 정상 표시 확인
- 사이드바 Guide 메뉴 항목이 하이라이트 되는지 확인
