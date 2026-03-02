import { useEffect, useState, useRef, useCallback } from 'react';
import mermaid from 'mermaid';
import { Alert, Spin } from 'antd';
import { TransformWrapper, TransformComponent } from 'react-zoom-pan-pinch';
import type { ReactZoomPanPinchRef } from 'react-zoom-pan-pinch';
import { ZoomInOutlined, ZoomOutOutlined, ExpandOutlined } from '@ant-design/icons';

/** mermaid 전역 초기화 플래그 */
let initialized = false;

/** 렌더 ID 카운터 (고유 ID 보장) */
let renderCounter = 0;

/** Mermaid 전역 설정 초기화 (다크 테마) */
function ensureInit() {
  if (initialized) return;
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
      fontSize: '16px',
    },
    flowchart: { htmlLabels: true, curve: 'basis', useMaxWidth: false, nodeSpacing: 100, rankSpacing: 100 },
    securityLevel: 'loose',
  });
  initialized = true;
}

interface MermaidDiagramProps {
  /** Mermaid 다이어그램 정의 코드 */
  chart: string;
}

/** Mermaid 다이어그램 렌더러 (다크 테마 전용) */
export default function MermaidDiagram({ chart }: MermaidDiagramProps) {
  const [svg, setSvg] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [fitScale, setFitScale] = useState(1);
  const containerRef = useRef<HTMLDivElement>(null);
  const zoomRef = useRef<ReactZoomPanPinchRef>(null);

  useEffect(() => {
    ensureInit();
    let cancelled = false;
    const renderId = `mermaid-${Date.now()}-${++renderCounter}`;

    (async () => {
      try {
        const { svg: rendered } = await mermaid.render(renderId, chart);
        if (!cancelled) {
          setSvg(rendered);
          setError(null);

          // SVG 자연 크기 측정
          const tempDiv = document.createElement('div');
          tempDiv.style.position = 'absolute';
          tempDiv.style.visibility = 'hidden';
          document.body.appendChild(tempDiv);
          tempDiv.innerHTML = rendered;
          const svgEl = tempDiv.querySelector('svg');
          const naturalWidth = svgEl ? parseFloat(svgEl.getAttribute('width') || '800') : 800;
          document.body.removeChild(tempDiv);

          const cw = containerRef.current?.clientWidth ?? 880;
          const scale = Math.min(1, (cw - 32) / naturalWidth);
          setFitScale(scale);

          // 렌더링 완료 후 센터뷰
          requestAnimationFrame(() => {
            zoomRef.current?.centerView(scale);
          });
        }
      } catch (err) {
        // 렌더링 실패 시 임시 DOM 요소 정리
        document.getElementById(renderId)?.remove();
        if (!cancelled) {
          setError(err instanceof Error ? err.message : '다이어그램 렌더링 실패');
          setSvg('');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => { cancelled = true; };
  }, [chart]);

  const handleCenterView = useCallback(() => {
    zoomRef.current?.centerView(fitScale);
  }, [fitScale]);

  if (error) {
    return <Alert type="error" showIcon title="다이어그램 렌더링 오류" description={error} />;
  }

  if (loading || !svg) {
    return (
      <div style={{ textAlign: 'center', padding: 32 }}>
        <Spin tip="다이어그램 로딩 중..." />
      </div>
    );
  }

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

  return (
    <div ref={containerRef} style={{
      background: '#141414', borderRadius: 8,
      position: 'relative', overflow: 'hidden', height: 500,
    }}>
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
      <TransformWrapper ref={zoomRef} initialScale={fitScale} minScale={0.3} maxScale={2}
        centerOnInit={true} wheel={{ disabled: true }}
        limitToBounds={false} alignmentAnimation={{ disabled: true }}>
        <TransformComponent wrapperStyle={{ width: '100%', height: '100%' }}>
          <div dangerouslySetInnerHTML={{ __html: svg }} />
        </TransformComponent>
      </TransformWrapper>
    </div>
  );
}
