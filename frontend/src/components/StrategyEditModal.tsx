import { useEffect, useMemo } from 'react';
import {
  Modal,
  Form,
  InputNumber,
  Button,
  Typography,
  Space,
  Alert,
  Divider,
  Row,
  Col,
  message,
  Slider,
} from 'antd';
import { EditOutlined, UndoOutlined, CheckOutlined } from '@ant-design/icons';
import { DEFAULT_STRATEGY as SHARED_DEFAULT, PRESETS, getActivePresetName } from '../lib/strategyParams';
const { Title, Text } = Typography;

const EXAMPLE_SCORES: Record<string, { label: string; score: number; field: string }> = {
  volatility: { label: '변동성', score: 90, field: 'w_volatility' },
  ma_trend:   { label: '이평선 추세', score: 100, field: 'w_ma_trend' },
  adx:        { label: 'ADX 횡보', score: 88, field: 'w_adx' },
  bb_recovery:{ label: 'BB 복귀', score: 100, field: 'w_bb_recovery' },
  rsi_slope:  { label: 'RSI 기울기', score: 70, field: 'w_rsi_slope' },
  rsi_level:  { label: 'RSI 레벨', score: 68, field: 'w_rsi_level' },
};

const EXAMPLE_EXIT_SCORES: Record<string, { label: string; score: number; field: string }> = {
  rsi_level:   { label: 'RSI 과매수', score: 83, field: 'w_exit_rsi_level' },
  bb_position: { label: 'BB 위치', score: 75, field: 'w_exit_bb_position' },
  profit_pct:  { label: '수익률', score: 67, field: 'w_exit_profit_pct' },
  adx_trend:   { label: 'ADX 추세', score: 55, field: 'w_exit_adx_trend' },
};

export interface StrategyParams {
  bb_period: number;
  bb_std_dev: number;
  rsi_period: number;
  rsi_oversold: number;
  atr_period: number;
  atr_stop_multiplier: number;
  top_volume_count?: number;
  w_volatility?: number;
  w_ma_trend?: number;
  w_adx?: number;
  w_bb_recovery?: number;
  w_rsi_slope?: number;
  w_rsi_level?: number;
  entry_score_threshold?: number;
  // 매도 청산
  w_exit_rsi_level?: number;
  w_exit_bb_position?: number;
  w_exit_profit_pct?: number;
  w_exit_adx_trend?: number;
  exit_score_threshold?: number;
  trailing_stop_atr_multiplier?: number;
  take_profit_sell_ratio?: number;
  min_profit_margin?: number;
  // 시장 레짐 설정
  regime_adx_trending_threshold?: number;
  regime_vol_overload_ratio?: number;
  regime_trending_offset?: number;
  regime_volatile_offset?: number;
}


interface Props {
  open: boolean;
  onClose: () => void;
  currentParams: StrategyParams;
  onApply: (params: StrategyParams) => void;
}

export default function StrategyEditModal({
  open,
  onClose,
  currentParams,
  onApply,
}: Props) {
  const [form] = Form.useForm<StrategyParams>();
  const [messageApi, contextHolder] = message.useMessage();

  const currentFormValues = Form.useWatch([], form);
  const activePreset = useMemo(
    () => currentFormValues ? getActivePresetName({ ...currentParams, ...currentFormValues } as StrategyParams) : null,
    [currentFormValues, currentParams],
  );

  const simulationResult = useMemo(() => {
    const values = currentFormValues || currentParams;
    if (!values) return { totalScore: 0, details: [] };
    
    let totalWeight = 0;
    let weightedScoreSum = 0;
    const details: { label: string; weight: number; score: number; weighted: number }[] = [];

    Object.values(EXAMPLE_SCORES).forEach(({ label, score, field }) => {
      const weight = Number((values as StrategyParams)[field as keyof StrategyParams]) || 0;
      const weighted = weight * score;
      totalWeight += weight;
      weightedScoreSum += weighted;
      details.push({ label, weight, score, weighted });
    });

    const totalScore = totalWeight > 0 ? weightedScoreSum / totalWeight : 0;
    return { totalScore, details };
  }, [currentFormValues, currentParams]);

  const threshold = (currentFormValues || currentParams)?.entry_score_threshold || 0;
  const isPass = simulationResult.totalScore >= threshold;

  const exitSimulationResult = useMemo(() => {
    const values = currentFormValues || currentParams;
    if (!values) return { totalScore: 0, details: [] };

    let totalWeight = 0;
    let weightedScoreSum = 0;
    const details: { label: string; weight: number; score: number; weighted: number }[] = [];

    Object.values(EXAMPLE_EXIT_SCORES).forEach(({ label, score, field }) => {
      const weight = Number((values as StrategyParams)[field as keyof StrategyParams]) || 0;
      const weighted = weight * score;
      totalWeight += weight;
      weightedScoreSum += weighted;
      details.push({ label, weight, score, weighted });
    });

    const totalScore = totalWeight > 0 ? weightedScoreSum / totalWeight : 0;
    return { totalScore, details };
  }, [currentFormValues, currentParams]);

  const exitThreshold = (currentFormValues || currentParams)?.exit_score_threshold || 0;
  const isExitPass = exitSimulationResult.totalScore >= exitThreshold;

  useEffect(() => {
    if (open) {
      form.setFieldsValue(currentParams);
    }
  }, [open, currentParams, form]);

  const handleApply = () => {
    const values = form.getFieldsValue();
    // top_volume_count는 모달 폼에 없으므로 currentParams에서 보존
    onApply({ ...currentParams, ...values });
    onClose();
  };

  return (
    <Modal
      open={open}
      onCancel={onClose}
      title={
        <Space>
          <EditOutlined style={{ color: '#1668dc', fontSize: 18 }} />
          <Title level={5} style={{ margin: 0 }}>
            전략 파라미터 실시간 수정
          </Title>
        </Space>
      }
      footer={
        <Space style={{ width: '100%', justifyContent: 'flex-end' }}>
          <Button onClick={onClose}>취소</Button>
          <Button type="primary" onClick={handleApply}>
            적용
          </Button>
        </Space>
      }
      width={600}
      destroyOnHidden
    >
      {contextHolder}
      <Alert
        title="변경 사항은 Supabase에 저장되며, 약 1분 내 봇에 자동 적용됩니다"
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
      />

      <Form form={form} layout="vertical" size="middle">
        <Divider titlePlacement="left" plain>
          볼린저 밴드
        </Divider>
        <Row gutter={16}>
          <Col span={12}>
            <Form.Item label="이동평균 기간" name="bb_period">
              <InputNumber min={5} max={100} style={{ width: '100%' }} />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item label="표준편차 배수 (σ)" name="bb_std_dev">
              <InputNumber min={0.5} max={5} step={0.1} style={{ width: '100%' }} />
            </Form.Item>
          </Col>
        </Row>

        <Divider titlePlacement="left" plain>
          RSI
        </Divider>
        <Row gutter={16}>
          <Col span={12}>
            <Form.Item label="RSI 기간" name="rsi_period">
              <InputNumber min={5} max={50} style={{ width: '100%' }} />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item label="과매도 기준" name="rsi_oversold">
              <InputNumber min={10} max={50} style={{ width: '100%' }} />
            </Form.Item>
          </Col>
        </Row>

        <Divider titlePlacement="left" plain>
          ATR 손절
        </Divider>
        <Row gutter={16}>
          <Col span={12}>
            <Form.Item label="ATR 기간" name="atr_period">
              <InputNumber min={5} max={50} style={{ width: '100%' }} />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item label="손절 계수" name="atr_stop_multiplier">
              <InputNumber min={1} max={5} step={0.1} style={{ width: '100%' }} />
            </Form.Item>
          </Col>
        </Row>

        <Divider titlePlacement="left" plain>
          프리셋
        </Divider>
        <Button
          icon={activePreset === '기본값' ? <CheckOutlined /> : <UndoOutlined />}
          type={activePreset === '기본값' ? 'primary' : 'default'}
          ghost={activePreset === '기본값'}
          onClick={() => {
            form.setFieldsValue(SHARED_DEFAULT);
            messageApi.info('기본값으로 복원되었습니다. 적용 버튼을 눌러 적용하세요.');
          }}
          block
        >
          기본값 복원
        </Button>
        <Row gutter={[8, 8]} style={{ marginTop: 8 }}>
          {PRESETS.map((preset) => (
            <Col span={12} key={preset.name}>
              <Button
                block
                type={activePreset === preset.name ? 'primary' : 'default'}
                ghost={activePreset === preset.name}
                icon={activePreset === preset.name ? <CheckOutlined style={{ fontSize: 12 }} /> : undefined}
                onClick={() => {
                  form.setFieldsValue(preset.params);
                  messageApi.info(`'${preset.name}' 프리셋이 적용되었습니다. 적용 버튼을 눌러 적용하세요.`);
                }}
              >
                <div style={{ lineHeight: 1.3 }}>
                  <div>{preset.name}</div>
                  <div style={{ fontSize: 11, opacity: 0.65 }}>{preset.description}</div>
                </div>
              </Button>
            </Col>
          ))}
        </Row>

        <Divider titlePlacement="left" plain>
          매수 진입 조건 (스코어링)
        </Divider>
        <Alert
          description="각 조건이 맞을 때마다 점수를 부여합니다. 총점이 '진입 스코어 임계값'을 넘으면 봇이 매수를 실행합니다. 중요하게 생각하는 조건의 점수를 높여보세요."
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
        />
        <Row gutter={16}>
          <Col span={12}>
            <Form.Item label="변동성 (Volatility)" name="w_volatility" style={{ marginBottom: 8 }}>
              <Slider min={0} max={3} step={0.1} />
            </Form.Item>
            <Text style={{ fontSize: 12, opacity: 0.65, marginTop: -8, marginBottom: 8, display: 'block' }}>
              시장이 안정적일수록 높은 점수. 급등락이 심하면 매수를 자제합니다.
            </Text>
          </Col>
          <Col span={12}>
            <Form.Item label="이평선 추세 (MA Trend)" name="w_ma_trend" style={{ marginBottom: 8 }}>
              <Slider min={0} max={3} step={0.1} />
            </Form.Item>
            <Text style={{ fontSize: 12, opacity: 0.65, marginTop: -8, marginBottom: 8, display: 'block' }}>
              20일선이 50일선 위에 있으면 상승 추세로 판단하여 높은 점수를 줍니다.
            </Text>
          </Col>
        </Row>
        <Row gutter={16}>
          <Col span={12}>
            <Form.Item label="ADX 추세 강도" name="w_adx" style={{ marginBottom: 8 }}>
              <Slider min={0} max={3} step={0.1} />
            </Form.Item>
            <Text style={{ fontSize: 12, opacity: 0.65, marginTop: -8, marginBottom: 8, display: 'block' }}>
              ADX가 낮을수록(횡보장) 평균 회귀 전략에 유리하여 높은 점수를 줍니다.
            </Text>
          </Col>
          <Col span={12}>
            <Form.Item label="볼린저 밴드 회복" name="w_bb_recovery" style={{ marginBottom: 8 }}>
              <Slider min={0} max={3} step={0.1} />
            </Form.Item>
            <Text style={{ fontSize: 12, opacity: 0.65, marginTop: -8, marginBottom: 8, display: 'block' }}>
              가격이 하단밴드 아래로 떨어졌다가 다시 올라오면 반등 신호로 높은 점수를 줍니다.
            </Text>
          </Col>
        </Row>
        <Row gutter={16}>
          <Col span={12}>
            <Form.Item label="RSI 기울기" name="w_rsi_slope" style={{ marginBottom: 8 }}>
              <Slider min={0} max={3} step={0.1} />
            </Form.Item>
            <Text style={{ fontSize: 12, opacity: 0.65, marginTop: -8, marginBottom: 8, display: 'block' }}>
              RSI가 상승 전환하는 기울기가 클수록 반등 모멘텀이 강하여 높은 점수를 줍니다.
            </Text>
          </Col>
          <Col span={12}>
            <Form.Item label="RSI 레벨" name="w_rsi_level" style={{ marginBottom: 8 }}>
              <Slider min={0} max={3} step={0.1} />
            </Form.Item>
            <Text style={{ fontSize: 12, opacity: 0.65, marginTop: -8, marginBottom: 8, display: 'block' }}>
              RSI가 낮을수록(과매도) 반등 가능성이 높아 높은 점수를 줍니다.
            </Text>
          </Col>
        </Row>
        <Row gutter={16}>
          <Col span={24}>
            <Form.Item label="진입 스코어 임계값" style={{ marginBottom: 24 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, opacity: 0.65, marginBottom: 8 }}>
                <span>공격적 (55)</span>
                <span>보수적 (90)</span>
              </div>
              <Row gutter={16} align="middle">
                <Col span={18}>
                  <Form.Item name="entry_score_threshold" noStyle>
                    <Slider
                      min={0}
                      max={100}
                      step={1}
                      marks={{ 55: '공격적', 70: '균형', 90: '보수적' }}
                    />
                  </Form.Item>
                </Col>
                <Col span={6}>
                  <Form.Item name="entry_score_threshold" noStyle>
                    <InputNumber min={0} max={100} step={1} style={{ width: '100%' }} />
                  </Form.Item>
                </Col>
              </Row>
              <Text style={{ fontSize: 12, opacity: 0.65, display: 'block', marginTop: 8 }}>
                기본값 78은 운영 튜닝 기준값입니다. 횡보장에서 과도한 진입을 줄이면서도 유효 신호를 놓치지 않도록 맞춘 값이며,
                추세장/변동성 폭발 구간에서는 레짐 오프셋이 더해져 실효 임계치가 자동으로 높아집니다.
              </Text>
            </Form.Item>
          </Col>
        </Row>
        <div style={{ marginTop: 8, padding: 16, backgroundColor: 'rgba(255, 255, 255, 0.04)', borderRadius: 8, border: '1px solid rgba(255, 255, 255, 0.1)' }}>
          <Typography.Title level={5} style={{ marginTop: 0, marginBottom: 12, fontSize: 14 }}>
            실시간 스코어 시뮬레이션
          </Typography.Title>
          <Row gutter={[8, 8]}>
            {simulationResult.details.map((detail, idx) => (
              <Col span={12} key={idx}>
                <Text style={{ fontSize: 12, opacity: 0.8 }}>
                  {detail.label}: {detail.weight} × {detail.score} = <Text strong>{detail.weighted.toFixed(1)}</Text>
                </Text>
              </Col>
            ))}
          </Row>
          <Divider style={{ margin: '12px 0', borderColor: 'rgba(255, 255, 255, 0.1)' }} />
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Text style={{ fontSize: 13 }}>총 가중 평균 스코어:</Text>
            <Text strong style={{ fontSize: 16, color: isPass ? '#52c41a' : '#ff4d4f' }}>
              {simulationResult.totalScore.toFixed(1)}점
            </Text>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 4 }}>
            <Text style={{ fontSize: 12, opacity: 0.65 }}>진입 임계값 ({threshold}점) 기준</Text>
            <Text strong style={{ fontSize: 13, color: isPass ? '#52c41a' : '#ff4d4f' }}>
              {isPass ? '매수 조건 충족' : '매수 조건 미달'}
            </Text>
          </div>
          <Text style={{ fontSize: 11, opacity: 0.45, display: 'block', marginTop: 12 }}>
            * 위 점수는 예시 시장 상황(RSI=28, ADX=18 등)을 기준으로 시뮬레이션한 결과입니다.
          </Text>
        </div>

        {/* ── 매도 청산 조건 (스코어링) ── */}
        <Divider titlePlacement="left" plain>
          매도 청산 조건 (스코어링)
        </Divider>
        <Alert
          description="각 청산 조건이 맞을 때마다 점수를 부여합니다. 총점이 '청산 스코어 임계값'을 넘으면 봇이 매도를 실행합니다. 중요하게 생각하는 조건의 점수를 높여보세요."
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
        />
        <Row gutter={16}>
          <Col span={12}>
            <Form.Item label="RSI 과매수" name="w_exit_rsi_level" style={{ marginBottom: 8 }}>
              <Slider min={0} max={3} step={0.1} />
            </Form.Item>
            <Text style={{ fontSize: 12, opacity: 0.65, marginTop: -8, marginBottom: 8, display: 'block' }}>
              RSI가 높을수록(과매수) 하락 반전 가능성이 높아 높은 점수를 줍니다.
            </Text>
          </Col>
          <Col span={12}>
            <Form.Item label="BB 위치" name="w_exit_bb_position" style={{ marginBottom: 8 }}>
              <Slider min={0} max={3} step={0.1} />
            </Form.Item>
            <Text style={{ fontSize: 12, opacity: 0.65, marginTop: -8, marginBottom: 8, display: 'block' }}>
              가격이 볼린저 상단에 가까울수록 과열 신호로 높은 점수를 줍니다.
            </Text>
          </Col>
        </Row>
        <Row gutter={16}>
          <Col span={12}>
            <Form.Item label="수익률" name="w_exit_profit_pct" style={{ marginBottom: 8 }}>
              <Slider min={0} max={3} step={0.1} />
            </Form.Item>
            <Text style={{ fontSize: 12, opacity: 0.65, marginTop: -8, marginBottom: 8, display: 'block' }}>
              현재 수익률이 높을수록 익절 타이밍으로 높은 점수를 줍니다.
            </Text>
          </Col>
          <Col span={12}>
            <Form.Item label="ADX 추세" name="w_exit_adx_trend" style={{ marginBottom: 8 }}>
              <Slider min={0} max={3} step={0.1} />
            </Form.Item>
            <Text style={{ fontSize: 12, opacity: 0.65, marginTop: -8, marginBottom: 8, display: 'block' }}>
              추세가 약해질수록(ADX 하락) 청산 신호로 높은 점수를 줍니다.
            </Text>
          </Col>
        </Row>
        <Row gutter={16}>
          <Col span={24}>
            <Form.Item label="청산 스코어 임계값" style={{ marginBottom: 24 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, opacity: 0.65, marginBottom: 8 }}>
                <span>공격적 (55)</span>
                <span>보수적 (90)</span>
              </div>
              <Row gutter={16} align="middle">
                <Col span={18}>
                  <Form.Item name="exit_score_threshold" noStyle>
                    <Slider
                      min={0}
                      max={100}
                      step={1}
                      marks={{ 55: '공격적', 70: '균형', 90: '보수적' }}
                    />
                  </Form.Item>
                </Col>
                <Col span={6}>
                  <Form.Item name="exit_score_threshold" noStyle>
                    <InputNumber min={0} max={100} step={1} style={{ width: '100%' }} />
                  </Form.Item>
                </Col>
              </Row>
            </Form.Item>
          </Col>
        </Row>
        <div style={{ marginTop: 8, padding: 16, backgroundColor: 'rgba(255, 255, 255, 0.04)', borderRadius: 8, border: '1px solid rgba(255, 255, 255, 0.1)' }}>
          <Typography.Title level={5} style={{ marginTop: 0, marginBottom: 12, fontSize: 14 }}>
            실시간 청산 스코어 시뮬레이션
          </Typography.Title>
          <Row gutter={[8, 8]}>
            {exitSimulationResult.details.map((detail, idx) => (
              <Col span={12} key={idx}>
                <Text style={{ fontSize: 12, opacity: 0.8 }}>
                  {detail.label}: {detail.weight} × {detail.score} = <Text strong>{detail.weighted.toFixed(1)}</Text>
                </Text>
              </Col>
            ))}
          </Row>
          <Divider style={{ margin: '12px 0', borderColor: 'rgba(255, 255, 255, 0.1)' }} />
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Text style={{ fontSize: 13 }}>총 가중 평균 스코어:</Text>
            <Text strong style={{ fontSize: 16, color: isExitPass ? '#52c41a' : '#ff4d4f' }}>
              {exitSimulationResult.totalScore.toFixed(1)}점
            </Text>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 4 }}>
            <Text style={{ fontSize: 12, opacity: 0.65 }}>청산 임계값 ({exitThreshold}점) 기준</Text>
            <Text strong style={{ fontSize: 13, color: isExitPass ? '#52c41a' : '#ff4d4f' }}>
              {isExitPass ? '청산 조건 충족' : '청산 조건 미달'}
            </Text>
          </div>
          <Text style={{ fontSize: 11, opacity: 0.45, display: 'block', marginTop: 12 }}>
            * 위 점수는 예시 포지션 상황(RSI=83, BB상단근접 등)을 기준으로 시뮬레이션한 결과입니다.
          </Text>
        </div>

        {/* ── 매도 상세 설정 ── */}
        <Divider titlePlacement="left" plain>
          매도 상세 설정
        </Divider>
        <Row gutter={16}>
          <Col span={8}>
            <Form.Item label="트레일링 스탑 ATR 배수" name="trailing_stop_atr_multiplier">
              <InputNumber min={0.5} max={5} step={0.1} style={{ width: '100%' }} />
            </Form.Item>
            <Text style={{ fontSize: 12, opacity: 0.65, marginTop: -8, marginBottom: 8, display: 'block' }}>
              1차 익절 후 고점 대비 ATR × 이 값만큼 하락하면 전량 매도합니다.
            </Text>
          </Col>
          <Col span={8}>
            <Form.Item label="1차 익절 매도 비율" name="take_profit_sell_ratio">
              <InputNumber min={0.1} max={0.9} step={0.1} style={{ width: '100%' }} />
            </Form.Item>
            <Text style={{ fontSize: 12, opacity: 0.65, marginTop: -8, marginBottom: 8, display: 'block' }}>
              1차 익절 시 매도할 비율입니다. 0.5 = 50% 매도.
            </Text>
          </Col>
          <Col span={8}>
            <Form.Item label="최소 수익률" name="min_profit_margin">
              <InputNumber min={0} max={0.05} step={0.001} style={{ width: '100%' }} />
            </Form.Item>
            <Text style={{ fontSize: 12, opacity: 0.65, marginTop: -8, marginBottom: 8, display: 'block' }}>
              1차 익절 실행을 위한 최소 수익률입니다. 수수료(0.1%) + 알파.
            </Text>
          </Col>
        </Row>
        {/* ── 시장 레짐 설정 ── */}
        <Divider titlePlacement="left" plain>
          시장 레짐 설정
        </Divider>
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          title="BTC 기준으로 시장 상태를 판단하여 진입 임계치를 동적으로 조정합니다. 추세장/변동성 폭발 시 임계치를 높여 더 확실한 기회만 포착합니다."
        />
        <Row gutter={16}>
          <Col span={12}>
            <Form.Item label="ADX 추세장 기준" name="regime_adx_trending_threshold">
              <InputNumber min={20} max={45} step={1} style={{ width: '100%' }} />
            </Form.Item>
            <Text style={{ fontSize: 12, opacity: 0.65, marginTop: -8, marginBottom: 8, display: 'block' }}>
              BTC의 ADX가 이 값 이상이면 추세장으로 판단합니다.
            </Text>
          </Col>
          <Col span={12}>
            <Form.Item label="변동성 폭발 기준" name="regime_vol_overload_ratio">
              <InputNumber min={1.5} max={4.0} step={0.1} style={{ width: '100%' }} />
            </Form.Item>
            <Text style={{ fontSize: 12, opacity: 0.65, marginTop: -8, marginBottom: 8, display: 'block' }}>
              변동성 비율이 이 값 이상이면 변동성 폭발로 판단합니다.
            </Text>
          </Col>
        </Row>
        <Row gutter={16}>
          <Col span={12}>
            <Form.Item label="추세장 임계치 가산" name="regime_trending_offset">
              <InputNumber min={0} max={30} step={1} style={{ width: '100%' }} />
            </Form.Item>
            <Text style={{ fontSize: 12, opacity: 0.65, marginTop: -8, marginBottom: 8, display: 'block' }}>
              추세장에서 진입 임계치를 이 값만큼 높입니다. 높을수록 진입이 어려워집니다.
            </Text>
          </Col>
          <Col span={12}>
            <Form.Item label="변동성 폭발 임계치 가산" name="regime_volatile_offset">
              <InputNumber min={0} max={30} step={1} style={{ width: '100%' }} />
            </Form.Item>
            <Text style={{ fontSize: 12, opacity: 0.65, marginTop: -8, marginBottom: 8, display: 'block' }}>
              변동성 폭발 시 진입 임계치를 이 값만큼 높입니다. 높을수록 진입이 어려워집니다.
            </Text>
          </Col>
        </Row>
      </Form>
    </Modal>
  );
}
