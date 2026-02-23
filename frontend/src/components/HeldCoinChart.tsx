import { memo } from 'react';
import { usePriceSnapshots } from '../hooks/useSupabase';
import StopLossChart from './StopLossChart';

interface Props {
  symbol: string;
}

/**
 * 개별 보유 종목의 가격 · 손절선 차트.
 * 각 인스턴스가 독립적으로 Realtime 구독을 관리합니다.
 */
export default memo(function HeldCoinChart({ symbol }: Props) {
  const { snapshots, loading } = usePriceSnapshots(symbol);
  return <StopLossChart symbol={symbol} data={snapshots} loading={loading} />;
});
