import { useState, useRef, useMemo } from 'react';
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
} from 'antd';
import {
  ArrowUpOutlined,
  ArrowDownOutlined,
  WalletOutlined,
  BankOutlined,
  SwapOutlined,
  FundOutlined,
  FireOutlined,
  InfoCircleOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';
import { useTrades, useDailyStats, useBotState, useHeldSymbols, useBalanceSnapshots, useHeldPositions, useLatestSnapshots } from '../hooks/useSupabase';
import type { Trade } from '../types/database';
import { useUpbitTicker } from '../hooks/useUpbitTicker';
import HeldCoinChart from '../components/HeldCoinChart';
import AssetGrowthChart from '../components/AssetGrowthChart';

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

/* ── Dashboard Page ────────────────────────────────────── */

export default function DashboardPage() {
  const [chartRange, setChartRange] = useState<string | number>('1h');
  const isHourly = chartRange === '1h' || chartRange === '1d';
  const balanceHours = chartRange === '1h' ? 1 : 24;

  const { trades, loading: tradesLoading } = useTrades(10);
  const { stats, loading: statsLoading } = useDailyStats(isHourly ? 30 : (chartRange as number));
  const { botState } = useBotState();
  const { symbols: heldSymbols, loading: heldLoading } = useHeldSymbols();
  const { snapshots: balanceSnapshots, loading: balanceLoading } = useBalanceSnapshots(balanceHours);
  const { positions: heldPositions } = useHeldPositions(heldSymbols);
  const { snapshots: latestSnapshots } = useLatestSnapshots(heldSymbols);

  /* 초기 로딩 이후에는 기간 변경 시 스켈레톤을 표시하지 않음 */
  const chartInitialLoadDone = useRef(false);
  if (!statsLoading && !balanceLoading) {
    chartInitialLoadDone.current = true;
  }
  const showChartSkeleton = !chartInitialLoadDone.current && (isHourly ? balanceLoading : statsLoading);

  /* top_symbols: DB에 이전 json.dumps 버그로 문자열로 저장된 경우 fallback */
  const topSymbols: string[] = (() => {
    const raw = botState?.top_symbols;
    if (!raw) return [];
    if (Array.isArray(raw)) return raw;
    if (typeof raw === 'string') {
      try { return JSON.parse(raw); } catch { return []; }
    }
    return [];
  })();

  /* 업비트 WebSocket 실시간 시세 — 상위 종목 + 보유 종목 모두 구독 */
  const allSymbols = useMemo(() => {
    const set = new Set([...topSymbols, ...heldSymbols]);
    return [...set];
  }, [topSymbols, heldSymbols]);
  const { tickers } = useUpbitTicker(allSymbols);

  const latestStat = stats.length > 0 ? stats[stats.length - 1] : null;
  const prevStat = stats.length > 1 ? stats[stats.length - 2] : null;

  const totalBalance = botState?.current_balance ?? latestStat?.total_balance ?? 0;
  const dailyPnl = latestStat?.net_profit ?? 0;
  const dailyPnlPct =
    prevStat && prevStat.total_balance > 0
      ? ((totalBalance - prevStat.total_balance) / prevStat.total_balance) * 100
      : 0;
  const todayTradeCount = trades.length;
  const krwBalance = botState?.krw_balance ?? 0;

  /* 자산 성장 곡선 데이터 */
  const chartData = isHourly
    ? balanceSnapshots.map((s) => ({ date: s.created_at, balance: s.total_balance }))
    : stats.map((s) => ({ date: s.stats_date, balance: s.total_balance, netProfit: s.net_profit }));

  if (tradesLoading && statsLoading) {
    return (
      <div style={{ textAlign: 'center', padding: 80 }}>
        <Spin size="large" />
      </div>
    );
  }

  return (
    <Flex vertical gap={24} style={{ width: '100%' }}>
      <Title level={4} style={{ margin: 0 }}>
        Dashboard
      </Title>

      {/* ── Summary Cards ── */}
      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} lg={6}>
          <Card variant="borderless">
            <Statistic
              title="보유 잔고 (매수 가능)"
              value={krwBalance}
              precision={0}
              prefix={<BankOutlined />}
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
              prefix={<WalletOutlined />}
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
              prefix={dailyPnl >= 0 ? <ArrowUpOutlined /> : <ArrowDownOutlined />}
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
              prefix={<FundOutlined />}
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
              prefix={<SwapOutlined />}
              suffix="건"
            />
          </Card>
        </Col>
      </Row>

      {/* ── 거래대금 상위 종목 ── */}
      <Card
        title={
          <Space>
            <FireOutlined style={{ color: '#fa541c' }} />
            <span>거래대금 상위 종목</span>
            {botState?.updated_at && (
              <Text type="secondary" style={{ fontSize: 12, fontWeight: 'normal' }}>
                (갱신: {dayjs(botState.updated_at).format('HH:mm:ss')})
              </Text>
            )}
          </Space>
        }
        variant="borderless"
      >
        {(() => {
          /* 상위 종목 + 기타 보유 종목을 합쳐서 테이블 데이터 생성 */
          const extraHeld = heldSymbols.filter((s) => !topSymbols.includes(s));
          const volMap = botState?.symbol_volatilities ?? {};
          const allRows = [
            ...topSymbols.map((symbol, idx) => ({
              key: symbol,
              rank: idx + 1,
              symbol,
              volatility: volMap[symbol] as number | undefined,
              pos: heldPositions.get(symbol) ?? null,
              snap: latestSnapshots.get(symbol) ?? null,
              ticker: tickers.get(symbol) ?? null,
            })),
            ...extraHeld.map((symbol) => ({
              key: symbol,
              rank: null as number | null,
              symbol,
              volatility: volMap[symbol] as number | undefined,
              pos: heldPositions.get(symbol) ?? null,
              snap: latestSnapshots.get(symbol) ?? null,
              ticker: tickers.get(symbol) ?? null,
            })),
          ];

          type RowType = (typeof allRows)[number];

          if (allRows.length === 0) {
            return (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description={
                  <Text type="secondary">봇 실행 후 거래대금 상위 종목이 표시됩니다</Text>
                }
                style={{ padding: 20 }}
              />
            );
          }

          return (
            <Table
              dataSource={allRows}
              rowKey="key"
              size="small"
              pagination={false}
              scroll={{ x: 900 }}
              rowClassName={(record) => record.pos ? 'held-row' : ''}
              columns={[
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
                  render: (v: string, record: RowType) => (
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
                      <Tooltip
                        title={
                          <div>
                            <div>단기(4h) / 장기(2일) 변동성 비율</div>
                            <div style={{ marginTop: 6 }}>
                              <span style={{ color: '#389e0d' }}>■</span> &lt;1.5x — 안정 (매수 가능)
                            </div>
                            <div>
                              <span style={{ color: '#fa8c16' }}>■</span> 1.5x~2.0x — 주의
                            </div>
                            <div>
                              <span style={{ color: '#cf1322' }}>■</span> ≥2.0x — 과부하 (매수 중단)
                            </div>
                          </div>
                        }
                      >
                        <InfoCircleOutlined style={{ fontSize: 11, color: '#999', cursor: 'pointer' }} />
                      </Tooltip>
                    </Space>
                  ),
                  dataIndex: 'volatility',
                  width: 85,
                  align: 'right' as const,
                  render: (vol: number | undefined) => {
                    if (vol == null) return <Text type="secondary" style={{ fontSize: 12 }}>-</Text>;
                    const color = vol >= 2.0 ? '#cf1322' : vol >= 1.5 ? '#fa8c16' : '#389e0d';
                    return <Text style={{ fontSize: 12, color, fontWeight: 500 }}>{vol.toFixed(2)}x</Text>;
                  },
                },
                {
                  title: '현재가',
                  dataIndex: 'ticker',
                  width: 110,
                  align: 'right' as const,
                  render: (_: unknown, record: RowType) => {
                    const t = record.ticker;
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
                  render: (_: unknown, record: RowType) => {
                    if (!record.pos) return <Text type="secondary" style={{ fontSize: 12 }}>-</Text>;
                    const entry = record.pos.entry_price;
                    const cur = record.ticker?.trade_price ?? record.snap?.price;
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
                  title: '수량',
                  dataIndex: 'pos',
                  width: 90,
                  align: 'right' as const,
                  render: (_: unknown, record: RowType) =>
                    record.pos ? (
                      <Text style={{ fontSize: 12 }}>{record.pos.volume.toFixed(4)}</Text>
                    ) : (
                      <Text type="secondary" style={{ fontSize: 12 }}>-</Text>
                    ),
                },
                {
                  title: '투입금액',
                  dataIndex: 'pos',
                  width: 110,
                  align: 'right' as const,
                  render: (_: unknown, record: RowType) =>
                    record.pos ? (
                      <Text style={{ fontSize: 12 }}>{Math.round(record.pos.amount).toLocaleString()}</Text>
                    ) : (
                      <Text type="secondary" style={{ fontSize: 12 }}>-</Text>
                    ),
                },
                {
                  title: '수익률',
                  width: 80,
                  align: 'right' as const,
                  render: (_: unknown, record: RowType) => {
                    if (!record.pos) return <Text type="secondary" style={{ fontSize: 12 }}>-</Text>;
                    const currentPrice = record.ticker?.trade_price ?? record.snap?.price;
                    if (!currentPrice) return <Text type="secondary" style={{ fontSize: 12 }}>-</Text>;
                    const pnlPct = ((currentPrice - record.pos.entry_price) / record.pos.entry_price) * 100;
                    const color = pnlPct >= 0 ? COLOR_RISE : COLOR_FALL;
                    return (
                      <Text style={{ fontSize: 12, color, fontWeight: 600 }}>
                        {pnlPct >= 0 ? '+' : ''}{pnlPct.toFixed(2)}%
                      </Text>
                    );
                  },
                },
                {
                  title: '손절가',
                  width: 100,
                  align: 'right' as const,
                  render: (_: unknown, record: RowType) => {
                    const sl = record.snap?.stop_loss;
                    if (!sl) return <Text type="secondary" style={{ fontSize: 12 }}>-</Text>;
                    return <Text style={{ fontSize: 12, color: COLOR_FALL }}>{Math.round(sl).toLocaleString()}</Text>;
                  },
                },
                {
                  title: '익절가',
                  width: 100,
                  align: 'right' as const,
                  render: (_: unknown, record: RowType) => {
                    const tp = record.snap?.take_profit;
                    if (!tp) return <Text type="secondary" style={{ fontSize: 12 }}>-</Text>;
                    return <Text style={{ fontSize: 12, color: COLOR_RISE }}>{Math.round(tp).toLocaleString()}</Text>;
                  },
                },
              ]}
            />
          );
        })()}
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
    </Flex>
  );
}
