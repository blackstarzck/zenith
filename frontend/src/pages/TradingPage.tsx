import { useState, useMemo } from 'react';
import {
  Row,
  Col,
  Card,
  Table,
  Tag,
  Typography,
  Tabs,
  Flex,
  Badge,
  Descriptions,
  Empty,
  Button,
} from 'antd';
import {
  ThunderboltOutlined,
  ControlOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';
import { useTrades, useSystemLogs } from '../hooks/useSupabase';
import type { Trade, SystemLog } from '../types/database';
import EmergencySellModal from '../components/EmergencySellModal';
import type { EmergencyPosition } from '../components/EmergencySellModal';
import ManualOverrideModal from '../components/ManualOverrideModal';
import type { BotStatus } from '../components/ManualOverrideModal';
import StrategyHealthRadar from '../components/StrategyHealthRadar';

const { Title, Text } = Typography;

/* ── Active Positions 컬럼 (매수된 것 중 아직 매도되지 않은 것) ── */

const positionColumns: ColumnsType<Trade> = [
  {
    title: '종목',
    dataIndex: 'symbol',
    width: 120,
    render: (v: string) => <Text strong>{v.replace('KRW-', '')}</Text>,
  },
  {
    title: '매수 가격',
    dataIndex: 'price',
    width: 140,
    align: 'right',
    render: (v: number) => `${v.toLocaleString()} KRW`,
  },
  {
    title: '수량',
    dataIndex: 'volume',
    width: 140,
    align: 'right',
    render: (v: number, record: Trade) => {
      if (record.side === 'ask' && record.remaining_volume != null && record.remaining_volume > 0) {
        return (
          <span>
            {v.toFixed(8)}
            <br />
            <Text type="secondary" style={{ fontSize: 11 }}>
              잔여: {record.remaining_volume.toFixed(8)}
            </Text>
          </span>
        );
      }
      return v.toFixed(8);
    },
  },
  {
    title: '투입 금액',
    dataIndex: 'amount',
    width: 140,
    align: 'right',
    render: (v: number) => `${Math.round(v).toLocaleString()} KRW`,
  },
  {
    title: '시간',
    dataIndex: 'created_at',
    width: 160,
    render: (v: string) => dayjs(v).format('MM-DD HH:mm:ss'),
  },
];

/* ── 실시간 로그 컬럼 ──────────────────────────────────── */

const logColumns: ColumnsType<SystemLog> = [
  {
    title: '시간',
    dataIndex: 'created_at',
    width: 100,
    render: (v: string) => dayjs(v).format('HH:mm:ss'),
  },
  {
    title: '레벨',
    dataIndex: 'level',
    width: 80,
    render: (v: string) => {
      const color = v === 'ERROR' ? 'red' : v === 'WARNING' ? 'orange' : 'green';
      return <Tag color={color}>{v}</Tag>;
    },
  },
  {
    title: '메시지',
    dataIndex: 'message',
    ellipsis: true,
  },
];

/* ── Trading Page ──────────────────────────────────────── */

export default function TradingPage() {
  const { trades, loading: tradesLoading } = useTrades(100);
  const { logs, loading: logsLoading } = useSystemLogs(null, 50);

  const [emergencyOpen, setEmergencyOpen] = useState(false);
  const [overrideOpen, setOverrideOpen] = useState(false);
  const [selectedPosition, setSelectedPosition] = useState<EmergencyPosition | null>(null);
  const [botStatus, setBotStatus] = useState<BotStatus>('active');

  // 종목별 최신 거래를 확인하여 활성 포지션 추출 (remaining_volume 기반)
  const activePositions = useMemo(() => {
    const fullyLiquidated = new Set<string>();
    const positionBySymbol = new Map<string, Trade>();

    for (const trade of trades) {
      if (positionBySymbol.has(trade.symbol) || fullyLiquidated.has(trade.symbol)) continue;

      if (trade.side === 'ask') {
        if (trade.remaining_volume != null && trade.remaining_volume <= 0) {
          fullyLiquidated.add(trade.symbol);
        }
        continue;
      }

      // bid → 활성 포지션
      positionBySymbol.set(trade.symbol, trade);
    }

    return [...positionBySymbol.values()];
  }, [trades]);

  const handleEmergencySell = (trade: Trade) => {
    setSelectedPosition({
      symbol: trade.symbol,
      volume: trade.volume,
      currentPrice: trade.price,
      avgPrice: trade.price,
      pnl: 0,
    });
    setEmergencyOpen(true);
  };

  const positionColumnsWithAction: ColumnsType<Trade> = [
    ...positionColumns,
    {
      title: '액션',
      width: 80,
      align: 'center',
      render: (_: unknown, record: Trade) => (
        <Button
          danger
          size="small"
          icon={<ThunderboltOutlined />}
          onClick={() => handleEmergencySell(record)}
        >
          매도
        </Button>
      ),
    },
  ];

  /* ── 거래내역 컬럼 (매도 시 잔여 수량 표시) ── */
  const tradeHistoryColumns: ColumnsType<Trade> = [
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
      align: 'center',
      render: (v: string) => (
        <Tag color={v === 'bid' ? '#ff4d4f' : '#1890ff'}>
          {v === 'bid' ? '매수' : '매도'}
        </Tag>
      ),
    },
    {
      title: '가격',
      dataIndex: 'price',
      width: 140,
      align: 'right',
      render: (v: number) => `${v.toLocaleString()} KRW`,
    },
    {
      title: '수량',
      dataIndex: 'volume',
      width: 160,
      align: 'right',
      render: (v: number, record: Trade) => {
        if (record.side === 'ask' && record.remaining_volume != null) {
          return (
            <span>
              {v.toFixed(8)}
              <br />
              <Text type="secondary" style={{ fontSize: 11 }}>
                {record.remaining_volume > 0
                  ? `잔여: ${record.remaining_volume.toFixed(8)}`
                  : '잔여: 없음 (전량)'}
              </Text>
            </span>
          );
        }
        return v.toFixed(8);
      },
    },
    {
      title: '금액',
      dataIndex: 'amount',
      width: 140,
      align: 'right',
      render: (v: number) => `${Math.round(v).toLocaleString()} KRW`,
    },
    {
      title: '손익',
      dataIndex: 'pnl',
      width: 120,
      align: 'right',
      render: (v: number | null) => {
        if (v == null) return '-';
        const color = v > 0 ? '#ff4d4f' : v < 0 ? '#1890ff' : '#999';
        const prefix = v > 0 ? '+' : '';
        return <Text style={{ color }}>{prefix}{Math.round(v).toLocaleString()}</Text>;
      },
    },
    {
      title: '시간',
      dataIndex: 'created_at',
      width: 160,
      render: (v: string) => dayjs(v).format('MM-DD HH:mm:ss'),
    },
  ];

  return (
    <Flex vertical gap={24} style={{ width: '100%' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Title level={4} style={{ margin: 0 }}>
          Trading
        </Title>
        <Flex gap={8}>
          <Button
            danger
            icon={<ThunderboltOutlined />}
            onClick={() => {
              if (activePositions.length > 0) {
                handleEmergencySell(activePositions[0]);
              }
            }}
            disabled={activePositions.length === 0}
          >
            긴급 매도
          </Button>
          <Button
            icon={<ControlOutlined />}
            style={{ borderColor: '#faad14', color: '#faad14' }}
            onClick={() => setOverrideOpen(true)}
          >
            수동 제어
          </Button>
        </Flex>
      </div>

      <Row gutter={[16, 16]}>
        {/* ── 좌측: 포지션 ── */}
        <Col xs={24} lg={14}>
          <Card variant="borderless">
            <Tabs
              defaultActiveKey="active"
              items={[
                {
                  key: 'active',
                  label: (
                    <span>
                      Active Positions <Badge count={activePositions.length} showZero />
                    </span>
                  ),
                  children: activePositions.length > 0 ? (
                    <Table<Trade>
                      columns={positionColumnsWithAction}
                      dataSource={activePositions}
                      rowKey="id"
                      size="small"
                      pagination={false}
                      loading={tradesLoading}
                    />
                  ) : (
                    <Empty description="보유 포지션 없음" />
                  ),
                },
                {
                  key: 'history',
                  label: '거래내역',
                  children: (
                    <Table<Trade>
                      columns={tradeHistoryColumns}
                      dataSource={trades}
                      rowKey="id"
                      size="small"
                      pagination={{ pageSize: 10 }}
                      loading={tradesLoading}
                    />
                  ),
                },
              ]}
            />
          </Card>
        </Col>

        {/* ── 우측: 전략 상태 ── */}
        <Col xs={24} lg={10}>
          <Card title="전략 상태" variant="borderless" style={{ marginBottom: 16 }}>
            <Descriptions column={1} size="small" bordered>
              <Descriptions.Item label="전략">
                변동성 조절형 평균 회귀
              </Descriptions.Item>
              <Descriptions.Item label="BB 기간">20일</Descriptions.Item>
              <Descriptions.Item label="BB 표준편차">2.0σ</Descriptions.Item>
              <Descriptions.Item label="RSI 기간">14</Descriptions.Item>
              <Descriptions.Item label="RSI 과매도">≤ 30</Descriptions.Item>
              <Descriptions.Item label="ATR 손절 계수">2.5x</Descriptions.Item>
              <Descriptions.Item label="최대 포지션">5종목</Descriptions.Item>
              <Descriptions.Item label="일일 손실 한도">5%</Descriptions.Item>
            </Descriptions>
          </Card>
          <StrategyHealthRadar />
        </Col>
      </Row>

      {/* ── 하단: 실시간 로그 터미널 ── */}
      <Card
        title="실시간 로그"
        variant="borderless"
        styles={{
          body: {
            maxHeight: 360,
            overflow: 'auto',
            background: '#0d0d0d',
            padding: 0,
          },
        }}
      >
        <Table<SystemLog>
          columns={logColumns}
          dataSource={logs}
          rowKey="id"
          size="small"
          pagination={false}
          loading={logsLoading}
          style={{ background: '#0d0d0d' }}
        />
      </Card>

      {/* ── Modals ── */}
      <EmergencySellModal
        open={emergencyOpen}
        onClose={() => setEmergencyOpen(false)}
        position={selectedPosition}
      />
      <ManualOverrideModal
        open={overrideOpen}
        onClose={() => setOverrideOpen(false)}
        botStatus={botStatus}
        onBotToggle={(paused) => setBotStatus(paused ? 'paused' : 'active')}
        positions={activePositions.map((t) => ({ symbol: t.symbol, pnl: 0 }))}
        onClosePosition={(symbol) => {
          const trade = activePositions.find((t) => t.symbol === symbol);
          if (trade) handleEmergencySell(trade);
          setOverrideOpen(false);
        }}
      />
    </Flex>
  );
}
