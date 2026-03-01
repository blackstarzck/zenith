import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import './index.css';
import App from './App';

// 개발 모드에서 Performance API 버퍼 오버플로우 방지
// React StrictMode + Profiler가 performance.mark()/measure()를 무한 누적하여
// 장시간 실행 시 "Out of Memory" 크래시 발생 (DataCloneError)
if (import.meta.env.DEV) {
  performance.setResourceTimingBufferSize(50);
  setInterval(() => {
    performance.clearMarks();
    performance.clearMeasures();
    performance.clearResourceTimings();
  }, 60_000); // 1분마다 정리
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
