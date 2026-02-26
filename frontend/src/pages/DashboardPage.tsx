import { useState, useRef, useMemo, useDeferredValue, memo, useCallback } from 'react';
import {
  Row,
  Col,
  Card,
  Statistic,
  Table,
  Tag,
  Typography,
  Flex,
  Space,
  Spin,
  Empty,
  Segmented,
  Tooltip,
  Button,
  message,
} from 'antd';
import {
  FireOutlined,
  InfoCircleOutlined,
  EditOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';
import { useTrades, useDailyStats, useBotState, useHeldSymbols, useBalanceSnapshots, useHeldPositions, useLatestSnapshots } from '../hooks/useSupabase';
import type { Trade, SymbolIndicators, PriceSnapshot, HeldPosition } from '../types/database';
import { useUpbitTicker, type TickerData } from '../hooks/useUpbitTicker';
import HeldCoinChart from '../components/HeldCoinChart';
import AssetGrowthChart from '../components/AssetGrowthChart';
import StrategyEditModal from '../components/StrategyEditModal';
import type { StrategyParams } from '../components/StrategyEditModal';
import { loadStrategyParams, saveStrategyParams, getActivePresetName } from '../lib/strategyParams';

const { Title, Text } = Typography;
/* ── 색상 상수 (한국 주식시장 컨벤션) ───────────────────── */
const COLOR_RISE = '#ff4d4f';   // 상승 · 플러스 = 빨강
const COLOR_FALL = '#1890ff';   // 하락 · 마이너스 = 파랑
const COLOR_EVEN = '#999';      // 보합 · 중립 = 회색

/* ── 차트 기간 옵션 ────────────────────────────────────── */

const CHART_RANGES = [
  { label: '1시간', value: '1h' },
  { label: '일', value: '1d' },
  { label: '주', value: 7 },
  { label: '월', value: 30 },
];

/* ── 지표 정규화 헬퍼 (모듈 레벨) ──────────────────────── */

function parseInd(v: unknown): SymbolIndicators | undefined {
  if (v == null) return undefined;
  if (typeof v === 'object' && 'vol' in (v as object)) return v as SymbolIndicators;
  // 이전 형식: number (변동성만 저장)
  if (typeof v === 'number') return { vol: v, trend: 'unknown', bb: 'none', rsi: 50, rsi_slope: 0 };
  return undefined;
}

/* ── 종목 테이블 행 타입 ────────────────────────────────── */

interface SymbolRow {
  key: string;
  rank: number | null;
  symbol: string;
  indicators: SymbolIndicators | undefined;
  pos: HeldPosition | null;
  snap: PriceSnapshot | null;
}

/* ── 최근 거래 테이블 컬럼 ──────────────────────────────── */

const tradeColumns: ColumnsType<Trade> = [
  {
    title: '시간',
    dataIndex: 'created_at',
    width: 160,
    render: (v: string) => dayjs(v).format('MM-DD HH:mm:ss'),
  },
  {
    title: '종목',
    dataIndex: 'symbol',
    width: 120,
    render: (v: string) => <Text strong>{v.replace('KRW-', '')}</Text>,
  },
  {
    title: '구분',
    dataIndex: 'side',
    width: 80,
    render: (v: string) => (
      <Tag color={v === 'bid' ? 'red' : 'blue'}>{v === 'bid' ? '매수' : '매도'}</Tag>
    ),
  },
  {
    title: '가격',
    dataIndex: 'price',
    width: 120,
    align: 'right',
    render: (v: number) => `${v.toLocaleString()} 원`,
  },
  {
    title: '수량',
    dataIndex: 'volume',
    width: 120,
    align: 'right',
    render: (v: number, record: Trade) => {
      if (record.side === 'ask' && record.remaining_volume != null) {
        return (
          <span>
            {v?.toFixed(4) ?? '-'}
            <br />
            <Text type="secondary" style={{ fontSize: 10 }}>
              {record.remaining_volume > 0
                ? `잔여: ${record.remaining_volume.toFixed(4)}`
                : '잔여: 없음 (전량)'}
            </Text>
          </span>
        );
      }
      return v?.toFixed(4) ?? '-';
    },
  },
  {
    title: '금액',
    dataIndex: 'amount',
    width: 120,
    align: 'right',
    render: (v: number) => `${Math.round(v).toLocaleString()} 원`,
  },
  {
    title: '손익',
    dataIndex: 'pnl',
    width: 120,
    align: 'right',
    render: (v: number | null, record: Trade) => {
      if (record.side === 'bid') return <Text type="secondary">-</Text>;
      if (v == null) return <Text type="secondary">-</Text>;
      const color = v >= 0 ? COLOR_RISE : COLOR_FALL;
      return <Text style={{ color }}>{`${v >= 0 ? '+' : ''}${Math.round(v).toLocaleString()}`}</Text>;
    },
  },
];

/* ── 거래대금 상위 종목 테이블 컬럼 (모듈 레벨 — 안정 참조) ── */

const baseSymbolColumns: ColumnsType<SymbolRow> = [
  {
    title: '#',
    dataIndex: 'rank',
    width: 48,
    render: (v: number | null) =>
      v != null ? (
        <Text type="secondary" style={{ fontSize: 12 }}>{v}</Text>
      ) : (
        <Text type="secondary" style={{ fontSize: 12 }}>-</Text>
      ),
  },
  {
    title: '종목',
    dataIndex: 'symbol',
    width: 110,
    render: (v: string, record: SymbolRow) => (
      <Flex gap={6} align="center">
        <Text strong>{v.replace('KRW-', '')}</Text>
        {record.pos && (
          <Tag color="blue" style={{ margin: 0, fontSize: 10, lineHeight: '16px', padding: '0 4px' }}>보유</Tag>
        )}
      </Flex>
    ),
  },
  {
    title: (
      <Space size={4}>
        <span>변동성</span>
        <Tooltip destroyOnHidden
          title={
            <div>
              <div>단기(4h) / 장기(2일) 변동성 비율</div>
              <div style={{ marginTop: 6 }}>
                <span style={{ color: '#389e0d' }}>■</span> 1.5x 미만 — 안정 (매수 가능)
              </div>
              <div>
                <span style={{ color: '#fa8c16' }}>■</span> 1.5x~2.0x — 주의
              </div>
              <div>
                <span style={{ color: '#cf1322' }}>■</span> 2.0x 이상 — 과부하 (매수 중단)
              </div>
            </div>
          }
        >
          <InfoCircleOutlined style={{ fontSize: 11, color: '#999', cursor: 'pointer' }} />
        </Tooltip>
      </Space>
    ),
    dataIndex: 'indicators',
    width: 85,
    align: 'right' as const,
    render: (_: unknown, record: SymbolRow) => {
      const vol = record.indicators?.vol;
      if (vol == null) return <Text type="secondary" style={{ fontSize: 12 }}>-</Text>;
      const color = vol >= 2.0 ? '#cf1322' : vol >= 1.5 ? '#fa8c16' : '#389e0d';
      return <Text style={{ fontSize: 12, color, fontWeight: 500 }}>{vol.toFixed(2)}x</Text>;
    },
  },
  {
    title: (
      <Space size={4}>
        <span>추세</span>
        <Tooltip destroyOnHidden
          title={
            <div>
              <div>이동평균선 추세 (MA20 vs MA50)</div>
              <div style={{ marginTop: 6 }}>
                <span style={{ color: '#389e0d' }}>■</span> 상승 — MA20이 MA50 위 (매수 가능)
              </div>
              <div>
                <span style={{ color: '#cf1322' }}>■</span> 하락 — MA20이 MA50 아래 (매수 차단)
              </div>
            </div>
          }
        >
          <InfoCircleOutlined style={{ fontSize: 11, color: '#999', cursor: 'pointer' }} />
        </Tooltip>
      </Space>
    ),
    dataIndex: 'indicators',
    width: 70,
    align: 'center' as const,
    render: (_: unknown, record: SymbolRow) => {
      const trend = record.indicators?.trend;
      if (!trend || trend === 'unknown') return <Text type="secondary" style={{ fontSize: 12 }}>-</Text>;
      const isUp = trend === 'up';
      return (
        <Text style={{ fontSize: 11, color: isUp ? '#389e0d' : '#cf1322', fontWeight: 500 }}>
          {isUp ? '▲ 상승' : '▼ 하락'}
        </Text>
      );
    },
  },
  {
    title: (
      <Space size={4}>
        <span>BB</span>
        <Tooltip destroyOnHidden
          title={
            <div>
              <div>볼린저밴드 하단 이탈 → 복귀 패턴</div>
              <div style={{ marginTop: 6 }}>
                <span style={{ color: '#389e0d' }}>■</span> 복귀 — 하단 이탈 후 복귀 완료 (매수 준비)
              </div>
              <div>
                <span style={{ color: '#fa8c16' }}>■</span> 이탈 — 현재 하단 아래 (대기 중)
              </div>
              <div>
                <span style={{ color: '#cf1322' }}>■</span> 없음 — 이탈 이력 없음 (매수 불가)
              </div>
            </div>
          }
        >
          <InfoCircleOutlined style={{ fontSize: 11, color: '#999', cursor: 'pointer' }} />
        </Tooltip>
      </Space>
    ),
    dataIndex: 'indicators',
    width: 70,
    align: 'center' as const,
    render: (_: unknown, record: SymbolRow) => {
      const bb = record.indicators?.bb;
      if (!bb) return <Text type="secondary" style={{ fontSize: 12 }}>-</Text>;
      if (bb === 'recovered') return <Text style={{ fontSize: 11, color: '#389e0d', fontWeight: 500 }}>복귀</Text>;
      if (bb === 'below') return <Text style={{ fontSize: 11, color: '#fa8c16', fontWeight: 500 }}>이탈</Text>;
      return <Text style={{ fontSize: 11, color: '#cf1322', fontWeight: 500 }}>없음</Text>;
    },
  },
  {
    title: (
      <Space size={4}>
        <span>RSI</span>
        <Tooltip destroyOnHidden
          title={
            <div>
              <div>RSI 과매도 + 상승전환 확인</div>
              <div style={{ marginTop: 6 }}>
                <span style={{ color: '#389e0d' }}>■</span> 30 이하 + 상승 중 — 매수 신호
              </div>
              <div>
                <span style={{ color: '#fa8c16' }}>■</span> 30 이하 하락 중 / 30~35 상승 중 — 경계
              </div>
              <div>
                <span style={{ color: '#cf1322' }}>■</span> 35 초과 또는 30~35 하락 중 — 매수 차단
              </div>
            </div>
          }
        >
          <InfoCircleOutlined style={{ fontSize: 11, color: '#999', cursor: 'pointer' }} />
        </Tooltip>
      </Space>
    ),
    dataIndex: 'indicators',
    width: 80,
    align: 'right' as const,
    render: (_: unknown, record: SymbolRow) => {
      const ind = record.indicators;
      if (!ind) return <Text type="secondary" style={{ fontSize: 12 }}>-</Text>;
      const { rsi, rsi_slope } = ind;
      const isRising = rsi_slope > 0;
      const color = rsi <= 30 && isRising ? '#389e0d' : (rsi <= 30 || (rsi <= 35 && isRising)) ? '#fa8c16' : '#cf1322';
      const arrow = isRising ? '↑' : '↓';
      return (
        <Text style={{ fontSize: 12, color, fontWeight: 500 }}>
          {rsi.toFixed(0)} {arrow}
        </Text>
      );
    },
  },
  ];

/* ── 손절가·익절가 헤더 (안정 참조) ───────────────────────── */

const STOP_LOSS_HEADER = (
  <Space size={4}>
    <span>손절가</span>
    <Tooltip destroyOnHidden
      title={
        <div>
          <div>진입가 − ATR × 2.5</div>
          <div>현재가 ≤ 손절가 도달 시 전량 매도</div>
          <div style={{ marginTop: 6 }}>
            <span style={{ color: "#cf1322" }}>■</span> 1% 미만 — 위험
          </div>
          <div>
            <span style={{ color: "#fa8c16" }}>■</span> 1%~3% — 주의
          </div>
          <div>
            <span style={{ color: "#999" }}>■</span> 3% 이상 — 여유
          </div>
        </div>
      }
    >
      <InfoCircleOutlined style={{ fontSize: 11, color: "#999", cursor: "pointer" }} />
    </Tooltip>
  </Space>
);

const TAKE_PROFIT_HEADER = (
  <Space size={4}>
    <span>익절가</span>
    <Tooltip destroyOnHidden
      title={
        <div>
          <div>볼린저밴드 상단선 (BB Upper)</div>
          <div>현재가 ≥ 익절가 도달 시 전량 매도</div>
          <div style={{ marginTop: 6 }}>
            <span style={{ color: "#389e0d" }}>■</span> 1% 미만 — 임박
          </div>
          <div>
            <span style={{ color: "#fa8c16" }}>■</span> 1%~3% — 주의
          </div>
          <div>
            <span style={{ color: "#999" }}>■</span> 3% 이상 — 여유
          </div>
        </div>
      }
    >
      <InfoCircleOutlined style={{ fontSize: 11, color: "#999", cursor: "pointer" }} />
    </Tooltip>
  </Space>
);

/* ── 시세 의존 컬럼 빌더 (SymbolTable 내부에서 useMemo) ──── */

function buildTickerColumns(tickers: Map<string, TickerData>): ColumnsType<SymbolRow> {
  return [
    {
      title: '현재가',
      dataIndex: 'symbol',
      width: 110,
      align: 'right' as const,
      render: (_: unknown, record: SymbolRow) => {
        const t = tickers.get(record.symbol);
        if (!t) return <Text type="secondary" style={{ fontSize: 12 }}>-</Text>;
        const color = t.change === 'RISE' ? COLOR_RISE : t.change === 'FALL' ? COLOR_FALL : COLOR_EVEN;
        return (
          <Flex vertical align="flex-end" gap={0}>
            <Text style={{ fontSize: 12, color }}>{t.trade_price.toLocaleString()}</Text>
            <Text style={{ fontSize: 10, color }}>
              {t.change_rate >= 0 ? '+' : ''}{t.change_rate.toFixed(2)}%
            </Text>
          </Flex>
        );
      },
    },
    {
      title: '매수가',
      dataIndex: 'pos',
      width: 120,
      align: 'right' as const,
      render: (_: unknown, record: SymbolRow) => {
        if (!record.pos) return <Text type="secondary" style={{ fontSize: 12 }}>-</Text>;
        const entry = record.pos.entry_price;
        const cur = tickers.get(record.symbol)?.trade_price ?? record.snap?.price;
        const diff = cur ? cur - entry : null;
        const diffColor = diff != null ? (diff >= 0 ? COLOR_RISE : COLOR_FALL) : undefined;
        return (
          <Flex vertical align="flex-end" gap={0}>
            <Text style={{ fontSize: 12 }}>{entry.toLocaleString()}</Text>
            {diff != null && (
              <Text style={{ fontSize: 10, color: diffColor }}>
                {diff >= 0 ? '+' : ''}{Math.round(diff).toLocaleString()}
              </Text>
            )}
          </Flex>
        );
      },
    },
    {
      title: '수익률',
      width: 120,
      align: 'right' as const,
      render: (_: unknown, record: SymbolRow) => {
        if (!record.pos) return <Text type="secondary" style={{ fontSize: 12 }}>-</Text>;
        const currentPrice = tickers.get(record.symbol)?.trade_price ?? record.snap?.price;
        if (!currentPrice) return <Text type="secondary" style={{ fontSize: 12 }}>-</Text>;
        const pnlPct = ((currentPrice - record.pos.entry_price) / record.pos.entry_price) * 100;
        const pnlAmt = (currentPrice - record.pos.entry_price) * record.pos.volume;
        const color = pnlPct >= 0 ? COLOR_RISE : COLOR_FALL;
        return (
          <div style={{ lineHeight: 1.3 }}>
            <Text style={{ fontSize: 12, color, fontWeight: 600 }}>
              {pnlPct >= 0 ? '+' : ''}{pnlPct.toFixed(2)}%
            </Text>
            <br />
            <Text style={{ fontSize: 11, color }}>
              {pnlAmt >= 0 ? '+' : ''}{Math.round(pnlAmt).toLocaleString()}원
            </Text>
          </div>
        );
      },
    },
    {
      title: STOP_LOSS_HEADER,
      width: 120,
      align: 'right' as const,
      render: (_: unknown, record: SymbolRow) => {
        const sl = record.snap?.stop_loss;
        if (!sl) return <Text type="secondary" style={{ fontSize: 12 }}>-</Text>;
        const curPrice = tickers.get(record.symbol)?.trade_price ?? record.snap?.price;
        const distPct = curPrice ? ((curPrice - sl) / curPrice) * 100 : null;
        const distColor = distPct != null ? (distPct < 1 ? '#cf1322' : distPct < 3 ? '#fa8c16' : '#999') : undefined;
        return (
          <div style={{ lineHeight: 1.3 }}>
            <Text style={{ fontSize: 12 }}>{Math.round(sl).toLocaleString()}</Text>
            {distPct != null && (
              <>
                <br />
                <Text style={{ fontSize: 11, color: distColor }}>
                  {distPct.toFixed(1)}%
                </Text>
              </>
            )}
          </div>
        );
      },
    },
    {
      title: TAKE_PROFIT_HEADER,
      width: 120,
      align: 'right' as const,
      render: (_: unknown, record: SymbolRow) => {
        const tp = record.snap?.take_profit;
        if (!tp) return <Text type="secondary" style={{ fontSize: 12 }}>-</Text>;
        const curPrice = tickers.get(record.symbol)?.trade_price ?? record.snap?.price;
        const distPct = curPrice ? ((tp - curPrice) / curPrice) * 100 : null;
        const distColor = distPct != null ? (distPct < 1 ? '#389e0d' : distPct < 3 ? '#fa8c16' : '#999') : undefined;
        return (
          <div style={{ lineHeight: 1.3 }}>
            <Text style={{ fontSize: 12 }}>{Math.round(tp).toLocaleString()}</Text>
            {distPct != null && (
              <>
                <br />
                <Text style={{ fontSize: 11, color: distColor }}>
                  {distPct.toFixed(1)}%
                </Text>
              </>
            )}
          </div>
        );
      },
    },
  ];
}

/* ── 테이블 안정 참조 (모듈 레벨) ─────────────────────── */

const symbolRowClassName = (record: SymbolRow) => record.pos ? 'held-row' : '';
const SYMBOL_TABLE_SCROLL = { x: 1200 } as const;

/* ── SymbolTable (React.memo — 부모 re-render 격리) ──── */

interface SymbolTableProps {
  rows: SymbolRow[];
  tickers: Map<string, TickerData>;
  updatedAt: string | null;
}

const SymbolTable = memo(function SymbolTable({ rows, tickers, updatedAt }: SymbolTableProps) {
  const columns = useMemo<ColumnsType<SymbolRow>>(
    () => [...baseSymbolColumns, ...buildTickerColumns(tickers)],
    [tickers]
  );
  return (
    <Card
      title={
        <Space>
          <FireOutlined style={{ color: '#fa541c' }} />
          <span>거래대금 상위 종목</span>
          {updatedAt && (
            <Text type="secondary" style={{ fontSize: 12, fontWeight: 'normal' }}>
              (갱신: {dayjs(updatedAt).format('HH:mm:ss')})
            </Text>
          )}
        </Space>
      }
      variant="borderless"
    >
      {rows.length === 0 ? (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description={
            <Text type="secondary">봇 실행 후 거래대금 상위 종목이 표시됩니다</Text>
          }
          style={{ padding: 20 }}
        />
      ) : (
        <Table<SymbolRow>
          dataSource={rows}
          rowKey="key"
          size="small"
          pagination={false}
          scroll={SYMBOL_TABLE_SCROLL}
          rowClassName={symbolRowClassName}
          columns={columns}
        />
      )}
    </Card>
  );
});

/* ── Dashboard Page ────────────────────────────────────── */

export default function DashboardPage() {
  const [chartRange, setChartRange] = useState<string | number>('1h');
  const [strategyEditOpen, setStrategyEditOpen] = useState(false);
  const [currentStrategyParams, setCurrentStrategyParams] = useState<StrategyParams>({
    bb_period: 20, bb_std_dev: 2.0, rsi_period: 14, rsi_oversold: 30,
    atr_period: 14, atr_multiplier: 2.5,
  });
  const [, setActivePreset] = useState<string | null>(null);
  const [messageApi, contextHolder] = message.useMessage();

  const handleOpenStrategyEdit = useCallback(async () => {
    const params = await loadStrategyParams();
    setCurrentStrategyParams(params);
    setActivePreset(getActivePresetName(params));
    setStrategyEditOpen(true);
  }, []);
  const isHourly = chartRange === '1h' || chartRange === '1d';
  const balanceHours = chartRange === '1h' ? 1 : 24;

  const { trades, loading: tradesLoading } = useTrades(10);
  const { stats: chartStats, loading: chartStatsLoading } = useDailyStats(isHourly ? 30 : (chartRange as number));
  const { stats: summaryStats } = useDailyStats(2); // Summary Cards용: 오늘 + 어제 (차트 기간과 독립)
  const { botState } = useBotState();

  /* 활성 프리셋 — botState.strategy_params에서 파생 */
  const strategyParamsRaw = botState?.strategy_params;
  const displayPreset = useMemo(() => {
    if (!strategyParamsRaw) return null;
    return getActivePresetName(strategyParamsRaw as unknown as StrategyParams);
  }, [strategyParamsRaw]);
  const { symbols: heldSymbols, loading: heldLoading } = useHeldSymbols();
  const { snapshots: balanceSnapshots, loading: balanceLoading } = useBalanceSnapshots(balanceHours);
  const { positions: heldPositions } = useHeldPositions(heldSymbols);
  const { snapshots: latestSnapshots } = useLatestSnapshots(heldSymbols);

  /* 초기 로딩 이후에는 기간 변경 시 스켈레톤을 표시하지 않음 */
  const chartInitialLoadDone = useRef(false);
  if (!chartStatsLoading && !balanceLoading) {
    chartInitialLoadDone.current = true;
  }
  const showChartSkeleton = !chartInitialLoadDone.current && (isHourly ? balanceLoading : chartStatsLoading);

  /* top_symbols: DB에 이전 json.dumps 버그로 문자열로 저장된 경우 fallback */
  const topSymbolsRaw = botState?.top_symbols;
  const topSymbols = useMemo<string[]>(() => {
    if (!topSymbolsRaw) return [];
    if (Array.isArray(topSymbolsRaw)) return topSymbolsRaw;
    if (typeof topSymbolsRaw === 'string') {
      try { return JSON.parse(topSymbolsRaw); } catch { return []; }
    }
    return [];
  }, [topSymbolsRaw]);

  /* 업비트 WebSocket 실시간 시세 — 상위 종목 + 보유 종목 모두 구독 */
  const allSymbols = useMemo(() => {
    const set = new Set([...topSymbols, ...heldSymbols]);
    return [...set];
  }, [topSymbols, heldSymbols]);
  const { tickers } = useUpbitTicker(allSymbols);
  const deferredTickers = useDeferredValue(tickers);

  /* ── 요약 통계 — 총자산 변동 기준으로 통일 ────────────── */
  const todayStat = summaryStats.length > 0 ? summaryStats[summaryStats.length - 1] : null;
  const prevDayStat = summaryStats.length > 1 ? summaryStats[summaryStats.length - 2] : null;

  const totalBalance = botState?.current_balance ?? todayStat?.total_balance ?? 0;
  const prevBalance = prevDayStat?.total_balance ?? 0;
  const dailyPnl = prevBalance > 0 ? totalBalance - prevBalance : 0;
  const dailyPnlPct = prevBalance > 0 ? (dailyPnl / prevBalance) * 100 : 0;
  const todayStr = dayjs().format('YYYY-MM-DD');
  const todayTradeCount = trades.filter((t) => t.created_at.startsWith(todayStr)).length;
  const krwBalance = botState?.krw_balance ?? 0;

  /* ── 자산 성장 곡선 데이터 (메모이제이션) ─────────────── */
  const chartData = useMemo(() => {
    return isHourly
      ? balanceSnapshots.map((s) => ({ date: s.created_at, balance: s.total_balance }))
      : chartStats.map((s) => ({ date: s.stats_date, balance: s.total_balance, netProfit: s.net_profit }));
  }, [isHourly, balanceSnapshots, chartStats]);

  /* ── 거래대금 상위 종목 테이블 행 (메모이제이션) ──────── */
  const rawIndMap = botState?.symbol_volatilities ?? {};
  const allRows = useMemo<SymbolRow[]>(() => {
    const extraHeld = heldSymbols.filter((s) => !topSymbols.includes(s));
    return [
      ...topSymbols.map((symbol, idx) => ({
        key: symbol,
        rank: idx + 1,
        symbol,
        indicators: parseInd(rawIndMap[symbol]),
        pos: heldPositions.get(symbol) ?? null,
        snap: latestSnapshots.get(symbol) ?? null,
      })),
      ...extraHeld.map((symbol) => ({
        key: symbol,
        rank: null as number | null,
        symbol,
        indicators: parseInd(rawIndMap[symbol]),
        pos: heldPositions.get(symbol) ?? null,
        snap: latestSnapshots.get(symbol) ?? null,
      })),
    ];
  }, [topSymbols, heldSymbols, rawIndMap, heldPositions, latestSnapshots]);

  if (tradesLoading && chartStatsLoading) {
    return (
      <div style={{ textAlign: 'center', padding: 80 }}>
        <Spin size="large" />
      </div>
    );
  }

  return (
    <Flex vertical gap={24} style={{ width: '100%' }}>
      {contextHolder}
      <Flex justify="space-between" align="center">
        <Flex align="center" gap={8}>
          <Title level={4} style={{ margin: 0 }}>
            Dashboard
          </Title>
          {displayPreset && (
            <Tag color="blue" style={{ margin: 0 }}>{displayPreset}</Tag>
          )}
        </Flex>
        <Button
          icon={<EditOutlined />}
          onClick={handleOpenStrategyEdit}
        >
          실시간 수정
        </Button>
      </Flex>

      {/* ── Summary Cards ── */}
      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} lg={6}>
          <Card variant="borderless">
            <Statistic
              title="보유 잔고 (매수 가능)"
              value={krwBalance}
              precision={0}
              suffix="KRW"
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card variant="borderless">
            <Statistic
              title="총 자산"
              value={totalBalance}
              precision={0}
              suffix="KRW"
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card variant="borderless">
            <Statistic
              title="당일 손익"
              value={dailyPnl}
              precision={0}
              suffix="KRW"
              styles={{ content: { color: dailyPnl >= 0 ? COLOR_RISE : COLOR_FALL } }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card variant="borderless">
            <Statistic
              title="일일 수익률"
              value={dailyPnlPct}
              precision={2}
              suffix="%"
              styles={{ content: { color: dailyPnlPct >= 0 ? COLOR_RISE : COLOR_FALL } }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card variant="borderless">
            <Statistic
              title="오늘 거래"
              value={todayTradeCount}
              suffix="건"
            />
          </Card>
        </Col>
      </Row>

      {/* ── 거래대금 상위 종목 ── */}
      <SymbolTable rows={allRows} tickers={deferredTickers} updatedAt={botState?.updated_at ?? null} />

      {/* ── 보유 종목 가격 & 손절선 (그리드) ── */}
      {heldLoading ? (
        <Card variant="borderless">
          <div style={{ textAlign: 'center', padding: 40 }}>
            <Spin />
          </div>
        </Card>
      ) : heldSymbols.length > 0 ? (
        <Row gutter={[16, 16]}>
          {heldSymbols.map((symbol) => (
            <Col key={symbol} xs={24} lg={12}>
              <HeldCoinChart symbol={symbol} />
            </Col>
          ))}
        </Row>
      ) : (
        <Card title="가격 & 손절선" variant="borderless">
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={
              <Text type="secondary">
                보유 종목이 있을 때 가격 · 손절선 데이터가 자동으로 기록됩니다
              </Text>
            }
            style={{ padding: 40 }}
          />
        </Card>
      )}

      {/* ── 최근 거래 ── */}
      <Card title="최근 거래" variant="borderless">
        <Table<Trade>
          columns={tradeColumns}
          dataSource={trades}
          rowKey="id"
          size="small"
          pagination={false}
          loading={tradesLoading}
        />
      </Card>

      {/* ── 자산 성장 차트 ── */}
      <Card
        title="자산 성장 곡선"
        variant="borderless"
        loading={showChartSkeleton}
        extra={
          <Segmented
            value={chartRange}
            onChange={(v) => setChartRange(v as string | number)}
            options={CHART_RANGES}
            size="small"
          />
        }
      >
        {chartData.length > 0 ? (
          <AssetGrowthChart data={chartData} chartRange={chartRange as '1h' | '1d' | 7 | 30} />
        ) : (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={
              <Text type="secondary">
                봇 실행 후 자산 데이터가 자동으로 기록됩니다
              </Text>
            }
            style={{ padding: 40 }}
          />
        )}
      </Card>
      <StrategyEditModal
        open={strategyEditOpen}
        onClose={() => setStrategyEditOpen(false)}
        currentParams={currentStrategyParams}
        onApply={async (params: StrategyParams) => {
          const ok = await saveStrategyParams(params);
          if (ok) {
            messageApi.success('전략 파라미터가 저장되었습니다. 약 1분 내 봇에 적용됩니다.');
          } else {
            messageApi.error('전략 파라미터 저장에 실패했습니다.');
          }
        }}
      />
    </Flex>
  );
}
