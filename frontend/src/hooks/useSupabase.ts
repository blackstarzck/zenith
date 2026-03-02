import { useState, useEffect, useCallback } from 'react';
import { supabase } from '../lib/supabase';
import type {
  Trade,
  DailyStat,
  SystemLog,
  BotState,
  PriceSnapshot,
  BalanceSnapshot,
  HeldPosition,
  DailyReport,
  SentimentInsight,
  SentimentPerformanceDaily,
  DislocationPaperTrade,
  DislocationPaperMetric,
} from '../types/database';
import dayjs from 'dayjs';
import { useRecoveryTick } from './useRecoverySignal';

/** Supabase 채널명 충돌 방지용 카운터 — 동일 훅이 복수 컴포넌트에서 사용될 때 고유성 보장 */
let _chId = 0;

/* ── Trades ─────────────────────────────────────────────── */

export function useTrades(limit = 50) {
  const [trades, setTrades] = useState<Trade[]>([]);
  const [loading, setLoading] = useState(true);
  const recoveryTick = useRecoveryTick();

  const fetch = useCallback(async () => {
    setLoading(true);
    const { data } = await supabase
      .from('trades')
      .select('*')
      .order('created_at', { ascending: false })
      .limit(limit);
    setTrades((data as Trade[]) ?? []);
    setLoading(false);
  }, [limit]);

  useEffect(() => {
    fetch();

    const channel = supabase
      .channel(`trades-${++_chId}`)
      .on(
        'postgres_changes',
        { event: 'INSERT', schema: 'public', table: 'trades' },
        (payload) => {
          setTrades((prev) => [payload.new as Trade, ...prev].slice(0, limit));
        },
      )
      .subscribe();

    return () => {
      supabase.removeChannel(channel);
    };
  }, [fetch, limit, recoveryTick]);

  return { trades, loading, refetch: fetch };
}

/* ── Daily Stats ────────────────────────────────────────── */

export function useDailyStats(days = 30) {
  const [stats, setStats] = useState<DailyStat[]>([]);
  const [loading, setLoading] = useState(true);
  const recoveryTick = useRecoveryTick();

  useEffect(() => {
    (async () => {
      setLoading(true);
      let query = supabase
        .from('daily_stats')
        .select('*')
        .order('stats_date', { ascending: true });
      if (days < 9999) {
        const since = dayjs().subtract(days, 'day').format('YYYY-MM-DD');
        query = query.gte('stats_date', since);
      }
      const { data } = await query;
      setStats((data as DailyStat[]) ?? []);
      setLoading(false);
    })();
  }, [days, recoveryTick]);

  return { stats, loading };
}

/* ── System Logs ────────────────────────────────────────── */

/**
 * 시스템 로그를 날짜별로 조회합니다.
 * @param date - 조회할 날짜 (YYYY-MM-DD). null이면 오늘 날짜.
 * @param limit - 최대 로그 수
 */
export function useSystemLogs(date: string | null = null, limit = 500, enabled = true) {
  const [logs, setLogs] = useState<SystemLog[]>([]);
  const [loading, setLoading] = useState(true);
  const recoveryTick = useRecoveryTick();

  const targetDate = date ?? dayjs().format('YYYY-MM-DD');
  const startOfDay = `${targetDate}T00:00:00.000Z`;
  const endOfDay = `${targetDate}T23:59:59.999Z`;
  const isToday = targetDate === dayjs().format('YYYY-MM-DD');

  useEffect(() => {
    if (!enabled) { setLogs([]); setLoading(false); return; }

    (async () => {
      setLoading(true);
      const { data } = await supabase
        .from('system_logs')
        .select('*')
        .gte('created_at', startOfDay)
        .lte('created_at', endOfDay)
        .order('created_at', { ascending: false })
        .limit(limit);
      setLogs((data as SystemLog[]) ?? []);
      setLoading(false);
    })();

    // 오늘 날짜일 때만 Realtime 구독 (과거 날짜는 새 로그가 안 들어옴)
    if (!enabled || !isToday) return;

    const channel = supabase
      .channel(`logs-${++_chId}`)
      .on(
        'postgres_changes',
        { event: 'INSERT', schema: 'public', table: 'system_logs' },
        (payload) => {
          setLogs((prev) => [payload.new as SystemLog, ...prev].slice(0, limit));
        },
      )
      .subscribe();

    return () => {
      supabase.removeChannel(channel);
    };
  }, [targetDate, startOfDay, endOfDay, isToday, limit, enabled, recoveryTick]);

  return { logs, loading };
}

/* ── Bot State (초기자산 · 상위종목) ─────────────────────── */

export function useBotState() {
  const [botState, setBotState] = useState<BotState | null>(null);
  const [loading, setLoading] = useState(true);
  const recoveryTick = useRecoveryTick();

  useEffect(() => {
    (async () => {
      setLoading(true);
      const { data, error } = await supabase
        .from('bot_state')
        .select('*')
        .eq('id', 1)
        .single();
      if (error) {
        console.error('[useBotState] 초기 조회 실패:', error.message);
      } else if (data) {
        setBotState(data as BotState);
      }
      setLoading(false);
    })();

    const channel = supabase
      .channel(`botstate-${++_chId}`)
      .on(
        'postgres_changes',
        { event: '*', schema: 'public', table: 'bot_state' },
        (payload) => {
          setBotState(payload.new as BotState);
        },
      )
      .subscribe();

    return () => {
      supabase.removeChannel(channel);
    };
  }, [recoveryTick]);

  return { botState, loading };
}

/* ── Price Snapshots (가격 · 손절선 · 익절선) ────────────── */

export function usePriceSnapshots(symbol: string | null, limit = 120) {
  const [snapshots, setSnapshots] = useState<PriceSnapshot[]>([]);
  const [loading, setLoading] = useState(true);
  const recoveryTick = useRecoveryTick();

  const fetch = useCallback(async () => {
    if (!symbol) {
      setSnapshots([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    const { data } = await supabase
      .from('price_snapshots')
      .select('*')
      .eq('symbol', symbol)
      .order('created_at', { ascending: true })
      .limit(limit);
    setSnapshots((data as PriceSnapshot[]) ?? []);
    setLoading(false);
  }, [symbol, limit]);

  useEffect(() => {
    fetch();

    if (!symbol) return;

    const channel = supabase
      .channel(`price-snap-${symbol}-${++_chId}`)
      .on(
        'postgres_changes',
        {
          event: 'INSERT',
          schema: 'public',
          table: 'price_snapshots',
          filter: `symbol=eq.${symbol}`,
        },
        (payload) => {
          setSnapshots((prev) => [...prev, payload.new as PriceSnapshot].slice(-limit));
        },
      )
      .subscribe();

    return () => {
      supabase.removeChannel(channel);
    };
  }, [fetch, symbol, limit, recoveryTick]);

  return { snapshots, loading, refetch: fetch };
}

/**
 * 특정 구간의 가격 스냅샷을 조회합니다.
 * 감성 검증 상세의 코인 차트 렌더링 용도입니다.
 */
export function usePriceSnapshotsRange(
  symbol: string | null,
  startAt: string | null,
  endAt: string | null,
  limit = 600,
) {
  const [snapshots, setSnapshots] = useState<PriceSnapshot[]>([]);
  const [loading, setLoading] = useState(true);
  const recoveryTick = useRecoveryTick();

  const fetch = useCallback(async () => {
    if (!symbol || !startAt || !endAt) {
      setSnapshots([]);
      setLoading(false);
      return;
    }

    setLoading(true);
    const { data } = await supabase
      .from('price_snapshots')
      .select('*')
      .eq('symbol', symbol)
      .gte('created_at', startAt)
      .lte('created_at', endAt)
      .order('created_at', { ascending: true })
      .limit(limit);

    setSnapshots((data as PriceSnapshot[]) ?? []);
    setLoading(false);
  }, [symbol, startAt, endAt, limit]);

  useEffect(() => {
    fetch();
  }, [fetch, recoveryTick]);

  return { snapshots, loading, refetch: fetch };
}

/* ── Held Symbols (보유 종목 목록) ────────────────────────── */

/**
 * 현재 보유 중인 종목 목록을 반환합니다.
 *
 * 1차: price_snapshots (최근 1시간 내 스냅샷 존재 = 보유 후보)
 * 2차: trades 테이블에서 각 후보의 최신 거래를 확인하여 전량 매도된 종목을 제외
 * 실시간: trades INSERT 구독으로 매수/매도 즉시 반영
 */
export function useHeldSymbols() {
  const [symbols, setSymbols] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const recoveryTick = useRecoveryTick();

  useEffect(() => {
    (async () => {
      setLoading(true);

      // 1. price_snapshots에서 최근 1시간 내 종목 후보 추출
      const since = dayjs().subtract(1, 'hour').toISOString();
      const { data: snapData } = await supabase
        .from('price_snapshots')
        .select('symbol')
        .gte('created_at', since);
      const candidates = [...new Set((snapData ?? []).map((d: { symbol: string }) => d.symbol))];

      // 2. 후보 종목의 최신 거래를 확인하여 전량 매도 종목 제외
      let held = candidates;
      if (candidates.length > 0) {
        const { data: tradeData } = await supabase
          .from('trades')
          .select('symbol, side, remaining_volume')
          .in('symbol', candidates)
          .order('created_at', { ascending: false });

        const latestBySymbol = new Map<string, { side: string; remaining_volume: number | null }>();
        for (const t of (tradeData ?? []) as Array<{ symbol: string; side: string; remaining_volume: number | null }>) {
          if (!latestBySymbol.has(t.symbol)) {
            latestBySymbol.set(t.symbol, { side: t.side, remaining_volume: t.remaining_volume });
          }
        }

        held = candidates.filter((sym) => {
          const latest = latestBySymbol.get(sym);
          // 최신 거래가 전량 매도(remaining_volume ≤ 0)이면 보유 아님
          if (latest && latest.side === 'ask' && latest.remaining_volume != null && latest.remaining_volume <= 0) {
            return false;
          }
          return true;
        });
      }

      setSymbols(held.sort());
      setLoading(false);
    })();

    // 실시간: price_snapshots INSERT + trades INSERT 구독
    const channel = supabase
      .channel(`held-sym-${++_chId}`)
      .on(
        'postgres_changes',
        { event: 'INSERT', schema: 'public', table: 'price_snapshots' },
        (payload) => {
          const sym = (payload.new as PriceSnapshot).symbol;
          setSymbols((prev) => {
            if (prev.includes(sym)) return prev;
            return [...prev, sym].sort();
          });
        },
      )
      .on(
        'postgres_changes',
        { event: 'INSERT', schema: 'public', table: 'trades' },
        (payload) => {
          const trade = payload.new as Trade;
          if (trade.side === 'bid') {
            // 매수 → 즉시 보유 목록에 추가
            setSymbols((prev) => {
              if (prev.includes(trade.symbol)) return prev;
              return [...prev, trade.symbol].sort();
            });
          } else if (trade.side === 'ask' && trade.remaining_volume != null && trade.remaining_volume <= 0) {
            // 전량 매도 → 즉시 보유 목록에서 제거
            setSymbols((prev) => prev.filter((s) => s !== trade.symbol));
          }
        },
      )
      .subscribe();

    return () => {
      supabase.removeChannel(channel);
    };
  }, [recoveryTick]);

  return { symbols, loading };
}

/* ── Balance Snapshots (시간별 잔고 스냅샷) ────────────── */

export function useBalanceSnapshots(hours = 24) {
  const [snapshots, setSnapshots] = useState<BalanceSnapshot[]>([]);
  const [loading, setLoading] = useState(true);
  const recoveryTick = useRecoveryTick();

  useEffect(() => {
    (async () => {
      setLoading(true);
      const since = dayjs().subtract(hours, 'hour').toISOString();
      const { data } = await supabase
        .from('balance_snapshots')
        .select('*')
        .gte('created_at', since)
        .order('created_at', { ascending: true });
      setSnapshots((data as BalanceSnapshot[]) ?? []);
      setLoading(false);
    })();
  }, [hours, recoveryTick]);

  return { snapshots, loading };
}

/* ── Held Positions (보유 종목 포지션 정보) ────────────── */

/**
 * 현재 보유 중인 종목의 포지션 정보(매수가, 수량, 투입금액)를 반환합니다.
 * 종목별 최신 거래를 확인하여 전량 매도된 종목은 제외합니다.
 */
export function useHeldPositions(heldSymbols: string[]) {
  const [positions, setPositions] = useState<Map<string, HeldPosition>>(new Map());
  const [loading, setLoading] = useState(true);
  const recoveryTick = useRecoveryTick();
  const symbolsKey = heldSymbols.join(',');

  const fetch = useCallback(async () => {
    if (heldSymbols.length === 0) {
      setPositions(new Map());
      setLoading(false);
      return;
    }
    setLoading(true);
    const { data } = await supabase
      .from('trades')
      .select('*')
      .in('symbol', heldSymbols)
      .order('created_at', { ascending: false })
      .limit(100);

    const posMap = new Map<string, HeldPosition>();
    const fullyLiquidated = new Set<string>();

    for (const trade of (data as Trade[]) ?? []) {
      // 이미 처리된 종목은 스킵
      if (posMap.has(trade.symbol) || fullyLiquidated.has(trade.symbol)) continue;

      if (trade.side === 'ask') {
        if (trade.remaining_volume != null && trade.remaining_volume <= 0) {
          // 전량 매도 완료 → 보유 아님
          fullyLiquidated.add(trade.symbol);
        }
        // 부분 매도(remaining > 0)는 스킵하고 아래의 bid를 탐색
        continue;
      }

      // bid → 매수 포지션 등록
      posMap.set(trade.symbol, {
        symbol: trade.symbol,
        entry_price: trade.price,
        volume: trade.volume,
        amount: trade.amount,
        created_at: trade.created_at,
      });
    }
    setPositions(posMap);
    setLoading(false);
  }, [symbolsKey]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    fetch();

    if (heldSymbols.length === 0) return;

    // 실시간: trades INSERT 구독으로 포지션 변경 즉시 반영
    const channel = supabase
      .channel(`held-pos-${++_chId}`)
      .on(
        'postgres_changes',
        { event: 'INSERT', schema: 'public', table: 'trades' },
        (payload) => {
          const trade = payload.new as Trade;
          if (heldSymbols.includes(trade.symbol)) {
            fetch();
          }
        },
      )
      .subscribe();

    return () => {
      supabase.removeChannel(channel);
    };
  }, [fetch, recoveryTick]); // eslint-disable-line react-hooks/exhaustive-deps

  return { positions, loading };
}

/* ── Latest Snapshots (보유 종목 최신 손절/익절 정보) ──── */

/** 보유 종목별 최신 price_snapshot에서 stop_loss, take_profit을 가져옵니다. */
export function useLatestSnapshots(heldSymbols: string[]) {
  const [snapshots, setSnapshots] = useState<Map<string, PriceSnapshot>>(new Map());
  const [loading, setLoading] = useState(true);
  const recoveryTick = useRecoveryTick();
  const symbolsKey = heldSymbols.join(',');

  const fetch = useCallback(async () => {
    if (heldSymbols.length === 0) {
      setSnapshots(new Map());
      setLoading(false);
      return;
    }
    setLoading(true);
    // 각 종목별 최신 스냅샷 1개씩 조회
    const { data } = await supabase
      .from('price_snapshots')
      .select('*')
      .in('symbol', heldSymbols)
      .order('created_at', { ascending: false })
      .limit(100);

    const snapMap = new Map<string, PriceSnapshot>();
    for (const row of (data as PriceSnapshot[]) ?? []) {
      if (!snapMap.has(row.symbol)) {
        snapMap.set(row.symbol, row);
      }
    }
    setSnapshots(snapMap);
    setLoading(false);
  }, [symbolsKey]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    fetch();

    if (heldSymbols.length === 0) return;

    // 새 스냅샷 도착 시 자동 갱신
    const channel = supabase
      .channel(`latest-snap-${++_chId}`)
      .on(
        'postgres_changes',
        { event: 'INSERT', schema: 'public', table: 'price_snapshots' },
        (payload) => {
          const row = payload.new as PriceSnapshot;
          if (heldSymbols.includes(row.symbol)) {
            setSnapshots((prev) => {
              const next = new Map(prev);
              next.set(row.symbol, row);
              return next;
            });
          }
        },
      )
      .subscribe();

    return () => {
      supabase.removeChannel(channel);
    };
  }, [fetch, recoveryTick]); // eslint-disable-line react-hooks/exhaustive-deps

  return { snapshots, loading };
}


/* ── Daily Reports (일일 분석 리포트) ─────────────────── */

export function useDailyReports(limit = 30) {
  const [reports, setReports] = useState<DailyReport[]>([]);
  const [loading, setLoading] = useState(true);
  const recoveryTick = useRecoveryTick();

  const fetch = useCallback(async () => {
    setLoading(true);
    const { data } = await supabase
      .from('daily_reports')
      .select('id, report_date, total_balance, net_profit, trade_count, win_count, loss_count, created_at')
      .order('report_date', { ascending: false })
      .limit(limit);
    setReports((data as DailyReport[]) ?? []);
    setLoading(false);
  }, [limit]);

  useEffect(() => {
    fetch();

    const channel = supabase
      .channel(`daily-rep-${++_chId}`)
      .on(
        'postgres_changes',
        { event: 'INSERT', schema: 'public', table: 'daily_reports' },
        () => { fetch(); },
      )
      .subscribe();

    return () => {
      supabase.removeChannel(channel);
    };
  }, [fetch, recoveryTick]);

  return { reports, loading, refetch: fetch };
}

export function useDailyReport(reportDate: string | null) {
  const [report, setReport] = useState<DailyReport | null>(null);
  const [loading, setLoading] = useState(false);
  const recoveryTick = useRecoveryTick();

  useEffect(() => {
    if (!reportDate) {
      setReport(null);
      return;
    }
    (async () => {
      setLoading(true);
      const { data } = await supabase
        .from('daily_reports')
        .select('*')
        .eq('report_date', reportDate)
        .single();
      setReport((data as DailyReport) ?? null);
      setLoading(false);
    })();
  }, [reportDate, recoveryTick]);

  return { report, loading };
}

/* ── Sentiment Insights (뉴스 감성 분석) ──────────────── */

export function useSentimentInsights(limit = 30) {
  const [insights, setInsights] = useState<SentimentInsight[]>([]);
  const [loading, setLoading] = useState(true);
  const recoveryTick = useRecoveryTick();

  const fetch = useCallback(async () => {
    setLoading(true);
    const { data } = await supabase
      .from('sentiment_insights')
      .select('*')
      .order('created_at', { ascending: false })
      .limit(limit);
    setInsights((data as SentimentInsight[]) ?? []);
    setLoading(false);
  }, [limit]);

  useEffect(() => {
    fetch();

    const channel = supabase
      .channel('sentiment-insights-realtime')
      .on(
        'postgres_changes',
        { event: 'INSERT', schema: 'public', table: 'sentiment_insights' },
        (payload) => {
          setInsights((prev) => [payload.new as SentimentInsight, ...prev].slice(0, limit));
        },
      )
      .on(
        'postgres_changes',
        { event: 'UPDATE', schema: 'public', table: 'sentiment_insights' },
        (payload) => {
          setInsights((prev) =>
            prev.map((item) =>
              item.id === (payload.new as SentimentInsight).id
                ? (payload.new as SentimentInsight)
                : item,
            ),
          );
        },
      )
      .subscribe();

    return () => {
      supabase.removeChannel(channel);
    };
  }, [fetch, limit, recoveryTick]);

  return { insights, loading, refetch: fetch };
}

/* ── Sentiment Performance Daily (감성 검증 일일 집계) ──────────────── */

export function useSentimentPerformanceDaily(days = 30, currency: string | null = null) {
  const [items, setItems] = useState<SentimentPerformanceDaily[]>([]);
  const [loading, setLoading] = useState(true);
  const recoveryTick = useRecoveryTick();

  const fetch = useCallback(async () => {
    setLoading(true);
    let query = supabase
      .from('sentiment_performance_daily')
      .select('*')
      .order('stats_date', { ascending: true });
    if (days < 9999) {
      const since = dayjs().subtract(days, 'day').format('YYYY-MM-DD');
      query = query.gte('stats_date', since);
    }
    if (currency) {
      query = query.eq('currency', currency);
    }
    const { data } = await query;
    setItems((data as SentimentPerformanceDaily[]) ?? []);
    setLoading(false);
  }, [days, currency]);

  useEffect(() => {
    fetch();

    const channel = supabase
      .channel(`sentiment-performance-${++_chId}`)
      .on(
        'postgres_changes',
        { event: '*', schema: 'public', table: 'sentiment_performance_daily' },
        () => {
          fetch();
        },
      )
      .subscribe();

    return () => {
      supabase.removeChannel(channel);
    };
  }, [fetch, recoveryTick]);

  return { items, loading, refetch: fetch };
}

/* ── Dislocation Paper Trades (괴리 모의매매 체결 로그) ──────────────── */

export function useDislocationPaperTrades(limit = 300) {
  const [items, setItems] = useState<DislocationPaperTrade[]>([]);
  const [loading, setLoading] = useState(true);
  const recoveryTick = useRecoveryTick();

  const fetch = useCallback(async () => {
    setLoading(true);
    const { data } = await supabase
      .from('dislocation_paper_trades')
      .select('*')
      .order('created_at', { ascending: false })
      .limit(limit);
    setItems((data as DislocationPaperTrade[]) ?? []);
    setLoading(false);
  }, [limit]);

  useEffect(() => {
    fetch();

    const channel = supabase
      .channel(`dislocation-paper-trades-${++_chId}`)
      .on(
        'postgres_changes',
        { event: 'INSERT', schema: 'public', table: 'dislocation_paper_trades' },
        (payload) => {
          setItems((prev) => [payload.new as DislocationPaperTrade, ...prev].slice(0, limit));
        },
      )
      .subscribe();

    return () => {
      supabase.removeChannel(channel);
    };
  }, [fetch, limit, recoveryTick]);

  return { items, loading, refetch: fetch };
}

/* ── Dislocation Paper Metrics (괴리 모의매매 분석 지표) ──────────────── */

export function useDislocationPaperMetrics(limit = 1000) {
  const [items, setItems] = useState<DislocationPaperMetric[]>([]);
  const [loading, setLoading] = useState(true);
  const recoveryTick = useRecoveryTick();

  const fetch = useCallback(async () => {
    setLoading(true);
    const { data } = await supabase
      .from('dislocation_paper_metrics')
      .select('*')
      .order('created_at', { ascending: false })
      .limit(limit);
    setItems((data as DislocationPaperMetric[]) ?? []);
    setLoading(false);
  }, [limit]);

  useEffect(() => {
    fetch();

    const channel = supabase
      .channel(`dislocation-paper-metrics-${++_chId}`)
      .on(
        'postgres_changes',
        { event: 'INSERT', schema: 'public', table: 'dislocation_paper_metrics' },
        (payload) => {
          setItems((prev) => [payload.new as DislocationPaperMetric, ...prev].slice(0, limit));
        },
      )
      .subscribe();

    return () => {
      supabase.removeChannel(channel);
    };
  }, [fetch, limit, recoveryTick]);

  return { items, loading, refetch: fetch };
}
