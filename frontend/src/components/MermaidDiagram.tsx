import { useEffect, useState } from 'react';
import mermaid from 'mermaid';
import { Alert, Spin } from 'antd';

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
    },
    flowchart: { htmlLabels: true, curve: 'basis' },
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

  if (error) {
    return <Alert type="error" showIcon message="다이어그램 렌더링 오류" description={error} />;
  }

  if (loading || !svg) {
    return (
      <div style={{ textAlign: 'center', padding: 32 }}>
        <Spin tip="다이어그램 로딩 중..." />
      </div>
    );
  }

  return (
    <div
      style={{
        background: '#141414',
        borderRadius: 8,
        padding: 16,
        overflow: 'auto',
        textAlign: 'center',
      }}
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
}
