/** DB 테이블 타입 정의 — Supabase 스키마와 1:1 매핑 */

export interface Trade {
  id: string;
  symbol: string;
  side: 'bid' | 'ask';
  price: number;
  volume: number;
  amount: number;
  fee: number;
  pnl: number | null;
  remaining_volume: number | null;
  created_at: string;
}

export interface DailyStat {
  stats_date: string;
  total_balance: number;
  net_profit: number;
  drawdown: number;
}

export interface SystemLog {
  id: number;
  level: 'INFO' | 'WARNING' | 'ERROR' | 'CRITICAL';
  message: string;
  created_at: string;
}

export type UpbitStatus = 'connected' | 'auth_failed' | 'rate_limited' | 'error' | 'unknown';
export type KakaoStatus = 'connected' | 'token_expired' | 'send_failed' | 'no_token' | 'unknown';

export interface BotState {
  id: number;
  initial_balance: number;
  current_balance: number;
  krw_balance: number;
  top_symbols: string[];
  symbol_volatilities: Record<string, number>;
  is_active: boolean;
  upbit_status: UpbitStatus;
  kakao_status: KakaoStatus;
  updated_at: string;
}

export interface PriceSnapshot {
  id: number;
  symbol: string;
  price: number;
  stop_loss: number | null;
  take_profit: number | null;
  created_at: string;
}

export interface BalanceSnapshot {
  id: number;
  total_balance: number;
  created_at: string;
}

/** 프론트엔드 전용: 보유 종목 포지션 요약 (trades 테이블 기반) */
export interface HeldPosition {
  symbol: string;
  entry_price: number;
  volume: number;
  amount: number;
  created_at: string;
}
