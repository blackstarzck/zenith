import { useState, useEffect, useCallback } from 'react';
import { supabase } from '../lib/supabase';
import type { Trade, DailyStat, SystemLog, BotState, PriceSnapshot, BalanceSnapshot, HeldPosition, DailyReport } from '../types/database';
import dayjs from 'dayjs';

/* ── Trades ─────────────────────────────────────────────── */

export function useTrades(limit = 50) {
  const [trades, setTrades] = useState<Trade[]>([]);
  const [loading, setLoading] = useState(true);

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
      .channel('trades-realtime')
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
  }, [fetch, limit]);

  return { trades, loading, refetch: fetch };
}

/* ── Daily Stats ────────────────────────────────────────── */

export function useDailyStats(days = 30) {
  const [stats, setStats] = useState<DailyStat[]>([]);
  const [loading, setLoading] = useState(true);

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
  }, [days]);

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
      .channel('logs-realtime')
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
  }, [targetDate, startOfDay, endOfDay, isToday, limit, enabled]);

  return { logs, loading };
}

/* ── Bot State (초기자산 · 상위종목) ─────────────────────── */

export function useBotState() {
  const [botState, setBotState] = useState<BotState | null>(null);
  const [loading, setLoading] = useState(true);

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
      .channel('botstate-realtime')
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
  }, []);

  return { botState, loading };
}

/* ── Price Snapshots (가격 · 손절선 · 익절선) ────────────── */

export function usePriceSnapshots(symbol: string | null, limit = 120) {
  const [snapshots, setSnapshots] = useState<PriceSnapshot[]>([]);
  const [loading, setLoading] = useState(true);

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
      .channel(`price-snapshots-${symbol}`)
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
  }, [fetch, symbol, limit]);

  return { snapshots, loading, refetch: fetch };
}

/* ── Held Symbols (보유 종목 목록) ────────────────────────── */

/**
 * 현재 보유 중인 종목 목록을 반환합니다.
 * 오케스트레이터는 보유 종목에 대해서만 price_snapshots를 저장하므로,
 * 최근 1시간 내 스냅샷이 있는 종목 = 현재 보유 종목입니다.
 */
export function useHeldSymbols() {
  const [symbols, setSymbols] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      setLoading(true);
      const since = dayjs().subtract(1, 'hour').toISOString();
      const { data } = await supabase
        .from('price_snapshots')
        .select('symbol')
        .gte('created_at', since);
      const unique = [...new Set((data ?? []).map((d: { symbol: string }) => d.symbol))].sort();
      setSymbols(unique);
      setLoading(false);
    })();

    // 새 스냅샷 도착 시 종목 목록 갱신
    const channel = supabase
      .channel('held-symbols-realtime')
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
      .subscribe();

    return () => {
      supabase.removeChannel(channel);
    };
  }, []);

  return { symbols, loading };
}

/* ── Balance Snapshots (시간별 잔고 스냅샷) ────────────── */

export function useBalanceSnapshots(hours = 24) {
  const [snapshots, setSnapshots] = useState<BalanceSnapshot[]>([]);
  const [loading, setLoading] = useState(true);

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
  }, [hours]);

  return { snapshots, loading };
}

/* ── Held Positions (보유 종목 포지션 정보) ────────────── */

/**
 * 현재 보유 중인 종목의 포지션 정보(매수가, 수량, 투입금액)를 반환합니다.
 * 각 종목의 가장 최근 매수(bid) 거래를 기준으로 합니다.
 */
export function useHeldPositions(heldSymbols: string[]) {
  const [positions, setPositions] = useState<Map<string, HeldPosition>>(new Map());
  const [loading, setLoading] = useState(true);
  const symbolsKey = heldSymbols.join(',');

  useEffect(() => {
    if (heldSymbols.length === 0) {
      setPositions(new Map());
      setLoading(false);
      return;
    }

    (async () => {
      setLoading(true);
      const { data } = await supabase
        .from('trades')
        .select('*')
        .in('symbol', heldSymbols)
        .eq('side', 'bid')
        .order('created_at', { ascending: false });

      const posMap = new Map<string, HeldPosition>();
      for (const trade of (data as Trade[]) ?? []) {
        // 종목당 가장 최근 매수 거래만 사용
        if (!posMap.has(trade.symbol)) {
          posMap.set(trade.symbol, {
            symbol: trade.symbol,
            entry_price: trade.price,
            volume: trade.volume,
            amount: trade.amount,
            created_at: trade.created_at,
          });
        }
      }
      setPositions(posMap);
      setLoading(false);
    })();
  }, [symbolsKey]); // eslint-disable-line react-hooks/exhaustive-deps

  return { positions, loading };
}

/* ── Latest Snapshots (보유 종목 최신 손절/익절 정보) ──── */

/** 보유 종목별 최신 price_snapshot에서 stop_loss, take_profit을 가져옵니다. */
export function useLatestSnapshots(heldSymbols: string[]) {
  const [snapshots, setSnapshots] = useState<Map<string, PriceSnapshot>>(new Map());
  const [loading, setLoading] = useState(true);
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
      .order('created_at', { ascending: false });

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
      .channel('latest-snapshots-realtime')
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
  }, [fetch]); // eslint-disable-line react-hooks/exhaustive-deps

  return { snapshots, loading };
}


/* ── Daily Reports (일일 분석 리포트) ─────────────────── */

export function useDailyReports(limit = 30) {
  const [reports, setReports] = useState<DailyReport[]>([]);
  const [loading, setLoading] = useState(true);

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
      .channel('daily-reports-realtime')
      .on(
        'postgres_changes',
        { event: 'INSERT', schema: 'public', table: 'daily_reports' },
        () => { fetch(); },
      )
      .subscribe();

    return () => {
      supabase.removeChannel(channel);
    };
  }, [fetch]);

  return { reports, loading, refetch: fetch };
}

export function useDailyReport(reportDate: string | null) {
  const [report, setReport] = useState<DailyReport | null>(null);
  const [loading, setLoading] = useState(false);

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
  }, [reportDate]);

  return { report, loading };
}