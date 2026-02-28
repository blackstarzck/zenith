import { supabase } from './supabase';
import type { StrategyParams } from '../components/StrategyEditModal';

export const DEFAULT_STRATEGY: StrategyParams = {
  bb_period: 20,
  bb_std_dev: 2.0,
  rsi_period: 14,
  rsi_oversold: 30,
  atr_period: 14,
  atr_stop_multiplier: 2.5,
  top_volume_count: 10,
  w_volatility: 1.0,
  w_ma_trend: 1.0,
  w_adx: 1.0,
  w_bb_recovery: 1.0,
  w_rsi_slope: 1.0,
  w_rsi_level: 1.0,
  entry_score_threshold: 70,
  w_exit_rsi_level: 1.0,
  w_exit_bb_position: 1.0,
  w_exit_profit_pct: 1.0,
  w_exit_adx_trend: 1.0,
  exit_score_threshold: 70,
  trailing_stop_atr_multiplier: 2.0,
  take_profit_sell_ratio: 0.5,
  min_profit_margin: 0.003,
};

export const PRESETS: { name: string; description: string; params: StrategyParams }[] = [
  {
    name: '보수적',
    description: '낮은 빈도, 안전 우선',
    params: { bb_period: 20, bb_std_dev: 2.5, rsi_period: 14, rsi_oversold: 25, atr_period: 14, atr_stop_multiplier: 3.0, top_volume_count: 5, w_volatility: 1.5, w_ma_trend: 1.0, w_adx: 1.0, w_bb_recovery: 2.0, w_rsi_slope: 1.0, w_rsi_level: 1.5, entry_score_threshold: 90, w_exit_rsi_level: 1.5, w_exit_bb_position: 2.0, w_exit_profit_pct: 1.0, w_exit_adx_trend: 1.0, exit_score_threshold: 60, trailing_stop_atr_multiplier: 1.5, take_profit_sell_ratio: 0.5, min_profit_margin: 0.005 },
  },
  {
    name: '공격적',
    description: '높은 빈도, 수익 극대화',
    params: { bb_period: 15, bb_std_dev: 1.5, rsi_period: 10, rsi_oversold: 35, atr_period: 10, atr_stop_multiplier: 2.0, top_volume_count: 15, w_volatility: 0.5, w_ma_trend: 0.5, w_adx: 0.5, w_bb_recovery: 1.0, w_rsi_slope: 1.0, w_rsi_level: 1.0, entry_score_threshold: 55, w_exit_rsi_level: 0.5, w_exit_bb_position: 1.0, w_exit_profit_pct: 1.5, w_exit_adx_trend: 0.5, exit_score_threshold: 80, trailing_stop_atr_multiplier: 2.5, take_profit_sell_ratio: 0.5, min_profit_margin: 0.002 },
  },
  {
    name: '횡보장',
    description: '박스권 최적화',
    params: { bb_period: 25, bb_std_dev: 2.0, rsi_period: 14, rsi_oversold: 28, atr_period: 14, atr_stop_multiplier: 2.5, top_volume_count: 8, w_volatility: 1.0, w_ma_trend: 0.5, w_adx: 2.0, w_bb_recovery: 2.0, w_rsi_slope: 1.0, w_rsi_level: 1.0, entry_score_threshold: 70, w_exit_rsi_level: 1.0, w_exit_bb_position: 2.0, w_exit_profit_pct: 1.0, w_exit_adx_trend: 0.5, exit_score_threshold: 65, trailing_stop_atr_multiplier: 2.0, take_profit_sell_ratio: 0.5, min_profit_margin: 0.003 },
  },
  {
    name: '변동성 장세',
    description: '급등락 대응',
    params: { bb_period: 15, bb_std_dev: 2.5, rsi_period: 10, rsi_oversold: 25, atr_period: 10, atr_stop_multiplier: 3.5, top_volume_count: 5, w_volatility: 2.0, w_ma_trend: 1.0, w_adx: 1.0, w_bb_recovery: 1.5, w_rsi_slope: 1.5, w_rsi_level: 1.5, entry_score_threshold: 75, w_exit_rsi_level: 1.5, w_exit_bb_position: 1.5, w_exit_profit_pct: 2.0, w_exit_adx_trend: 1.5, exit_score_threshold: 60, trailing_stop_atr_multiplier: 1.5, take_profit_sell_ratio: 0.5, min_profit_margin: 0.003 },
  },
];

/** 현재 파라미터와 일치하는 프리셋 이름을 반환. 없으면 null. */
export function getActivePresetName(params: StrategyParams): string | null {
  const keys: (keyof StrategyParams)[] = [
    'bb_period', 'bb_std_dev', 'rsi_period', 'rsi_oversold', 'atr_period', 'atr_stop_multiplier', 'top_volume_count',
    'w_volatility', 'w_ma_trend', 'w_adx', 'w_bb_recovery', 'w_rsi_slope', 'w_rsi_level', 'entry_score_threshold',
    'w_exit_rsi_level', 'w_exit_bb_position', 'w_exit_profit_pct', 'w_exit_adx_trend',
    'exit_score_threshold', 'trailing_stop_atr_multiplier', 'take_profit_sell_ratio', 'min_profit_margin',
  ];
  for (const preset of PRESETS) {
    if (keys.every((k) => preset.params[k] === params[k])) return preset.name;
  }
  if (keys.every((k) => DEFAULT_STRATEGY[k] === params[k])) return '기본값';
  return null;
}

export async function loadStrategyParams(): Promise<StrategyParams> {
  const { data } = await supabase
    .from('bot_state')
    .select('strategy_params')
    .eq('id', 1)
    .single();
  if (data?.strategy_params) {
    return { ...DEFAULT_STRATEGY, ...data.strategy_params };
  }
  return DEFAULT_STRATEGY;
}

export async function saveStrategyParams(params: StrategyParams): Promise<boolean> {
  // RPC 함수로 RLS 우회하여 저장 (SECURITY DEFINER)
  const { data, error } = await supabase.rpc('update_strategy_params', {
    p_params: params,
  });
  if (error) {
    console.error('[saveStrategyParams] RPC 저장 실패:', error.message, error.details);
    return false;
  }
  if (data === false) {
    console.error('[saveStrategyParams] RPC 반환값 false: bot_state 행이 존재하지 않음');
    return false;
  }
  // 저장 검증: DB에서 다시 읽어 실제 반영 여부 확인
  const { data: verify } = await supabase
    .from('bot_state')
    .select('strategy_params')
    .eq('id', 1)
    .single();
  if (!verify?.strategy_params) {
    console.error('[saveStrategyParams] 검증 실패: DB에 값이 반영되지 않음');
    return false;
  }
  return true;
}
