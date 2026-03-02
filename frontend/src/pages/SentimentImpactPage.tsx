import { useMemo, useState } from 'react';
import {
  Card, Col, Empty, Flex, Row, Segmented, Spin, Statistic, Table, Tag, Typography,
} from 'antd';
import {
  AimOutlined, CheckCircleOutlined, LineChartOutlined, PercentageOutlined,
} from '@ant-design/icons';
import { Line } from '@ant-design/charts';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';
import 'dayjs/locale/ko';
import {
  usePriceSnapshotsRange,
  useSentimentInsights,
  useSentimentPerformanceDaily,
} from '../hooks/useSupabase';
import AssetGrowthChart from '../components/AssetGrowthChart';
import type { SentimentInsight } from '../types/database';

const { Title, Text } = Typography;
dayjs.locale('ko');

type RangeDays = 1 | 7 | 30 | 90;

const DECISION_COLOR: Record<SentimentInsight['decision'], string> = {
  BUY: 'green',
  SELL: 'red',
  HOLD: 'gold',
  WAIT: 'default',
  PENDING: 'blue',
};

const DECISION_LABEL: Record<SentimentInsight['decision'], string> = {
  BUY: '매수',
  SELL: '매도',
  HOLD: '보류',
  WAIT: '대기',
  PENDING: '분석중',
};

const RESULT_LABEL: Record<NonNullable<SentimentInsight['verification_result']>, string> = {
  correct: '적중',
  incorrect: '오판',
  neutral: '중립',
};

function isDirectionalDecision(decision: string) {
  return decision === 'BUY' || decision === 'SELL';
}

function isDirectionMatched(item: SentimentInsight) {
  if (!isDirectionalDecision(item.decision) || item.actual_price_change == null) return null;
  if (item.decision === 'BUY') return item.actual_price_change > 0;
  return item.actual_price_change < 0;
}

function summarizeText(text: string | null | undefined) {
  if (!text) return '근거 요약 없음';
  return text.replace(/\s+/g, ' ').trim();
}

function toKrwSymbol(raw: string | null | undefined) {
  if (!raw) return null;
  const upper = raw.toUpperCase().trim();
  if (!upper) return null;
  if (upper.startsWith('KRW-')) return upper;
  if (upper.includes('-')) return `KRW-${upper.split('-').pop()}`;
  return `KRW-${upper}`;
}

function getCoinChartRange(startAt: string, endAt: string): '1h' | '1d' | 7 | 30 {
  const mins = Math.max(1, dayjs(endAt).diff(dayjs(startAt), 'minute'));
  if (mins <= 60) return '1h';
  if (mins <= 60 * 24) return '1d';
  if (mins <= 60 * 24 * 7) return 7;
  return 30;
}

function VerificationCoinChart({ record }: { record: SentimentInsight }) {
  const symbol = toKrwSymbol(record.currencies?.[0]);
  // 사용자가 원하는 기준: 뉴스가 올라온 시각 이후 흐름
  const startAt = record.created_at;
  const endAt = record.verification_window_end_at
    ?? record.evaluated_at
    ?? dayjs(record.created_at).add(record.verification_horizon_min ?? 30, 'minute').toISOString();
  const chartEndAt = dayjs(endAt).add(20, 'minute').toISOString();
  const { snapshots, loading } = usePriceSnapshotsRange(symbol, startAt, chartEndAt, 1200);

  if (!symbol) {
    return <Text type="secondary">코인 정보가 없어 차트를 표시할 수 없습니다.</Text>;
  }
  if (loading) {
    return <Spin size="small" />;
  }
  if (snapshots.length < 2) {
    return <Text type="secondary">해당 검증 구간의 가격 스냅샷이 부족해 차트를 표시할 수 없습니다.</Text>;
  }

  const chartData = snapshots.map((s) => ({
    date: s.created_at,
    balance: s.price,
  }));
  const first = chartData[0]?.balance ?? 0;
  const last = chartData[chartData.length - 1]?.balance ?? 0;
  const isUp = last >= first;
  const chartRange = getCoinChartRange(startAt, chartEndAt);

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'minmax(220px, 1fr) 180px', gap: 12, alignItems: 'center' }}>
      <AssetGrowthChart
        data={chartData}
        height={220}
        chartRange={chartRange}
        highlightStartAt={startAt}
        highlightEndAt={endAt}
        pinOneHourToNow={false}
      />
      <div
        style={{
          background: '#141414',
          border: '1px solid #252525',
          borderRadius: 6,
          padding: '10px 12px',
          display: 'flex',
          flexDirection: 'column',
          gap: 6,
        }}
      >
        <Text style={{ fontSize: 11, color: '#8c8c8c' }}>
          코인
        </Text>
        <Text style={{ fontSize: 14, color: '#d9d9d9', fontWeight: 600 }}>
          {symbol}
        </Text>
        <Text style={{ fontSize: 11, color: '#8c8c8c' }}>
          구간 변동
        </Text>
        <Text style={{ fontSize: 18, fontWeight: 700, color: isUp ? '#52c41a' : '#ff4d4f' }}>
          {first > 0 ? `${((last / first - 1) * 100 >= 0 ? '+' : '')}${((last / first - 1) * 100).toFixed(2)}%` : '-'}
        </Text>
        <Text style={{ fontSize: 11, color: '#8c8c8c' }}>
          시작 시각
        </Text>
        <Text style={{ fontSize: 12, color: '#bfbfbf' }}>
          {dayjs(startAt).format('M월 D일 HH:mm')}
        </Text>
      </div>
    </div>
  );
}

export default function SentimentImpactPage() {
  const [rangeDays, setRangeDays] = useState<RangeDays>(7);
  const { insights, loading } = useSentimentInsights(500);
  const { items: dailyItems, loading: dailyLoading } = useSentimentPerformanceDaily(120);

  const filtered = useMemo(() => {
    const since = dayjs().subtract(rangeDays, 'day');
    return insights.filter((item) => dayjs(item.created_at).isAfter(since));
  }, [insights, rangeDays]);

  const verified = useMemo(
    () => filtered.filter((item) => item.verification_result !== null),
    [filtered],
  );
  const verifiedScored = useMemo(
    () => verified.filter((item) => item.verification_result !== 'neutral'),
    [verified],
  );

  const directional = useMemo(
    () => verified.filter((item) => isDirectionalDecision(item.decision) && item.actual_price_change !== null),
    [verified],
  );

  const backendCorrectCount = verifiedScored.filter((item) => item.verification_result === 'correct').length;
  const backendAccuracy = verifiedScored.length > 0 ? (backendCorrectCount / verifiedScored.length) * 100 : 0;

  const directionMatchedCount = directional.filter((item) => isDirectionMatched(item)).length;
  const directionAccuracy = directional.length > 0 ? (directionMatchedCount / directional.length) * 100 : 0;

  const avgActualMove = directional.length > 0
    ? directional.reduce((sum, item) => sum + Math.abs(item.actual_price_change ?? 0), 0) / directional.length
    : 0;

  const confidence70 = directional.filter((item) => item.confidence >= 70);
  const confidence70MatchedCount = confidence70.filter((item) => isDirectionMatched(item)).length;
  const confidence70Accuracy = confidence70.length > 0
    ? (confidence70MatchedCount / confidence70.length) * 100
    : 0;

  const dailyAccuracyData = useMemo(() => {
    const since = dayjs().subtract(rangeDays, 'day');
    const grouped = new Map<string, { verified: number; correct: number }>();

    for (const row of dailyItems) {
      if (row.currency !== 'ALL') continue;
      if (!isDirectionalDecision(row.decision)) continue;
      if (!dayjs(row.stats_date).isAfter(since)) continue;
      const key = row.stats_date;
      const prev = grouped.get(key) ?? { verified: 0, correct: 0 };
      grouped.set(key, {
        verified: prev.verified + row.verified_count,
        correct: prev.correct + row.correct_count,
      });
    }

    return [...grouped.entries()]
      .sort((a, b) => dayjs(a[0]).valueOf() - dayjs(b[0]).valueOf())
      .map(([date, value]) => ({
        date,
        accuracy: value.verified > 0 ? Number(((value.correct / value.verified) * 100).toFixed(2)) : 0,
      }));
  }, [dailyItems, rangeDays]);

  const lineConfig = {
    data: dailyAccuracyData,
    xField: 'date',
    yField: 'accuracy',
    smooth: true,
    height: 280,
    color: '#52c41a',
    theme: 'classicDark',
    xAxis: {
      label: {
        formatter: (v: string) => dayjs(v).format('MM/DD'),
      },
    },
    yAxis: {
      label: {
        formatter: (v: string) => `${v}%`,
      },
      min: 0,
      max: 100,
    },
  };

  const columns: ColumnsType<SentimentInsight> = [
    {
      title: '시각',
      dataIndex: 'created_at',
      width: 140,
      render: (v: string) => dayjs(v).format('M월 D일 ddd요일 HH시 mm분'),
    },
    {
      title: '코인',
      dataIndex: 'currencies',
      width: 130,
      render: (v: string[]) => (v.length > 0 ? v.join(', ') : '-'),
    },
    {
      title: 'AI 결정',
      dataIndex: 'decision',
      width: 100,
      render: (v: SentimentInsight['decision']) => (
        <Tag color={DECISION_COLOR[v]}>{DECISION_LABEL[v]}</Tag>
      ),
    },
    {
      title: '검증 기준',
      dataIndex: 'verification_horizon_min',
      width: 100,
      align: 'right',
      render: (v: number | null) => (v ? `${v}분` : '-'),
    },
    {
      title: '실제 변화',
      dataIndex: 'actual_price_change',
      width: 110,
      align: 'right',
      render: (v: number | null) => {
        if (v == null) return <Text type="secondary">-</Text>;
        return (
          <Text style={{ color: v >= 0 ? '#52c41a' : '#ff4d4f' }}>
            {`${v >= 0 ? '+' : ''}${v.toFixed(2)}%`}
          </Text>
        );
      },
    },
    {
      title: '검증 결과',
      dataIndex: 'verification_result',
      width: 110,
      render: (v: SentimentInsight['verification_result']) => {
        if (!v) return <Text type="secondary">미검증</Text>;
        const color = v === 'correct' ? 'success' : v === 'neutral' ? 'gold' : 'error';
        return <Tag color={color}>{RESULT_LABEL[v]}</Tag>;
      },
    },
    {
      title: '대기 사유',
      dataIndex: 'pending_reason',
      width: 140,
      render: (v: string | null) => v || '-',
    },
    {
      title: '뉴스 제목',
      dataIndex: 'title',
      ellipsis: true,
      render: (v: string) => <Text>{v}</Text>,
    },
  ];

  if (loading && insights.length === 0) {
    return (
      <div style={{ textAlign: 'center', padding: 80 }}>
        <Spin size="large" />
      </div>
    );
  }

  return (
    <Flex vertical gap={16}>
      <Flex justify="space-between" align="center" wrap="wrap" gap={12}>
        <Title level={4} style={{ margin: 0 }}>
          AI 감성 영향도 검증
        </Title>
        <Segmented
          value={rangeDays}
          onChange={(value) => setRangeDays(value as RangeDays)}
          options={[
            { label: '1일', value: 1 },
            { label: '7일', value: 7 },
            { label: '30일', value: 30 },
            { label: '90일', value: 90 },
          ]}
        />
      </Flex>

      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} lg={6}>
          <Card variant="borderless">
            <Statistic
              title="검증 정확도(중립 제외)"
              value={backendAccuracy}
              precision={1}
              suffix="%"
              prefix={<CheckCircleOutlined />}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card variant="borderless">
            <Statistic
              title="방향 일치율"
              value={directionAccuracy}
              precision={1}
              suffix="%"
              prefix={<AimOutlined />}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card variant="borderless">
            <Statistic
              title="평균 실제 변동"
              value={avgActualMove}
              precision={2}
              suffix="%"
              prefix={<LineChartOutlined />}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card variant="borderless">
            <Statistic
              title="고신뢰(70+) 일치율"
              value={confidence70Accuracy}
              precision={1}
              suffix="%"
              prefix={<PercentageOutlined />}
            />
          </Card>
        </Col>
      </Row>

      <Card title="감성 평가 안내" variant="borderless">
        <Row gutter={[12, 12]}>
          <Col xs={24} md={12}>
            <Text strong style={{ display: 'block', marginBottom: 6 }}>평가 절차</Text>
            <Text type="secondary" style={{ whiteSpace: 'pre-wrap' }}>
              {`1) 뉴스가 올라온 시간을 기준으로, 그 뒤 가격이 어떻게 움직였는지 봅니다.
2) 가격은 업비트 1분 단위 데이터로 확인합니다. (1분마다 가격을 찍어 둔 기록)
3) AI가 "오를 것(BUY)" 또는 "내릴 것(SELL)"이라고 말한 방향과 실제 방향을 비교합니다.
4) 가격이 아주 조금만 움직인 경우(±0.15% 이내)는 맞다/틀리다를 억지로 정하지 않고 "중립(neutral)"으로 둡니다.

쉽게 말해:
- AI가 오를 거라고 했는데 실제로 충분히 오르면 적중
- AI가 내릴 거라고 했는데 실제로 충분히 내리면 적중
- 거의 안 움직였으면 중립 처리`}
            </Text>
          </Col>
          <Col xs={24} md={12}>
            <Text strong style={{ display: 'block', marginBottom: 6 }}>현재 기준 수치</Text>
            <Text type="secondary" style={{ whiteSpace: 'pre-wrap' }}>
              {`- AI가 강하게 확신한 경우만 매수/매도 의견으로 인정합니다.
  (신뢰도 80점 이상 + 감성 점수 절대값 0.45 이상)
- 검증 시간은 2가지로 나눕니다.
  - 확신이 높은 신호: 30분 동안 결과 확인
  - 일반 신호: 180분(3시간) 동안 결과 확인
- 관망(HOLD/WAIT)은 가격이 ±0.30% 안에서만 움직이면 맞았다고 봅니다.
- 매수/매도는 가격이 ±0.15% 이내로만 움직였으면 중립으로 처리합니다.
  (중립은 정확도 계산에서 제외)`}
            </Text>
          </Col>
        </Row>
      </Card>

      <Card
        title="일자별 방향 일치율 추이"
        variant="borderless"
        extra={<Text type="secondary">집계 {dailyLoading ? '로딩중' : `${dailyAccuracyData.length}일`}</Text>}
      >
        {dailyAccuracyData.length > 0 ? (
          <Line {...lineConfig} />
        ) : (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description="선택한 기간의 방향 검증 데이터가 없습니다."
          />
        )}
      </Card>

      <Card
        title="검증 상세 로그"
        variant="borderless"
        extra={<Text type="secondary">전체 {filtered.length}건 · 유효평가 {verifiedScored.length}건</Text>}
      >
        <Table<SentimentInsight>
          rowKey="id"
          size="small"
          columns={columns}
          dataSource={filtered}
        expandable={{
            expandedRowRender: (record) => (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12, padding: '4px 0' }}>
                {(() => {
                  const decisionText = DECISION_LABEL[record.decision] ?? record.decision;
                  const actual = record.actual_price_change;
                  const actualColor = actual == null ? '#8c8c8c' : (actual >= 0 ? '#52c41a' : '#ff4d4f');
                  const resultText = record.verification_result ? RESULT_LABEL[record.verification_result] : '미검증';
                  const reasoningText = summarizeText(record.reasoning_chain);
                  const insightText = summarizeText(record.analysis_insight);
                  const showInsight = Boolean(record.analysis_insight) && reasoningText !== insightText;

                  return (
                    <>
                      {/* 1) 핵심 결과 요약 */}
                      <div
                        style={{
                          background: 'linear-gradient(135deg, rgba(82, 196, 26, 0.08), rgba(82, 196, 26, 0.03))',
                          border: '1px solid rgba(82, 196, 26, 0.2)',
                          borderRadius: 8,
                          padding: '12px 16px',
                        }}
                      >
                        <Text style={{ fontSize: 11, color: '#52c41a', fontWeight: 600, display: 'block', marginBottom: 6 }}>
                          핵심 결과
                        </Text>
                        <Text style={{ fontSize: 13, color: '#e8e8e8', display: 'block' }}>
                          AI 초기 판단: <b>{decisionText}</b> · 신뢰도 <b>{record.confidence.toFixed(0)}점</b>
                        </Text>
                        <Text style={{ fontSize: 13, color: actualColor }}>
                          실제 시장: {actual == null ? '검증 대기 중' : `${actual >= 0 ? '+' : ''}${actual.toFixed(2)}%`} ({resultText})
                        </Text>
                      </div>

                      {/* 2) AI 근거/해석 */}
                      <div
                        style={{
                          background: 'linear-gradient(135deg, rgba(22, 119, 255, 0.08), rgba(22, 119, 255, 0.03))',
                          border: '1px solid rgba(22, 119, 255, 0.2)',
                          borderRadius: 8,
                          padding: '12px 16px',
                        }}
                      >
                        <Text style={{ fontSize: 11, color: '#1677ff', fontWeight: 600, display: 'block', marginBottom: 6 }}>
                          AI 근거 / 해석
                        </Text>
                        <Text style={{ fontSize: 11, color: '#91caff', display: 'block', marginBottom: 2 }}>
                          초기 추론 근거
                        </Text>
                        <Text style={{ color: '#e8e8e8', fontSize: 13, lineHeight: 1.7, whiteSpace: 'pre-wrap' }}>
                          {reasoningText}
                        </Text>
                        {showInsight && (
                          <>
                            <Text style={{ fontSize: 11, color: '#91caff', display: 'block', marginTop: 8, marginBottom: 2 }}>
                              사후 인사이트
                            </Text>
                            <Text style={{ color: '#e8e8e8', fontSize: 13, lineHeight: 1.7, whiteSpace: 'pre-wrap' }}>
                              {insightText}
                            </Text>
                          </>
                        )}
                      </div>
                    </>
                  );
                })()}

                {/* 3) 코인 차트 */}
                <div
                  style={{
                    background: '#141414',
                    border: '1px solid #303030',
                    borderRadius: 8,
                    padding: '12px 16px',
                  }}
                >
                  <Text style={{ fontSize: 11, color: '#8c8c8c', fontWeight: 600, display: 'block', marginBottom: 6 }}>
                    코인 차트
                  </Text>
                  <VerificationCoinChart record={record} />
                </div>
              </div>
            ),
            rowExpandable: (record) =>
              record.reasoning_chain != null ||
              (record.currencies?.length ?? 0) > 0 ||
              record.analysis_insight != null ||
              record.window_return_pct != null,
          }}
          pagination={{ pageSize: 12, showSizeChanger: true }}
          scroll={{ x: 1200 }}
        />
      </Card>
    </Flex>
  );
}
