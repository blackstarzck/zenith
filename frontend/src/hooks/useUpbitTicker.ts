/**
 * 업비트 WebSocket 실시간 시세 훅.
 * wss://api.upbit.com/websocket/v1 에 접속하여
 * 지정 종목의 현재가를 실시간으로 수신합니다.
 */

import { useState, useEffect, useRef, useCallback } from 'react';

export interface TickerData {
  /** 현재가 */
  trade_price: number;
  /** 전일 종가 */
  prev_closing_price: number;
  /** 전일 대비 변화율 (signed_change_rate * 100 → %) */
  change_rate: number;
  /** 전일 대비 변화량 */
  change_price: number;
  /** 전일 대비 구분: RISE | EVEN | FALL */
  change: 'RISE' | 'EVEN' | 'FALL';
  /** 수신 시각 (ms) */
  timestamp: number;
}

const WS_URL = 'wss://api.upbit.com/websocket/v1';
const RECONNECT_DELAY = 3_000;

/**
 * 업비트 WebSocket 실시간 시세를 구독합니다.
 * @param symbols KRW-BTC 형태의 종목 배열
 * @returns Map<symbol, TickerData>
 */
export function useUpbitTicker(symbols: string[]) {
  const [tickers, setTickers] = useState<Map<string, TickerData>>(new Map());
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const symbolsKey = symbols.join(',');

  const connect = useCallback(() => {
    if (symbols.length === 0) return;

    // 기존 연결 정리
    if (wsRef.current) {
      wsRef.current.onclose = null;
      wsRef.current.close();
    }

    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;

    ws.binaryType = 'arraybuffer';

    ws.onopen = () => {
      const payload = JSON.stringify([
        { ticket: `zenith-ticker-${Date.now()}` },
        { type: 'ticker', codes: symbols, isOnlyRealtime: false },
      ]);
      ws.send(payload);
    };

    ws.onmessage = (event) => {
      try {
        // 업비트 WS는 arraybuffer로 데이터를 보냄
        const text =
          typeof event.data === 'string'
            ? event.data
            : new TextDecoder('utf-8').decode(event.data as ArrayBuffer);

        const data = JSON.parse(text);
        if (!data.code || data.type !== 'ticker') return;

        const ticker: TickerData = {
          trade_price: data.trade_price,
          prev_closing_price: data.prev_closing_price,
          change_rate: data.signed_change_rate * 100,
          change_price: data.signed_change_price,
          change: data.change,
          timestamp: data.timestamp,
        };

        setTickers((prev) => {
          const next = new Map(prev);
          next.set(data.code as string, ticker);
          return next;
        });
      } catch {
        // 파싱 실패 무시
      }
    };

    ws.onclose = () => {
      // 자동 재연결
      reconnectTimer.current = setTimeout(connect, RECONNECT_DELAY);
    };

    ws.onerror = () => {
      ws.close();
    };
  }, [symbolsKey]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    connect();

    return () => {
      clearTimeout(reconnectTimer.current);
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [connect]);

  return { tickers };
}
