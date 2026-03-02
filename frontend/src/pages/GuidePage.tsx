import { useState, useMemo } from 'react';
import { Typography, Flex, Collapse, Table, Alert, Card, Row, Col, InputNumber, Select, Divider, Tag, Input, Empty } from 'antd';
import { BookOutlined, SearchOutlined } from '@ant-design/icons';
import { GUIDE_SECTIONS, GUIDE_GLOSSARY } from '../lib/guideContent';
import { GUIDE_DIAGRAMS } from '../lib/guideDiagrams';
import MermaidDiagram from '../components/MermaidDiagram';

const { Title, Text, Paragraph } = Typography;

export default function GuidePage() {
  // ── 용어 사전 검색 상태 ─────────────────────────────────────────────
  const [glossaryQuery, setGlossaryQuery] = useState('');

  const filteredGlossary = useMemo(() => {
    const q = glossaryQuery.trim().toLowerCase();
    if (!q) {
      return GUIDE_GLOSSARY;
    }
    return GUIDE_GLOSSARY.filter((item) =>
      item.term.toLowerCase().includes(q) ||
      item.simple.toLowerCase().includes(q) ||
      item.detail.toLowerCase().includes(q),
    );
  }, [glossaryQuery]);

  // ── 스코어 시뮬레이터 상태 ─────────────────────────────────────────
  const [simInputs, setSimInputs] = useState({
    volRatio: 1.2,
    maTrend: 'up' as 'up' | 'down' | 'insufficient',
    adx: 18,
    bbStatus: 'recovered' as 'recovered' | 'below' | 'none',
    rsiSlope: 2.1,
    rsiLevel: 28,
    entryThreshold: 70,
    regime: 'ranging' as 'ranging' | 'trending' | 'volatile',
  });

  // ── 스코어 계산 (engine.py 139-181 라인과 동일) ──────────────────────
  const scores = useMemo(() => {
    // engine.py line 145
    const volScore = Math.max(0, Math.min(100, ((3.0 - simInputs.volRatio) / 2.0) * 100));
    // engine.py line 149
    const maScore = simInputs.maTrend === 'up' ? 100 : simInputs.maTrend === 'down' ? 0 : 50;
    // engine.py line 153
    const adxScore = Math.max(0, Math.min(100, ((40 - simInputs.adx) / 25) * 100));
    // engine.py line 157
    const bbScore = simInputs.bbStatus === 'recovered' ? 100 : simInputs.bbStatus === 'below' ? 30 : 0;
    // engine.py line 165
    const slopeScore = Math.max(0, Math.min(100, (simInputs.rsiSlope / 3.0) * 100));
    // engine.py line 173
    const rsiScore = Math.max(0, Math.min(100, ((45 - simInputs.rsiLevel) / 25) * 100));

    return [
      { label: '변동성', score: volScore },
      { label: 'MA 추세', score: maScore },
      { label: 'ADX', score: adxScore },
      { label: 'BB 복귀', score: bbScore },
      { label: 'RSI 기울기', score: slopeScore },
      { label: 'RSI 레벨', score: rsiScore },
    ];
  }, [simInputs]);

  const totalScore = useMemo(() => {
    return scores.reduce((a, b) => a + b.score, 0) / 6;
  }, [scores]);

  const regimeOffset = useMemo(() => {
    // engine.py line 114
    return simInputs.regime === 'trending' ? 15 : simInputs.regime === 'volatile' ? 25 : 0;
  }, [simInputs.regime]);

  const effectiveThreshold = useMemo(() => {
    return Math.min(simInputs.entryThreshold + regimeOffset, 99);
  }, [simInputs.entryThreshold, regimeOffset]);

  const isBuy = totalScore >= effectiveThreshold;

  // ── Collapse 아이템 렌더링 ─────────────────────────────────────────
  const collapseItems = GUIDE_SECTIONS.map((section) => {
    return {
      key: section.key,
      label: <Text strong>{section.title}</Text>,
      children: (
        <Flex vertical gap={16}>
          {/* 1. Paragraphs */}
          {section.content.paragraphs.map((p, idx) => (
            <Paragraph key={idx} style={{ margin: 0 }}>
              {p}
            </Paragraph>
          ))}

          {/* 2. Diagrams (섹션별 Mermaid 다이어그램) */}
          {GUIDE_DIAGRAMS[section.key]?.map((diagram, idx) => (
            <Card
              key={`diagram-${idx}`}
              size="small"
              title={diagram.title}
              style={{ marginTop: idx === 0 ? 8 : 0 }}
            >
              <MermaidDiagram chart={diagram.chart} />
            </Card>
          ))}

          {/* 3. Tables */}
          {section.content.tables?.map((table, idx) => (
            <div key={idx}>
              {table.title && (
                <Text strong style={{ display: 'block', marginBottom: 8 }}>
                  {table.title}
                </Text>
              )}
              <Table
                dataSource={table.data}
                columns={table.columns}
                pagination={false}
                size="small"
                bordered
              />
            </div>
          ))}

          {/* 4. Highlights */}
          {section.content.highlights?.map((highlight, idx) => (
            <Alert key={idx} type="info" showIcon title={highlight} />
          ))}

          {/* 5. Formulas */}
          {section.content.formulas && section.content.formulas.length > 0 && (
            <pre style={{ background: '#1a1a1a', padding: 12, borderRadius: 6, overflow: 'auto', margin: 0 }}>
              <code>{section.content.formulas.join(String.fromCharCode(10))}</code>
            </pre>
          )}

          {/* 5. 스코어 시뮬레이터 (entry 섹션에만 추가) */}
          {section.key === 'entry' && (
            <>
              <Divider>스코어 시뮬레이터</Divider>
              <Card size="small" title="매수 스코어 시뮬레이터" style={{ marginTop: 16 }}>
                <Row gutter={[16, 16]}>
                  {/* Row 1 */}
                  <Col span={12}>
                    <Flex vertical gap={4}>
                      <Text>변동성 비율</Text>
                      <InputNumber
                        min={0}
                        max={5}
                        step={0.1}
                        value={simInputs.volRatio}
                        onChange={(val) => setSimInputs((prev) => ({ ...prev, volRatio: val ?? 0 }))}
                        style={{ width: '100%' }}
                      />
                    </Flex>
                  </Col>
                  <Col span={12}>
                    <Flex vertical gap={4}>
                      <Text>MA 추세</Text>
                      <Select
                        value={simInputs.maTrend}
                        onChange={(val) => setSimInputs((prev) => ({ ...prev, maTrend: val }))}
                        options={[
                          { label: '상승', value: 'up' },
                          { label: '하락', value: 'down' },
                          { label: '데이터부족', value: 'insufficient' },
                        ]}
                        style={{ width: '100%' }}
                      />
                    </Flex>
                  </Col>

                  {/* Row 2 */}
                  <Col span={12}>
                    <Flex vertical gap={4}>
                      <Text>ADX</Text>
                      <InputNumber
                        min={0}
                        max={100}
                        step={1}
                        value={simInputs.adx}
                        onChange={(val) => setSimInputs((prev) => ({ ...prev, adx: val ?? 0 }))}
                        style={{ width: '100%' }}
                      />
                    </Flex>
                  </Col>
                  <Col span={12}>
                    <Flex vertical gap={4}>
                      <Text>BB 상태</Text>
                      <Select
                        value={simInputs.bbStatus}
                        onChange={(val) => setSimInputs((prev) => ({ ...prev, bbStatus: val }))}
                        options={[
                          { label: '하단이탈후복귀', value: 'recovered' },
                          { label: '하단이탈중', value: 'below' },
                          { label: '해당없음', value: 'none' },
                        ]}
                        style={{ width: '100%' }}
                      />
                    </Flex>
                  </Col>

                  {/* Row 3 */}
                  <Col span={12}>
                    <Flex vertical gap={4}>
                      <Text>RSI 기울기</Text>
                      <InputNumber
                        min={-5}
                        max={10}
                        step={0.1}
                        value={simInputs.rsiSlope}
                        onChange={(val) => setSimInputs((prev) => ({ ...prev, rsiSlope: val ?? 0 }))}
                        style={{ width: '100%' }}
                      />
                    </Flex>
                  </Col>
                  <Col span={12}>
                    <Flex vertical gap={4}>
                      <Text>RSI 레벨</Text>
                      <InputNumber
                        min={0}
                        max={100}
                        step={1}
                        value={simInputs.rsiLevel}
                        onChange={(val) => setSimInputs((prev) => ({ ...prev, rsiLevel: val ?? 0 }))}
                        style={{ width: '100%' }}
                      />
                    </Flex>
                  </Col>
                </Row>

                <Divider style={{ margin: '16px 0' }} />

                <Row gutter={[16, 16]}>
                  {/* Row 4 */}
                  <Col span={12}>
                    <Flex vertical gap={4}>
                      <Text>진입 임계치</Text>
                      <InputNumber
                        min={0}
                        max={100}
                        step={1}
                        value={simInputs.entryThreshold}
                        onChange={(val) => setSimInputs((prev) => ({ ...prev, entryThreshold: val ?? 0 }))}
                        style={{ width: '100%' }}
                      />
                    </Flex>
                  </Col>
                  <Col span={12}>
                    <Flex vertical gap={4}>
                      <Text>시장 레짐</Text>
                      <Select
                        value={simInputs.regime}
                        onChange={(val) => setSimInputs((prev) => ({ ...prev, regime: val }))}
                        options={[
                          { label: '횡보', value: 'ranging' },
                          { label: '추세장', value: 'trending' },
                          { label: '변동성폭발', value: 'volatile' },
                        ]}
                        style={{ width: '100%' }}
                      />
                    </Flex>
                  </Col>
                </Row>

                <Divider style={{ margin: '16px 0' }} />

                {/* Results */}
                <Flex vertical gap={16}>
                  <Flex wrap="wrap" gap={8}>
                    {scores.map((s, idx) => {
                      const color = s.score >= 70 ? '#52c41a' : s.score >= 40 ? '#faad14' : '#ff4d4f';
                      return (
                        <Tag key={idx} color={color}>
                          {s.label}: {s.score.toFixed(1)}
                        </Tag>
                      );
                    })}
                  </Flex>

                  <Flex align="center" justify="space-between" style={{ background: '#1a1a1a', padding: 16, borderRadius: 8 }}>
                    <Flex vertical gap={4}>
                      <Text type="secondary">
                        기본 {simInputs.entryThreshold} + 레짐 +{regimeOffset} = {effectiveThreshold}
                      </Text>
                      <Text style={{ fontSize: 32, fontWeight: 700 }}>
                        {totalScore.toFixed(1)} 점
                      </Text>
                    </Flex>
                    <Tag color={isBuy ? '#52c41a' : '#ff4d4f'} style={{ fontSize: 24, padding: '8px 16px', lineHeight: '32px' }}>
                      {isBuy ? 'BUY' : 'HOLD'}
                    </Tag>
                  </Flex>
                </Flex>
              </Card>
            </>
          )}
        </Flex>
      ),
    };
  });

  return (
    <div style={{ padding: 24, maxWidth: 1280, margin: '0 auto' }}>
      <Flex align="center" gap={8} style={{ marginBottom: 16 }}>
        <BookOutlined />
        <Title level={4} style={{ margin: 0 }}>사용법 가이드</Title>
      </Flex>

      <Row gutter={[16, 16]} align="top">
        <Col xs={24} lg={16}>
          <Alert
            type="success"
            showIcon
            style={{ marginBottom: 16 }}
            title="처음 보시는 분은 오른쪽 용어 사전부터 읽고, 이후에 각 전략 섹션을 보시면 훨씬 이해가 쉽습니다."
          />
          <Collapse defaultActiveKey={['overview']} items={collapseItems} />
        </Col>

        <Col xs={24} lg={8}>
          <div style={{ position: 'sticky', top: 24 }}>
            <Card
              size="small"
              title="용어 사전 (쉽게 보기)"
              extra={
                <Input
                  allowClear
                  placeholder="용어 검색 (예: RSI, ATR, 레짐)"
                  prefix={<SearchOutlined />}
                  value={glossaryQuery}
                  onChange={(e) => setGlossaryQuery(e.target.value)}
                  style={{ width: 240 }}
                />
              }
            >
              {filteredGlossary.length === 0 ? (
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description="검색 결과가 없습니다. 다른 키워드로 검색해보세요."
                />
              ) : (
                <div style={{ maxHeight: '70vh', overflowY: 'auto', paddingRight: 4 }}>
                  <Flex vertical gap={10}>
                    {filteredGlossary.map((item) => (
                      <div key={item.term} style={{ padding: 12, border: '1px solid #303030', borderRadius: 8 }}>
                        <Flex align="center" gap={8} style={{ marginBottom: 4 }}>
                          <Tag color="processing">{item.term}</Tag>
                          <Text>{item.simple}</Text>
                        </Flex>
                        <Text type="secondary">{item.detail}</Text>
                      </div>
                    ))}
                  </Flex>
                </div>
              )}
            </Card>
          </div>
        </Col>
      </Row>
    </div>
  );
}
