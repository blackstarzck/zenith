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
} from 'antd';
import { EditOutlined, UndoOutlined, CheckOutlined } from '@ant-design/icons';
import { DEFAULT_STRATEGY as SHARED_DEFAULT, PRESETS, getActivePresetName } from '../lib/strategyParams';

const { Title } = Typography;

export interface StrategyParams {
  bb_period: number;
  bb_std_dev: number;
  rsi_period: number;
  rsi_oversold: number;
  atr_period: number;
  atr_stop_multiplier: number;
  top_volume_count?: number;
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
      width={520}
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
      </Form>
    </Modal>
  );
}
