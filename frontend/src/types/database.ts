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
  slippage: number | null;  // 예상 슬리피지 (bps), 매도 거래는 null
  remaining_volume: number | null;
  reason: string | null;
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

/** 종목별 진입 게이트 지표 (backend에서 10초마다 갱신) */
export interface SymbolIndicators {
  vol: number;           // 변동성 비율 (< 2.0이면 통과)
  trend: 'up' | 'down' | 'unknown';  // MA20 vs MA50
  bb: 'none' | 'below' | 'recovered'; // BB 하단 이탈 상태
  rsi: number;           // RSI 값 (0~100)
  rsi_slope: number;     // RSI 기울기 (양수=상승전환)
  adx: number;           // ADX 값 (0~100, 낮을수록 횡보=평균회귀 유리)
}

export interface BotState {
  id: number;
  initial_balance: number;
  current_balance: number;
  krw_balance: number;
  top_symbols: string[];
  symbol_volatilities: Record<string, SymbolIndicators>;
  is_active: boolean;
  upbit_status: UpbitStatus;
  kakao_status: KakaoStatus;
  strategy_params: Record<string, number> | null;
  market_regime: 'trending' | 'ranging' | 'volatile' | null;
  kelly_fraction: number | null;  // 켈리 비중 (0.0~1.0), null이면 고정비율
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


export interface DailyReport {
  id: number;
  report_date: string;
  content: string;
  total_balance: number;
  net_profit: number;
  trade_count: number;
  win_count: number;
  loss_count: number;
  created_at: string;
}
export interface SentimentInsight {
  id: number;
  news_id: string;
  title: string;
  source: string | null;
  url: string | null;
  currencies: string[];
  sentiment_score: number;         // -1.0 ~ 1.0
  sentiment_label: 'bullish' | 'bearish' | 'neutral';
  decision: 'BUY' | 'SELL' | 'HOLD' | 'WAIT';
  confidence: number;              // 0 ~ 100
  reasoning_chain: string | null;
  keywords: string[];
  positive_factors: string[];
  negative_factors: string[];
  volume_impact: boolean;
  verification_result: 'correct' | 'incorrect' | null;
  actual_price_change: number | null;
  created_at: string;
}
