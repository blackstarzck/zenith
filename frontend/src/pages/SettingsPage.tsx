import { useState } from 'react';
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
  EditOutlined,
  CheckCircleOutlined,
} from '@ant-design/icons';
import StrategyEditModal from '../components/StrategyEditModal';
import type { StrategyParams } from '../components/StrategyEditModal';
import { useAuth } from '../contexts/AuthContext';

const { Title, Text } = Typography;

/* ── Settings Page ─────────────────────────────────────── */

export default function SettingsPage() {
  const [apiForm] = Form.useForm();
  const [strategyForm] = Form.useForm();
  const [messageApi, contextHolder] = message.useMessage();
  const [connecting, setConnecting] = useState(false);
  const [strategyEditOpen, setStrategyEditOpen] = useState(false);
  const { user } = useAuth();

  const handleApiTest = async () => {
    setConnecting(true);
    // 시뮬레이션: 실제로는 프록시 API 호출
    setTimeout(() => {
      setConnecting(false);
      messageApi.success('API 연결 테스트 완료');
    }, 1500);
  };

  const handleStrategySave = () => {
    const values = strategyForm.getFieldsValue();
    console.log('Strategy params:', values);
    messageApi.success('전략 파라미터가 저장되었습니다.');
  };

  return (
    <Flex vertical gap={24} style={{ width: '100%' }}>
      {contextHolder}

      <Title level={4} style={{ margin: 0 }}>
        Settings
      </Title>

      <Alert
        title="주의: 설정 변경은 봇 재시작 후 반영됩니다."
        type="warning"
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
            variant="borderless"
          >
            <Form
              form={strategyForm}
              layout="vertical"
              size="middle"
              initialValues={{
                bb_period: 20,
                bb_std_dev: 2.0,
                rsi_period: 14,
                rsi_oversold: 30,
                atr_period: 14,
                atr_multiplier: 2.5,
                top_volume: 10,
              }}
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
                  <Form.Item label="손절 계수" name="atr_multiplier">
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
              <Form.Item label="거래 대금 상위 종목 수" name="top_volume">
                <InputNumber min={3} max={30} style={{ width: '100%' }} />
              </Form.Item>

              <Button type="primary" onClick={handleStrategySave} block>
                파라미터 저장
              </Button>
              <Button
                icon={<EditOutlined />}
                onClick={() => setStrategyEditOpen(true)}
                block
                style={{ marginTop: 8 }}
              >
                실시간 수정
              </Button>
            </Form>
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

      <StrategyEditModal
        open={strategyEditOpen}
        onClose={() => setStrategyEditOpen(false)}
        currentParams={{
          bb_period: strategyForm.getFieldValue('bb_period') ?? 20,
          bb_std_dev: strategyForm.getFieldValue('bb_std_dev') ?? 2.0,
          rsi_period: strategyForm.getFieldValue('rsi_period') ?? 14,
          rsi_oversold: strategyForm.getFieldValue('rsi_oversold') ?? 30,
          atr_period: strategyForm.getFieldValue('atr_period') ?? 14,
          atr_multiplier: strategyForm.getFieldValue('atr_multiplier') ?? 2.5,
        }}
        onApply={(params: StrategyParams) => {
          strategyForm.setFieldsValue(params);
          messageApi.success('전략 파라미터가 실시간 적용되었습니다.');
        }}
      />
    </Flex>
  );
}
