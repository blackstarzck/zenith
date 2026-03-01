# Plan: Mermaid 다이어그램 가독성 개선 (팬/줌 + 간격 튜닝)

## 목표
Guide 페이지의 큰 Mermaid 다이어그램(특히 entry[0] 36노드, exit[0] 27노드)에서 도형 안 텍스트가 읽히지 않는 문제 해결.
`useMaxWidth: false`로 자연 크기 렌더링 + `react-zoom-pan-pinch`로 팬/줌 인터랙션 제공.

## 근본 원인
- Mermaid 기본 `useMaxWidth: true`가 SVG에 `max-width: 100%` + `viewBox`를 적용
- 36노드 다이어그램이 ~2000px 자연폭 → 880px 유효폭으로 축소 → 텍스트 읽기 불가

## 범위
- **IN**: MermaidDiagram 컴포넌트 개선, mermaid 설정 튜닝, react-zoom-pan-pinch 통합, vite 청크 업데이트
- **OUT**: 다이어그램 내용(guideDiagrams.ts) 수정, GuidePage 레이아웃 변경, 풀스크린 모드, 미니맵

## 수정 대상 파일
| 파일 | 변경 유형 |
|------|-----------|
| `frontend/package.json` | react-zoom-pan-pinch 의존성 추가 |
| `frontend/src/components/MermaidDiagram.tsx` | mermaid 설정 변경 + 줌 래퍼 + 커스텀 컨트롤 |
| `frontend/vite.config.ts` | vendor-mermaid 청크에 react-zoom-pan-pinch 추가 |

## 기술 결정 사항

### 1. Mermaid 설정 변경 (ensureInit 함수)
```typescript
mermaid.initialize({
  startOnLoad: false,
  theme: 'dark',
  themeVariables: {
    darkMode: true,
    background: '#141414',
    primaryColor: '#177ddc',
    primaryTextColor: '#e8e8e8',
    primaryBorderColor: '#434343',
    lineColor: '#595959',
    secondaryColor: '#1f1f1f',
    tertiaryColor: '#262626',
    fontSize: '16px',          // ← 추가
  },
  flowchart: {
    htmlLabels: true,
    curve: 'basis',
    useMaxWidth: false,        // ← 추가: 자연 크기 렌더링
    nodeSpacing: 100,          // ← 추가: 노드 간 수평 간격 (기본 ~50)
    rankSpacing: 100,          // ← 추가: 노드 간 수직 간격 (기본 ~50)
  },
  securityLevel: 'loose',
});
```

### 2. react-zoom-pan-pinch 통합 구조
```
TransformWrapper (initialScale=자동계산, minScale=0.3, maxScale=2, wheel={{ disabled: true }})
  ├── ZoomControls (position: absolute, top-right, 다크 테마)
  │     ├── ZoomInOutlined 버튼
  │     ├── ZoomOutOutlined 버튼
  │     └── ExpandOutlined (리셋) 버튼
  └── TransformComponent (wrapperStyle, contentStyle)
        └── <div dangerouslySetInnerHTML={{ __html: svg }} />
```

### 3. 핵심 가드레일 (Metis 검증)
- **MUST**: `wheel={{ disabled: true }}` — 스크롤 트랩 방지 (마우스휠이 줌이 아닌 페이지 스크롤)
- **MUST**: `overflow: auto` 제거 → `overflow: hidden` + 고정 높이(~500px) 컨테이너
- **MUST**: `initialScale`을 컨테이너/SVG 비율로 계산하거나 `centerOnInit={true}` 사용 — 초기 로드 시 잘린 모서리가 아닌 전체가 보여야 함
- **MUST**: innerHTML div를 TransformComponent 안에 네스트 (TransformComponent 자체에 dangerouslySetInnerHTML 불가)
- **MUST**: react-zoom-pan-pinch를 기존 `vendor-mermaid` 청크에 합침 (별도 청크 불필요, ~12KB gzipped)
- **MUST NOT**: guideDiagrams.ts 다이어그램 정의 수정 — 렌더링 개선이지 내용 변경 아님
- **MUST NOT**: 다이어그램별 조건부 줌 로직 — 모든 다이어그램에 균일 적용 (심플하게)

### 4. 줌 컨트롤 스타일 (다크 테마)
```typescript
// AntD 아이콘: ZoomInOutlined, ZoomOutOutlined, ExpandOutlined
// 컨트롤 컨테이너: position absolute, top: 8, right: 8, z-index: 10
// 버튼 스타일:
{
  background: '#1f1f1f',
  border: '1px solid #434343',
  color: '#e8e8e8',
  borderRadius: 4,
  padding: '4px 8px',
  cursor: 'pointer',
  display: 'flex',
  alignItems: 'center',
  gap: 4,
}
// hover: background '#303030'
```

### 5. 초기 스케일 계산
SVG 렌더링 후 자연폭을 측정하여 컨테이너 대비 축소율 계산:
```typescript
// SVG 렌더링 후 자연 크기 측정
const tempDiv = document.createElement('div');
tempDiv.innerHTML = rendered;
const svgEl = tempDiv.querySelector('svg');
const naturalWidth = svgEl?.getAttribute('width') 
  ? parseFloat(svgEl.getAttribute('width')!) 
  : svgEl?.getBoundingClientRect().width ?? 800;

// 컨테이너 폭 대비 스케일 (최대 1.0)
const containerWidth = containerRef.current?.clientWidth ?? 880;
const fitScale = Math.min(1, containerWidth / naturalWidth);
setInitialScale(fitScale);
```
단, `react-zoom-pan-pinch`의 `initialScale` prop은 마운트 시점에만 적용되므로 SVG가 준비된 후 `ref.current?.centerView(fitScale)` 호출이 더 안정적.

---

## Tasks

### Task 1: react-zoom-pan-pinch 설치 및 청크 등록

**카테고리**: `quick`
**스킬**: `[]`

**작업 내용**:
1. `frontend/` 디렉토리에서 `npm install react-zoom-pan-pinch` 실행
2. `frontend/vite.config.ts`에서 `'vendor-mermaid': ['mermaid']`를 `'vendor-mermaid': ['mermaid', 'react-zoom-pan-pinch']`로 변경

**검증**:
- `frontend/package.json`에 `react-zoom-pan-pinch` 의존성 존재 확인
- `frontend/vite.config.ts`에서 vendor-mermaid 청크에 두 패키지 모두 포함 확인

---

### Task 2: MermaidDiagram 컴포넌트 개선 — mermaid 설정 + 팬/줌 래퍼

**카테고리**: `visual-engineering`
**스킬**: `['frontend-ui-ux']`
**의존**: Task 1

**작업 내용**:

**파일**: `frontend/src/components/MermaidDiagram.tsx`

#### 2-1. 임포트 추가
```typescript
import { useRef, useEffect, useState, useCallback } from 'react';
import mermaid from 'mermaid';
import { Alert, Spin } from 'antd';
import { ZoomInOutlined, ZoomOutOutlined, ExpandOutlined } from '@ant-design/icons';
import { TransformWrapper, TransformComponent } from 'react-zoom-pan-pinch';
import type { ReactZoomPanPinchRef } from 'react-zoom-pan-pinch';
```
- ⚠️ `context7_query-docs`로 `react-zoom-pan-pinch` 최신 API 확인 필수 (TransformWrapper props, useControls vs ref 패턴)

#### 2-2. ensureInit() 함수 — mermaid 설정 변경
기존 `mermaid.initialize()` 호출에 아래 변경 적용:
- `themeVariables`에 `fontSize: '16px'` 추가
- `flowchart` 객체에 `useMaxWidth: false`, `nodeSpacing: 100`, `rankSpacing: 100` 추가
- 기존 `htmlLabels: true`, `curve: 'basis'` 유지

#### 2-3. 컴포넌트 상태 추가
기존 `svg`, `loading`, `error` 상태에 추가:
```typescript
const [fitScale, setFitScale] = useState(1);
const containerRef = useRef<HTMLDivElement>(null);
const zoomRef = useRef<ReactZoomPanPinchRef>(null);
```

#### 2-4. useEffect — SVG 렌더링 후 스케일 계산
기존 useEffect 내, `setSvg(rendered)` 직후:
```typescript
// SVG 자연 크기 측정
const tempDiv = document.createElement('div');
tempDiv.style.position = 'absolute';
tempDiv.style.visibility = 'hidden';
document.body.appendChild(tempDiv);
tempDiv.innerHTML = rendered;
const svgEl = tempDiv.querySelector('svg');
const naturalWidth = svgEl ? parseFloat(svgEl.getAttribute('width') || '800') : 800;
document.body.removeChild(tempDiv);

// 컨테이너 폭 대비 피팅 스케일 계산
const cw = containerRef.current?.clientWidth ?? 880;
const scale = Math.min(1, (cw - 32) / naturalWidth);  // 32 = 패딩 여유
setFitScale(scale);
```

#### 2-5. centerView 콜백
```typescript
const handleCenterView = useCallback(() => {
  zoomRef.current?.centerView(fitScale);
}, [fitScale]);
```
SVG 렌더링 완료 후 한 번 호출 (useEffect 내에서 setTimeout 0으로 래핑):
```typescript
// setSvg 및 setFitScale 이후
requestAnimationFrame(() => {
  zoomRef.current?.centerView(scale);
});
```

#### 2-6. ZoomControls 내부 컴포넌트
MermaidDiagram 컴포넌트 내부에 정의:
```tsx
function ZoomControls({ onCenter }: { onCenter: () => void }) {
  return null; // 아래 JSX 구조로 교체
}
```
실제로는 `TransformWrapper` 내부에서 `useControls()` 훅이 아닌, `ref` 패턴 사용:
```tsx
<div style={{
  position: 'absolute',
  top: 8,
  right: 8,
  zIndex: 10,
  display: 'flex',
  gap: 4,
}}>
  <button
    onClick={() => zoomRef.current?.zoomIn()}
    style={controlButtonStyle}
    title="확대"
  >
    <ZoomInOutlined />
  </button>
  <button
    onClick={() => zoomRef.current?.zoomOut()}
    style={controlButtonStyle}
    title="축소"
  >
    <ZoomOutOutlined />
  </button>
  <button
    onClick={handleCenterView}
    style={controlButtonStyle}
    title="맞춤 보기"
  >
    <ExpandOutlined />
  </button>
</div>
```

`controlButtonStyle` 상수:
```typescript
const controlButtonStyle: React.CSSProperties = {
  background: '#1f1f1f',
  border: '1px solid #434343',
  color: '#e8e8e8',
  borderRadius: 4,
  padding: '4px 8px',
  cursor: 'pointer',
  display: 'flex',
  alignItems: 'center',
  fontSize: 14,
};
```

#### 2-7. JSX 반환부 교체
기존 성공 상태 return (line 83-94)을 교체:

```tsx
return (
  <div
    ref={containerRef}
    style={{
      background: '#141414',
      borderRadius: 8,
      position: 'relative',
      overflow: 'hidden',   // ← auto → hidden 변경
      height: 500,          // ← 고정 높이
    }}
  >
    {/* 줌 컨트롤 */}
    <div style={{ position: 'absolute', top: 8, right: 8, zIndex: 10, display: 'flex', gap: 4 }}>
      <button onClick={() => zoomRef.current?.zoomIn()} style={controlButtonStyle} title="확대">
        <ZoomInOutlined />
      </button>
      <button onClick={() => zoomRef.current?.zoomOut()} style={controlButtonStyle} title="축소">
        <ZoomOutOutlined />
      </button>
      <button onClick={handleCenterView} style={controlButtonStyle} title="맞춤 보기">
        <ExpandOutlined />
      </button>
    </div>

    {/* 팬/줌 래퍼 */}
    <TransformWrapper
      ref={zoomRef}
      initialScale={fitScale}
      minScale={0.3}
      maxScale={2}
      centerOnInit={true}
      wheel={{ disabled: true }}
    >
      <TransformComponent
        wrapperStyle={{ width: '100%', height: '100%' }}
        contentStyle={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
      >
        <div dangerouslySetInnerHTML={{ __html: svg }} />
      </TransformComponent>
    </TransformWrapper>
  </div>
);
```

**핵심 체크포인트**:
- ⚠️ `wheel={{ disabled: true }}` 반드시 포함 — 스크롤 트랩 방지
- ⚠️ `overflow: 'hidden'` 사용 (auto 아님) — 팬/줌이 스크롤바를 대체
- ⚠️ `dangerouslySetInnerHTML` div는 TransformComponent **안에** 네스트
- ⚠️ 기존 `textAlign: 'center'`, `padding: 16` 제거 — TransformComponent contentStyle이 대체

**검증**:
1. `cd frontend && npx tsc -b --noEmit` — 0 에러
2. `cd frontend && npx eslint .` — 0 신규 에러
3. `cd frontend && npx vite build` — 성공, vendor-mermaid 청크 출력 확인
4. dev-browser 또는 playwright로 Guide 페이지 열기:
   - "전략 개요" 패널 열기 → "시스템 아키텍처 개요" 다이어그램 정상 렌더링 확인
   - "매수 진입 조건" 패널 열기 → 36노드 다이어그램 텍스트 읽히는지 확인
   - 줌 인/아웃 버튼 클릭 → 동작 확인
   - ExpandOutlined 버튼 → 전체 맞춤 보기 복원 확인
   - 다이어그램 위에서 마우스 휠 → 페이지 스크롤 (줌 아님) 확인
   - 다이어그램 드래그 → 팬 동작 확인
   - 5개 다이어그램 모두 에러 없이 렌더링 확인

---

## Final Verification Wave

모든 Task 완료 후:
1. TypeScript: `cd frontend && npx tsc -b --noEmit` — 0 에러
2. ESLint: `cd frontend && npx eslint .` — 0 에러  
3. Build: `cd frontend && npx vite build` — 성공
4. 시각 검증: Playwright 스크린샷으로 entry 다이어그램 텍스트 가독성 확인
5. Git 커밋 + 푸시 (`feat: Mermaid 다이어그램 팬/줌 및 가독성 개선`)
