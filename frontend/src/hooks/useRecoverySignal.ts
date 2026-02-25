import { createContext, useContext, useState, useEffect, useRef, useCallback } from 'react';
import { createElement, type ReactNode } from 'react';

/**
 * 네트워크 복구 감지 Context
 *
 * - `online` 이벤트: 브라우저가 오프라인→온라인 전환 시
 * - `visibilitychange`: 탭이 백그라운드→포그라운드 전환 시
 * - 1 초 디바운스로 연속 이벤트 무시
 *
 * 각 useSupabase 훅에서 useRecoveryTick() 을 호출하여
 * recoveryTick 이 변할 때마다 데이터를 다시 fetch 합니다.
 */

const RecoveryContext = createContext<number>(0);

export function RecoveryProvider({ children }: { children: ReactNode }) {
  const [recoveryTick, setRecoveryTick] = useState(0);
  const cooldownRef = useRef(false);

  const bump = useCallback(() => {
    if (cooldownRef.current) return;
    cooldownRef.current = true;
    setRecoveryTick((t) => t + 1);
    setTimeout(() => {
      cooldownRef.current = false;
    }, 1000);
  }, []);

  useEffect(() => {
    const onOnline = () => {
      console.info('[Recovery] 네트워크 복구 감지 (online)');
      bump();
    };

    const onVisibility = () => {
      if (document.visibilityState === 'visible') {
        console.info('[Recovery] 탭 포커스 복구 감지 (visibilitychange)');
        bump();
      }
    };

    window.addEventListener('online', onOnline);
    document.addEventListener('visibilitychange', onVisibility);

    return () => {
      window.removeEventListener('online', onOnline);
      document.removeEventListener('visibilitychange', onVisibility);
    };
  }, [bump]);

  return createElement(RecoveryContext.Provider, { value: recoveryTick }, children);
}

/** 현재 recovery tick 값을 반환합니다. useEffect deps 에 추가하면 복구 시 자동 re-fetch 됩니다. */
export function useRecoveryTick(): number {
  return useContext(RecoveryContext);
}
