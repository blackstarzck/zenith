/** DB 테이블 타입 정의 — Supabase 스키마와 1:1 매핑 */

export type TradeSource = 'bot' | 'manual' | 'sync';

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
  trade_source: TradeSource | null;  // 거래 출처: bot=자동, manual=수동, sync=동기화
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
  // 진입 스코어 (백엔드에서 계산)
  entry_score?: number | null;              // 진입 가중합산 점수 (0~100)
  entry_threshold_base?: number | null;     // 기본 임계치
  entry_threshold_effective?: number | null; // 레짐 오프셋 적용 후 실효 임계치
  entry_regime_offset?: number | null;      // 레짐 오프셋 값
  entry_decision?: string | null;           // 'BUY' | 'HOLD' | 'BLOCKED' 등
  entry_block_reason?: string | null;       // 차단 사유 (쿨다운, 리스크 등)
  entry_executable?: boolean | null;        // 실제 매수 실행 가능 여부
  // 매도 스코어 (보유 종목에만 존재, 백엔드에서 계산)
  exit_score?: number | null;    // 매도 가중합산 점수 (0~100), null이면 트레일링 대기
  exit_rsi?: number;             // RSI 과매수 스코어 (0~100)
  exit_bb?: number;              // BB 상단 접근 스코어 (0~100)
  exit_profit?: number;          // 수익률 스코어 (0~100)
  exit_adx?: number;             // ADX 추세 강도 스코어 (0~100)
  exit_status?: string;          // "trailing" = 트레일링 스탑 대기 중
  exit_threshold_effective?: number | null;  // 매도 실효 임계치
  exit_decision?: string | null;            // 'SELL' | 'HOLD' 등
  exit_block_reason?: string | null;        // 매도 차단 사유
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
  decision: 'BUY' | 'SELL' | 'HOLD' | 'WAIT' | 'PENDING';
  confidence: number;              // 0 ~ 100
  reasoning_chain: string | null;
  keywords: string[];
  positive_factors: string[];
  negative_factors: string[];
  volume_impact: boolean;
  verification_result: 'correct' | 'incorrect' | 'neutral' | null;
  actual_price_change: number | null;
  // 검증 확장 필드
  verification_horizon_min: number | null;
  baseline_price: number | null;
  evaluation_price: number | null;
  evaluated_at: string | null;
  direction_match: boolean | null;
  pending_reason: string | null;
  // 검증 구간 수치
  verification_window_start_at: string | null;
  verification_window_end_at: string | null;
  window_open_price: number | null;
  window_close_price: number | null;
  window_high_price: number | null;
  window_low_price: number | null;
  window_return_pct: number | null;
  window_max_rise_pct: number | null;
  window_max_drop_pct: number | null;
  // AI 인사이트
  verification_explanation: string | null;
  analysis_insight: string | null;
  created_at: string;
}

/** 감성 검증 일일 집계 (sentiment_performance_daily 테이블) */
export interface SentimentPerformanceDaily {
  id: number;
  stats_date: string;
  currency: string;        // 'ALL' 또는 개별 통화 코드
  decision: string;        // 'BUY' | 'SELL' | 'HOLD' | 'WAIT' | 'ALL'
  total_count: number;
  verified_count: number;
  correct_count: number;
  incorrect_count: number;
  avg_confidence: number | null;
  avg_actual_change: number | null;
  created_at: string;
}

export interface DislocationPaperTrade {
  id: number;
  run_id: string;
  symbol: string;
  side: 'BUY' | 'SELL';
  reason: string | null;
  price: number;
  quantity: number;
  amount: number;
  fee: number;
  pnl: number | null;
  upbit_price: number;
  binance_price_usdt: number;
  usdt_krw_rate: number;
  foreign_price_krw: number;
  dislocation_pct: number;
  entry_threshold_pct: number | null;
  exit_threshold_pct: number | null;
  take_profit_pct: number | null;
  stop_loss_pct: number | null;
  max_hold_minutes: number | null;
  order_amount: number | null;
  entry_slice_index: number | null;
  entry_slices: number | null;
  exit_slice_index: number | null;
  exit_slices: number | null;
  upbit_momentum_1m: number | null;
  upbit_momentum_5m: number | null;
  binance_momentum_1m: number | null;
  lead_gap_pct: number | null;
  upbit_bid_pressure: number | null;
  binance_bid_pressure: number | null;
  chart_filter_pass: boolean | null;
  lead_filter_pass: boolean | null;
  dislocation_filter_pass: boolean | null;
  orderbook_filter_pass: boolean | null;
  created_at: string;
}

export interface DislocationPaperMetric {
  id: number;
  run_id: string;
  symbol: string;
  upbit_price: number;
  binance_price_usdt: number;
  usdt_krw_rate: number;
  foreign_price_krw: number;
  dislocation_pct: number;
  auto_enabled: boolean;
  has_position: boolean;
  avg_entry_price: number | null;
  unrealized_pnl_pct: number | null;
  entry_threshold_pct: number | null;
  exit_threshold_pct: number | null;
  take_profit_pct: number | null;
  stop_loss_pct: number | null;
  max_hold_minutes: number | null;
  entry_slices: number | null;
  next_entry_slice: number | null;
  next_exit_slice: number | null;
  upbit_momentum_1m: number | null;
  upbit_momentum_5m: number | null;
  binance_momentum_1m: number | null;
  lead_gap_pct: number | null;
  upbit_bid_pressure: number | null;
  binance_bid_pressure: number | null;
  chart_filter_pass: boolean | null;
  lead_filter_pass: boolean | null;
  dislocation_filter_pass: boolean | null;
  orderbook_filter_pass: boolean | null;
  all_filters_pass: boolean | null;
  decision: string | null;
  reason: string | null;
  created_at: string;
}
