import { useEffect, useMemo, useRef, useState } from 'react';

export interface BinanceTickerData {
  symbol: string;
  price: number;
  timestamp: number;
}

function toBinanceSymbol(upbitMarket: string): string {
  const parts = upbitMarket.split('-');
  const base = parts.length > 1 ? parts[1] : upbitMarket;
  return `${base.toUpperCase()}USDT`;
}

/**
 * 바이낸스 WebSocket 스트림으로 현재가(USDT)를 실시간 수신합니다.
 * - CORS 제약이 없는 WebSocket 방식을 사용합니다.
 * - 공개 시세 조회만 사용하므로 API 키가 필요하지 않습니다.
 * - 리렌더 빈도를 제어하기 위해 수신 데이터를 ref에 누적 후 주기적으로 flush합니다.
 */
export function useBinanceTicker(upbitMarkets: string[], flushIntervalMs = 1500) {
  const [tickers, setTickers] = useState<Map<string, BinanceTickerData>>(new Map());
  const symbols = useMemo(() => upbitMarkets.map(toBinanceSymbol), [upbitMarkets]);
  const symbolsKey = useMemo(() => [...symbols].sort().join(','), [symbols]);
  const tickersRef = useRef<Map<string, BinanceTickerData>>(new Map());

  useEffect(() => {
    if (!symbolsKey) return;

    const currentSymbols = symbolsKey.split(',');
    const streams = currentSymbols.map((s) => `${s.toLowerCase()}@miniTicker`).join('/');
    const wsUrl = `wss://stream.binance.com:9443/stream?streams=${streams}`;

    let ws: WebSocket | null = null;
    let disposed = false;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

    // 심볼 변경 시 이전 데이터 초기화
    tickersRef.current = new Map();

    const connect = () => {
      if (disposed) return;
      ws = new WebSocket(wsUrl);

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          const data = msg.data;
          if (!data?.s || data?.c == null) return;
          const price = Number(data.c);
          if (!Number.isFinite(price) || price <= 0) return;
          tickersRef.current.set(data.s, {
            symbol: data.s,
            price,
            timestamp: Date.now(),
          });
        } catch {
          // 파싱 실패는 다음 메시지에서 자동 복구
        }
      };

      ws.onclose = () => {
        if (!disposed) {
          // 연결 끊김 시 3초 후 자동 재연결
          reconnectTimer = setTimeout(connect, 3000);
        }
      };

      ws.onerror = () => {
        ws?.close();
      };
    };

    connect();

    // 주기적으로 누적된 데이터를 state에 반영 (리렌더 빈도 제어)
    const flushTimer = setInterval(() => {
      if (tickersRef.current.size > 0) {
        setTickers(new Map(tickersRef.current));
      }
    }, flushIntervalMs);

    return () => {
      disposed = true;
      ws?.close();
      if (reconnectTimer) clearTimeout(reconnectTimer);
      clearInterval(flushTimer);
    };
  }, [symbolsKey, flushIntervalMs]);

  return { tickers };
}
