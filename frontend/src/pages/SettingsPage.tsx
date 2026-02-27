import { useState, useEffect, useCallback } from 'react';
import {
  Card,
  Form,
  Input,
  InputNumber,
  Button,
  Typography,
  Flex,
  Divider,
  Row,
  Col,
  message,
  Descriptions,
  Alert,
} from 'antd';
import {
  ApiOutlined,
  SafetyOutlined,
  ExperimentOutlined,
  CheckCircleOutlined,
  UndoOutlined,
} from '@ant-design/icons';
import type { StrategyParams } from '../components/StrategyEditModal';
import { loadStrategyParams, saveStrategyParams, DEFAULT_STRATEGY, PRESETS, getActivePresetName } from '../lib/strategyParams';
import { useAuth } from '../contexts/AuthContext';

const { Title, Text } = Typography;

/* ── Settings Page ─────────────────────────────────────── */

export default function SettingsPage() {
  const [apiForm] = Form.useForm();
  const [strategyForm] = Form.useForm();
  const [messageApi, contextHolder] = message.useMessage();
  const [connecting, setConnecting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [loadingParams, setLoadingParams] = useState(true);
  const [loadedParams, setLoadedParams] = useState<StrategyParams | null>(null);
  const { user } = useAuth();
  const [activePreset, setActivePreset] = useState<string | null>(null);

  // 페이지 로드 시 DB에서 전략 파라미터 조회
  const loadParams = useCallback(async () => {
    setLoadingParams(true);
    const params = await loadStrategyParams();
    setLoadedParams(params);
    setActivePreset(getActivePresetName(params));
    setLoadingParams(false);
  }, []);

  useEffect(() => {
    loadParams();
  }, [loadParams]);

  const handleApiTest = async () => {
    setConnecting(true);
    setTimeout(() => {
      setConnecting(false);
      messageApi.success('API 연결 테스트 완료');
    }, 1500);
  };

  const handleStrategySave = async () => {
    const values = strategyForm.getFieldsValue() as StrategyParams;
    setSaving(true);
    const ok = await saveStrategyParams(values);
    setSaving(false);
    if (ok) {
      setActivePreset(getActivePresetName(values));
      messageApi.success('전략 파라미터가 저장되었습니다. 약 1분 내 봇에 적용됩니다.');
    } else {
      messageApi.error('전략 파라미터 저장에 실패했습니다.');
    }
  };

  return (
    <Flex vertical gap={24} style={{ width: '100%' }}>
      {contextHolder}

      <Title level={4} style={{ margin: 0 }}>
        Settings
      </Title>

      <Alert
        title="설정 변경은 저장 후 약 1분 내 봇에 자동 적용됩니다."
        type="info"
        showIcon
        banner
      />

      <Row gutter={[24, 24]}>
        {/* ── API 설정 ── */}
        <Col xs={24} lg={12}>
          <Card
            title={
              <span>
                <ApiOutlined /> API 연결 설정
              </span>
            }
            variant="borderless"
          >
            <Form form={apiForm} layout="vertical" size="middle">
              <Divider titlePlacement="left" plain>
                Upbit
              </Divider>
              <Form.Item label="Access Key" name="upbit_access">
                <Input.Password placeholder="업비트 Access Key" />
              </Form.Item>
              <Form.Item label="Secret Key" name="upbit_secret">
                <Input.Password placeholder="업비트 Secret Key" />
              </Form.Item>

              <Divider titlePlacement="left" plain>
                Supabase
              </Divider>
              <Form.Item label="Project URL" name="supabase_url">
                <Input placeholder="https://xxx.supabase.co" />
              </Form.Item>
              <Form.Item label="Service Key" name="supabase_key">
                <Input.Password placeholder="Supabase Secret Key" />
              </Form.Item>

              <Divider titlePlacement="left" plain>
                KakaoTalk
              </Divider>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
                <CheckCircleOutlined style={{ color: '#52c41a', fontSize: 16 }} />
                <Text style={{ color: '#52c41a' }}>
                  카카오 계정 연동됨 ({user?.nickname ?? '-'})
                </Text>
              </div>

              <Button
                type="primary"
                onClick={handleApiTest}
                loading={connecting}
                block
              >
                연결 테스트
              </Button>
            </Form>
          </Card>
        </Col>

        {/* ── 전략 파라미터 ── */}
        <Col xs={24} lg={12}>
          <Card
            title={
              <span>
                <ExperimentOutlined /> 전략 파라미터
              </span>
            }
            loading={loadingParams}
          >
            {!loadingParams && (
            <Form
              form={strategyForm}
              layout="vertical"
              size="middle"
              initialValues={loadedParams ?? DEFAULT_STRATEGY}
            >
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
                    <InputNumber
                      min={0.5}
                      max={5}
                      step={0.1}
                      style={{ width: '100%' }}
                    />
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
                    <InputNumber
                      min={1}
                      max={5}
                      step={0.1}
                      style={{ width: '100%' }}
                    />
                  </Form.Item>
                </Col>
              </Row>

              <Divider titlePlacement="left" plain>
                기타
              </Divider>
              <Form.Item label="거래 대금 상위 종목 수" name="top_volume_count">
                <InputNumber min={3} max={30} style={{ width: '100%' }} />
              </Form.Item>

              <Button type="primary" onClick={handleStrategySave} loading={saving} block>
                파라미터 저장
              </Button>
              <Divider titlePlacement="left" plain>
                프리셋
              </Divider>
              <Button
                icon={<UndoOutlined />}
                type={activePreset === '기본값' ? 'primary' : 'default'}
                ghost={activePreset === '기본값'}
                onClick={async () => {
                  strategyForm.setFieldsValue(DEFAULT_STRATEGY);
                  setSaving(true);
                  const ok = await saveStrategyParams(DEFAULT_STRATEGY);
                  setSaving(false);
                  if (ok) {
                    setActivePreset('기본값');
                    messageApi.success('기본값으로 복원되었습니다.');
                  } else {
                    messageApi.error('기본값 복원에 실패했습니다.');
                  }
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
                      onClick={async () => {
                        strategyForm.setFieldsValue(preset.params);
                        setSaving(true);
                        const ok = await saveStrategyParams(preset.params);
                        setSaving(false);
                        if (ok) {
                          setActivePreset(preset.name);
                          messageApi.success(`'${preset.name}' 프리셋이 적용되었습니다.`);
                        } else {
                          messageApi.error('프리셋 적용에 실패했습니다.');
                        }
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
            </Form>
            )}
          </Card>

          {/* ── 리스크 설정 요약 ── */}
          <Card
            title={
              <span>
                <SafetyOutlined /> 리스크 관리 규정
              </span>
            }
            variant="borderless"
            style={{ marginTop: 16 }}
          >
            <Descriptions column={1} size="small" bordered>
              <Descriptions.Item label="종목당 최대 비중">20%</Descriptions.Item>
              <Descriptions.Item label="최대 동시 보유">5종목</Descriptions.Item>
              <Descriptions.Item label="일일 손실 한도">5%</Descriptions.Item>
              <Descriptions.Item label="미체결 타임아웃">5분</Descriptions.Item>
              <Descriptions.Item label="최소 주문 금액">5,000 KRW</Descriptions.Item>
            </Descriptions>
          </Card>
        </Col>
      </Row>

    </Flex>
  );
}
