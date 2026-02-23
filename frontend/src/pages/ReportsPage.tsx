import { useState } from 'react';
import { Row, Col, Card, List, Tag, Typography, Spin, Empty, Flex } from 'antd';
import { FileTextOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import Markdown from 'react-markdown';
import { useDailyReports, useDailyReport } from '../hooks/useSupabase';
import type { DailyReport } from '../types/database';

const { Title, Text } = Typography;

/* ── 색상 상수 (한국 주식시장 컨벤션) ───────────────────── */
const COLOR_RISE = '#ff4d4f';   // 상승 · 플러스 = 빨강
const COLOR_FALL = '#1890ff';   // 하락 · 마이너스 = 파랑
const COLOR_EVEN = '#999';      // 보합 · 중립 = 회색

function pnlColor(v: number) {
  if (v > 0) return COLOR_RISE;
  if (v < 0) return COLOR_FALL;
  return COLOR_EVEN;
}

function formatKRW(v: number) {
  const abs = Math.abs(v);
  if (abs >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
  if (abs >= 1_000) return `${(v / 1_000).toFixed(0)}K`;
  return v.toFixed(0);
}

export default function ReportsPage() {
  const { reports, loading: listLoading } = useDailyReports(60);
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const { report, loading: detailLoading } = useDailyReport(selectedDate);

  return (
    <div>
      <Flex align="center" gap={8} style={{ marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}>Reports</Title>
      </Flex>

      <Row gutter={16}>
        {/* ── 좌측: 리포트 목록 ─────────────────────────── */}
        <Col xs={24} md={8} lg={6}>
          <Card
            size="small"
            title={<Text style={{ fontSize: 13 }}>리포트 목록</Text>}
            styles={{
              header: { background: '#1a1a1a', borderBottom: '1px solid #303030', minHeight: 40 },
              body: { padding: 0, maxHeight: 'calc(100vh - 200px)', overflowY: 'auto' },
            }}
          >
            {listLoading ? (
              <div style={{ textAlign: 'center', padding: 40 }}>
                <Spin size="small" />
              </div>
            ) : reports.length === 0 ? (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description={<Text type="secondary">리포트가 없습니다</Text>}
                style={{ padding: 40 }}
              />
            ) : (
              <List
                dataSource={reports}
                renderItem={(item: DailyReport) => {
                  const isSelected = selectedDate === item.report_date;
                  const winRate = item.trade_count > 0
                    ? ((item.win_count / item.trade_count) * 100).toFixed(0)
                    : '-';

                  return (
                    <List.Item
                      onClick={() => setSelectedDate(item.report_date)}
                      style={{
                        padding: '10px 12px',
                        cursor: 'pointer',
                        background: isSelected ? 'rgba(22, 104, 220, 0.12)' : 'transparent',
                        borderLeft: isSelected ? '3px solid #1668dc' : '3px solid transparent',
                        borderBottom: '1px solid #1f1f1f',
                        transition: 'background 0.15s',
                      }}
                      onMouseEnter={(e) => {
                        if (!isSelected) e.currentTarget.style.background = '#1a1a1a';
                      }}
                      onMouseLeave={(e) => {
                        if (!isSelected) e.currentTarget.style.background = 'transparent';
                      }}
                    >
                      <div style={{ width: '100%' }}>
                        <Flex justify="space-between" align="center">
                          <Text strong style={{ fontSize: 13 }}>
                            {dayjs(item.report_date).format('YYYY.MM.DD')}
                          </Text>
                          <Text style={{ color: pnlColor(item.net_profit), fontSize: 12, fontWeight: 600 }}>
                            {item.net_profit >= 0 ? '+' : ''}{formatKRW(item.net_profit)}
                          </Text>
                        </Flex>
                        <Flex gap={4} style={{ marginTop: 4 }}>
                          <Tag
                            color="green"
                            style={{ fontSize: 10, lineHeight: '16px', margin: 0 }}
                          >
                            {item.win_count}W
                          </Tag>
                          <Tag
                            color="red"
                            style={{ fontSize: 10, lineHeight: '16px', margin: 0 }}
                          >
                            {item.loss_count}L
                          </Tag>
                          <Text type="secondary" style={{ fontSize: 10, marginLeft: 'auto' }}>
                            승률 {winRate}% · {item.trade_count}건
                          </Text>
                        </Flex>
                      </div>
                    </List.Item>
                  );
                }}
              />
            )}
          </Card>
        </Col>

        {/* ── 우측: 리포트 상세 (마크다운) ──────────────── */}
        <Col xs={24} md={16} lg={18}>
          <Card
            size="small"
            title={
              selectedDate ? (
                <Text style={{ fontSize: 13 }}>
                  {dayjs(selectedDate).format('YYYY년 M월 D일')} 분석 리포트
                </Text>
              ) : (
                <Text style={{ fontSize: 13 }}>리포트 상세</Text>
              )
            }
            styles={{
              header: { background: '#1a1a1a', borderBottom: '1px solid #303030', minHeight: 40 },
              body: { maxHeight: 'calc(100vh - 200px)', overflowY: 'auto' },
            }}
          >
            {!selectedDate ? (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description={
                  <Text type="secondary">
                    좌측 목록에서 리포트를 선택하세요
                  </Text>
                }
                style={{ padding: 60 }}
              />
            ) : detailLoading ? (
              <div style={{ textAlign: 'center', padding: 60 }}>
                <Spin size="default" />
                <div style={{ marginTop: 8 }}>
                  <Text type="secondary" style={{ fontSize: 12 }}>리포트 불러오는 중...</Text>
                </div>
              </div>
            ) : !report ? (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description={<Text type="secondary">리포트를 찾을 수 없습니다</Text>}
                style={{ padding: 60 }}
              />
            ) : (
              <div className="report-markdown">
                <Markdown>{report.content}</Markdown>
              </div>
            )}
          </Card>
        </Col>
      </Row>

      {/* ── 마크다운 스타일 ─────────────────────────────── */}
      <style>{`
        .report-markdown {
          color: #d0d0d0;
          line-height: 1.7;
          font-size: 13px;
        }
        .report-markdown h1 {
          font-size: 20px;
          color: #fff;
          border-bottom: 1px solid #303030;
          padding-bottom: 8px;
          margin-top: 0;
        }
        .report-markdown h2 {
          font-size: 16px;
          color: #e0e0e0;
          margin-top: 24px;
          margin-bottom: 12px;
        }
        .report-markdown h3 {
          font-size: 14px;
          color: #ccc;
          margin-top: 16px;
          margin-bottom: 8px;
        }
        .report-markdown table {
          width: 100%;
          border-collapse: collapse;
          margin: 12px 0;
          font-size: 12px;
        }
        .report-markdown th {
          background: #1a1a1a;
          color: #aaa;
          text-align: left;
          padding: 8px 10px;
          border-bottom: 1px solid #303030;
          font-weight: 600;
        }
        .report-markdown td {
          padding: 6px 10px;
          border-bottom: 1px solid #1f1f1f;
          color: #bbb;
        }
        .report-markdown tr:hover td {
          background: rgba(22, 104, 220, 0.04);
        }
        .report-markdown ul, .report-markdown ol {
          padding-left: 20px;
          margin: 8px 0;
        }
        .report-markdown li {
          margin: 4px 0;
          color: #bbb;
        }
        .report-markdown strong {
          color: #fff;
        }
        .report-markdown code {
          background: #1a1a1a;
          padding: 2px 6px;
          border-radius: 3px;
          font-size: 12px;
          color: #e0e0e0;
        }
        .report-markdown blockquote {
          border-left: 3px solid #1668dc;
          margin: 12px 0;
          padding: 8px 12px;
          background: rgba(22, 104, 220, 0.06);
          color: #aaa;
        }
        .report-markdown hr {
          border: none;
          border-top: 1px solid #303030;
          margin: 16px 0;
        }
        .report-markdown p {
          margin: 8px 0;
        }
      `}</style>
    </div>
  );
}
