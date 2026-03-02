import { useState } from 'react';
import { Card, Tag, Typography, Space, Empty, Spin } from 'antd';
import { LinkOutlined, CheckCircleOutlined, CloseCircleOutlined, RiseOutlined, FallOutlined, PauseCircleOutlined, ClockCircleOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import relativeTime from 'dayjs/plugin/relativeTime';
import 'dayjs/locale/ko';
import type { SentimentInsight } from '../types/database';

dayjs.extend(relativeTime);
dayjs.locale('ko');

const { Text, Paragraph } = Typography;

interface SentimentInsightPanelProps {
  insights: SentimentInsight[];
  loading: boolean;
}

const COLOR_BULLISH = '#52c41a';
const COLOR_BEARISH = '#ff4d4f';
const COLOR_NEUTRAL = '#faad14';

const DECISION_COLORS: Record<string, string> = {
  BUY: '#52c41a',
  SELL: '#ff4d4f',
  HOLD: '#faad14',
  WAIT: '#8c8c8c',
  PENDING: '#1890ff',
};

const DECISION_ICONS: Record<string, React.ReactNode> = {
  BUY: <RiseOutlined />,
  SELL: <FallOutlined />,
  HOLD: <PauseCircleOutlined />,
  WAIT: <ClockCircleOutlined />,
};

const DECISION_LABELS: Record<string, string> = {
  BUY: '매수',
  SELL: '매도',
  HOLD: '보류',
  WAIT: '대기',
  PENDING: 'AI 분석 중',
};

export default function SentimentInsightPanel({ insights, loading }: SentimentInsightPanelProps) {
  const [expandedKeys, setExpandedKeys] = useState<string[]>([]);

  if (loading && insights.length === 0) {
    return (
      <div style={{ textAlign: 'center', padding: 40 }}>
        <Spin size="large" />
        <div style={{ marginTop: 16 }}>
          <Text type="secondary">뉴스 감성 분석 데이터를 불러오는 중...</Text>
        </div>
      </div>
    );
  }

  if (insights.length === 0) {
    return (
      <Empty
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        description={<Text type="secondary">아직 분석된 뉴스가 없습니다</Text>}
        style={{ padding: 40 }}
      />
    );
  }

  // 최근 24시간 예측 적중률 계산
  const last24h = dayjs().subtract(24, 'hour');
  const recentInsights = insights.filter((i) => dayjs(i.created_at).isAfter(last24h));
  const verifiedInsights = recentInsights.filter((i) => i.verification_result !== null);
  const correctCount = verifiedInsights.filter((i) => i.verification_result === 'correct').length;
  const accuracy = verifiedInsights.length > 0 ? Math.round((correctCount / verifiedInsights.length) * 100) : 0;

  return (
    <div style={{ padding: 16, background: '#0d0d0d', minHeight: '100%', display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* 상단 요약 바 */}
      <div style={{ background: '#141414', padding: '12px 16px', borderRadius: 8, border: '1px solid #303030', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Text style={{ color: '#e0e0e0', fontSize: 13 }}>최근 24시간 예측 적중률</Text>
        <Space>
          <Text strong style={{ color: accuracy >= 50 ? COLOR_BULLISH : COLOR_BEARISH, fontSize: 16 }}>
            {verifiedInsights.length > 0 ? `${accuracy}%` : '-'}
          </Text>
          <Text type="secondary" style={{ fontSize: 12 }}>
            ({correctCount}/{verifiedInsights.length})
          </Text>
        </Space>
      </div>

      {/* 카드 리스트 */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {insights.map((insight) => {
          const isExpanded = expandedKeys.includes(insight.id.toString());
          const toggleExpand = () => {
            setExpandedKeys((prev) =>
              prev.includes(insight.id.toString())
                ? prev.filter((k) => k !== insight.id.toString())
                : [...prev, insight.id.toString()]
            );
          };

          // 감성 바 계산
          const score = insight.sentiment_score; // -1.0 ~ 1.0
          const isPositive = score > 0;
          const barWidth = `${Math.abs(score) * 50}%`;
          const barColor = isPositive ? '#1890ff' : COLOR_BEARISH; // 파란색/빨간색
          const barLeft = isPositive ? '50%' : `${50 - Math.abs(score) * 50}%`;

          return (
            <Card
              key={insight.id}
              size="small"
              style={{
                background: '#141414',
                borderColor: '#303030',
                borderRadius: 8,
                cursor: 'pointer',
                transition: 'border-color 0.2s',
              }}
              styles={{ body: { padding: 12 } }}
              onClick={toggleExpand}
              hoverable
            >
              {/* 헤더 */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8, gap: 8 }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                    <Text type="secondary" style={{ fontSize: 11 }}>
                      {insight.source || '알 수 없음'}
                    </Text>
                    <Text type="secondary" style={{ fontSize: 11 }}>•</Text>
                    <Text type="secondary" style={{ fontSize: 11 }}>
                      {dayjs(insight.created_at).fromNow()}
                    </Text>
                  </div>
                  <Paragraph
                    style={{
                      color: '#e0e0e0',
                      fontSize: 14,
                      fontWeight: 500,
                      margin: 0,
                      display: '-webkit-box',
                      WebkitLineClamp: 2,
                      WebkitBoxOrient: 'vertical',
                      overflow: 'hidden',
                      lineHeight: 1.4,
                    }}
                  >
                    {insight.title}
                  </Paragraph>
                </div>
                <Tag
                  color={DECISION_COLORS[insight.decision] || '#8c8c8c'}
                  style={{ margin: 0, fontWeight: 600, border: 'none' }}
                  icon={insight.decision === 'PENDING' ? <Spin size="small" style={{ marginRight: 4 }} /> : DECISION_ICONS[insight.decision]}
                >
                  {DECISION_LABELS[insight.decision] || insight.decision}
                </Tag>
              </div>

              {insight.decision !== 'PENDING' && (
                <>
                  {/* 감성 바 */}
                  <div style={{ marginBottom: 12 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                      <Text style={{ fontSize: 11, color: COLOR_BEARISH }}>약세</Text>
                      <Text style={{ fontSize: 11, color: insight.sentiment_label === 'bullish' ? COLOR_BULLISH : insight.sentiment_label === 'bearish' ? COLOR_BEARISH : COLOR_NEUTRAL }}>
                        {insight.sentiment_label === 'bullish' ? '강세' : insight.sentiment_label === 'bearish' ? '약세' : '중립'} ({score.toFixed(2)})
                      </Text>

                      <Text style={{ fontSize: 11, color: '#1890ff' }}>강세</Text>
                    </div>
                    <div style={{ height: 6, background: '#303030', borderRadius: 3, position: 'relative', overflow: 'hidden' }}>
                      {/* 중앙선 */}
                      <div style={{ position: 'absolute', left: '50%', top: 0, bottom: 0, width: 1, background: '#555', zIndex: 1 }} />
                      {/* 채워지는 바 */}
                      <div
                        style={{
                          position: 'absolute',
                          top: 0,
                          bottom: 0,
                          left: barLeft,
                          width: barWidth,
                          background: barColor,
                          borderRadius: 3,
                          transition: 'all 0.3s ease',
                        }}
                      />
                    </div>
                  </div>

                  {/* 키워드 칩 */}
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginBottom: isExpanded ? 12 : 0 }}>
                    {insight.keywords.slice(0, 5).map((kw, idx) => (
                      <Tag key={idx} style={{ background: '#1f1f1f', borderColor: '#303030', color: '#aaa', margin: 0, fontSize: 11 }}>
                        {kw}
                      </Tag>
                    ))}
                  </div>
                </>
              )}

              {/* 상세 (Collapse) — 애니메이션 */}
              <div
                style={{
                  display: 'grid',
                  gridTemplateRows: isExpanded ? '1fr' : '0fr',
                  transition: 'grid-template-rows 0.3s ease',
                }}
              >
                <div style={{ overflow: 'hidden' }}>
                  <div
                    style={{
                      marginTop: 12,
                      paddingTop: 12,
                      borderTop: '1px solid #303030',
                      opacity: isExpanded ? 1 : 0,
                      transition: 'opacity 0.25s ease',
                    }}
                    onClick={(e) => e.stopPropagation()}
                  >
                    {/* AI 추론 과정 */}
                    {insight.reasoning_chain && (
                      <div style={{ marginBottom: 12 }}>
                        <Text type="secondary" style={{ fontSize: 11, display: 'block', marginBottom: 4 }}>AI 추론 과정</Text>
                        <div style={{ background: '#1a1a1a', padding: 8, borderRadius: 6, fontSize: 12, color: '#ccc', lineHeight: 1.5 }}>
                          {insight.reasoning_chain}
                        </div>
                      </div>
                    )}

                    {/* 긍정/부정 요인 2분할 */}
                    <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
                      <div style={{ flex: 1, background: 'rgba(82, 196, 26, 0.1)', padding: 8, borderRadius: 6, border: '1px solid rgba(82, 196, 26, 0.2)' }}>
                        <Text style={{ color: COLOR_BULLISH, fontSize: 11, fontWeight: 600, display: 'block', marginBottom: 4 }}>긍정 요인</Text>
                        <ul style={{ margin: 0, paddingLeft: 16, color: '#e0e0e0', fontSize: 11 }}>
                          {insight.positive_factors.length > 0 ? (
                            insight.positive_factors.map((f, i) => <li key={i}>{f}</li>)
                          ) : (
                            <li style={{ color: '#666', listStyle: 'none', marginLeft: -16 }}>없음</li>
                          )}
                        </ul>
                      </div>
                      <div style={{ flex: 1, background: 'rgba(255, 77, 79, 0.1)', padding: 8, borderRadius: 6, border: '1px solid rgba(255, 77, 79, 0.2)' }}>
                        <Text style={{ color: COLOR_BEARISH, fontSize: 11, fontWeight: 600, display: 'block', marginBottom: 4 }}>부정 요인</Text>
                        <ul style={{ margin: 0, paddingLeft: 16, color: '#e0e0e0', fontSize: 11 }}>
                          {insight.negative_factors.length > 0 ? (
                            insight.negative_factors.map((f, i) => <li key={i}>{f}</li>)
                          ) : (
                            <li style={{ color: '#666', listStyle: 'none', marginLeft: -16 }}>없음</li>
                          )}
                        </ul>
                      </div>
                    </div>

                    {/* 신뢰도 + 검증 결과 */}
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12, background: '#1a1a1a', padding: '8px 12px', borderRadius: 6 }}>
                      <div>
                        <Text type="secondary" style={{ fontSize: 11, marginRight: 8 }}>신뢰도</Text>
                        <Text style={{ color: '#e0e0e0', fontSize: 12, fontWeight: 600 }}>{insight.confidence}%</Text>
                      </div>
                      {insight.verification_result && (
                        <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                          <Text type="secondary" style={{ fontSize: 11 }}>검증:</Text>
                          {insight.verification_result === 'correct' ? (
                            <Tag icon={<CheckCircleOutlined />} color="success" style={{ margin: 0, border: 'none' }}>적중</Tag>
                          ) : (
                            <Tag icon={<CloseCircleOutlined />} color="error" style={{ margin: 0, border: 'none' }}>실패</Tag>
                          )}
                          {insight.actual_price_change !== null && (
                            <Text style={{ fontSize: 11, color: insight.actual_price_change > 0 ? COLOR_BULLISH : COLOR_BEARISH }}>
                              ({insight.actual_price_change > 0 ? '+' : ''}{insight.actual_price_change.toFixed(2)}%)
                            </Text>
                          )}
                        </div>
                      )}
                    </div>

                    {/* 카드 하단: 코인 태그 + 원문 링크 */}
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <Space size={4}>
                        {insight.currencies.map((c) => (
                          <Tag key={c} color="blue" style={{ margin: 0, border: 'none' }}>{c}</Tag>
                        ))}
                      </Space>
                      {insight.url && (
                        <a href={insight.url} target="_blank" rel="noreferrer" style={{ fontSize: 12, color: '#1890ff', display: 'flex', alignItems: 'center', gap: 4 }}>
                          원문 보기 <LinkOutlined />
                        </a>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
