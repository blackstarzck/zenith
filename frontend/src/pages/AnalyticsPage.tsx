import {
  Card,
  Table,
  Tag,
  Typography,
  Tabs,
  Flex,
  Row,
  Col,
  Statistic,
  Spin,
} from 'antd';
import {
  TrophyOutlined,
  FallOutlined,
  PercentageOutlined,
} from '@ant-design/icons';
import { Line } from '@ant-design/charts';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';
import { useTrades, useDailyStats } from '../hooks/useSupabase';
import type { Trade } from '../types/database';

const { Title, Text } = Typography;

/* ── Trade History 컬럼 ─────────────────────────────────── */

const historyColumns: ColumnsType<Trade> = [
  {
    title: '시간',
    dataIndex: 'created_at',
    width: 160,
    render: (v: string) => dayjs(v).format('YYYY-MM-DD HH:mm'),
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
    width: 140,
    align: 'right',
    render: (v: number) => `${v.toLocaleString()}`,
  },
  {
    title: '수량',
    dataIndex: 'volume',
    width: 120,
    align: 'right',
    render: (v: number) => v.toFixed(8),
  },
  {
    title: '금액',
    dataIndex: 'amount',
    width: 140,
    align: 'right',
    render: (v: number) => `${Math.round(v).toLocaleString()} KRW`,
  },
  {
    title: '수수료',
    dataIndex: 'fee',
    width: 100,
    align: 'right',
    render: (v: number) => `${Math.round(v).toLocaleString()}`,
  },
  {
    title: '손익',
    dataIndex: 'pnl',
    width: 120,
    align: 'right',
    render: (v: number | null, record: Trade) => {
      if (record.side === 'bid') return <Text type="secondary">-</Text>;
      if (v == null) return <Text type="secondary">-</Text>;
      const color = v >= 0 ? '#52c41a' : '#ff4d4f';
      return <Text style={{ color }}>{`${v >= 0 ? '+' : ''}${Math.round(v).toLocaleString()}`}</Text>;
    },
  },
];

/* ── Analytics Page ────────────────────────────────────── */

export default function AnalyticsPage() {
  const { trades, loading: tradesLoading } = useTrades(200);
  const { stats, loading: statsLoading } = useDailyStats(90);

  // 성과 지표 계산
  const sellTrades = trades.filter((t) => t.side === 'ask');
  const buyTrades = trades.filter((t) => t.side === 'bid');
  const totalTrades = sellTrades.length;

  // MDD 계산
  const mdd =
    stats.length > 0
      ? Math.min(...stats.map((s) => s.drawdown))
      : 0;

  // 일별 손익 차트
  const pnlChartData = stats.map((s) => ({
    date: s.stats_date,
    profit: s.net_profit,
  }));

  const pnlLineConfig = {
    data: pnlChartData,
    xField: 'date',
    yField: 'profit',
    smooth: true,
    theme: 'classicDark',
    height: 300,
    color: '#1668dc',

    xAxis: {
      label: {
        formatter: (v: string) => dayjs(v).format('MM/DD'),
      },
    },
    yAxis: {
      label: {
        formatter: (v: string) => `${(Number(v) / 10000).toFixed(0)}만`,
      },
    },
    annotations: [
      {
        type: 'line',
        yField: 0,
        style: { stroke: '#ff4d4f', lineDash: [4, 4] },
      },
    ],
  };

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
        Analytics
      </Title>

      {/* ── 성과 지표 카드 ── */}
      <Row gutter={[16, 16]}>
        <Col xs={24} sm={8}>
          <Card variant="borderless">
            <Statistic
              title="총 거래 횟수"
              value={totalTrades + buyTrades.length}
              prefix={<TrophyOutlined />}
              suffix="건"
            />
          </Card>
        </Col>
        <Col xs={24} sm={8}>
          <Card variant="borderless">
            <Statistic
              title="매도 거래"
              value={totalTrades}
              prefix={<PercentageOutlined />}
              suffix="건"
            />
          </Card>
        </Col>
        <Col xs={24} sm={8}>
          <Card variant="borderless">
            <Statistic
              title="최대 낙폭 (MDD)"
              value={mdd}
              precision={2}
              prefix={<FallOutlined />}
              suffix="%"
              styles={{ content: { color: mdd < -5 ? '#ff4d4f' : '#52c41a' } }}
            />
          </Card>
        </Col>
      </Row>

      <Card variant="borderless">
        <Tabs
          defaultActiveKey="history"
          items={[
            {
              key: 'history',
              label: 'Trade History',
              children: (
                <Table<Trade>
                  columns={historyColumns}
                  dataSource={trades}
                  rowKey="id"
                  size="small"
                  pagination={{ pageSize: 15, showSizeChanger: true }}
                  loading={tradesLoading}
                  scroll={{ x: 800 }}
                />
              ),
            },
            {
              key: 'benchmark',
              label: 'Benchmarking',
              children: (
                <Card title="일별 손익 추이" variant="borderless" loading={statsLoading}>
                  {pnlChartData.length > 0 ? (
                    <Line {...pnlLineConfig} />
                  ) : (
                    <div style={{ textAlign: 'center', padding: 60, color: '#666' }}>
                      데이터가 아직 없습니다.
                    </div>
                  )}
                </Card>
              ),
            },
          ]}
        />
      </Card>
    </Flex>
  );
}
