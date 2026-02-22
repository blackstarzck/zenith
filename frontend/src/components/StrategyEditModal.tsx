import { useEffect } from 'react';
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
} from 'antd';
import { EditOutlined } from '@ant-design/icons';

const { Title } = Typography;

export interface StrategyParams {
  bb_period: number;
  bb_std_dev: number;
  rsi_period: number;
  rsi_oversold: number;
  atr_period: number;
  atr_multiplier: number;
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

  useEffect(() => {
    if (open) {
      form.setFieldsValue(currentParams);
    }
  }, [open, currentParams, form]);

  const handleApply = () => {
    const values = form.getFieldsValue();
    onApply(values);
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
      destroyOnClose
    >
      <Alert
        message="실시간 변경은 다음 틱부터 적용됩니다"
        type="warning"
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
            <Form.Item label="손절 계수" name="atr_multiplier">
              <InputNumber min={1} max={5} step={0.1} style={{ width: '100%' }} />
            </Form.Item>
          </Col>
        </Row>
      </Form>
    </Modal>
  );
}
