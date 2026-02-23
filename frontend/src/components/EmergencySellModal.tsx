import { useState, useEffect } from 'react';
import {
  Modal,
  Button,
  Typography,
  Descriptions,
  Space,
  Alert,
} from 'antd';
import { ExclamationCircleOutlined, ThunderboltOutlined } from '@ant-design/icons';

const { Text, Title } = Typography;

export interface EmergencyPosition {
  symbol: string;
  volume: number;
  currentPrice: number;
  avgPrice: number;
  pnl: number;
}

interface Props {
  open: boolean;
  onClose: () => void;
  position: EmergencyPosition | null;
}

export default function EmergencySellModal({ open, onClose, position }: Props) {
  const [countdown, setCountdown] = useState(3);
  const [confirmed, setConfirmed] = useState(false);

  useEffect(() => {
    if (!open) {
      setCountdown(3);
      setConfirmed(false);
      return;
    }

    if (countdown <= 0) {
      setConfirmed(true);
      return;
    }

    const timer = setTimeout(() => setCountdown((c) => c - 1), 1000);
    return () => clearTimeout(timer);
  }, [open, countdown]);

  if (!position) return null;

  const pnlColor = position.pnl >= 0 ? '#52c41a' : '#ff4d4f';
  const pnlPct =
    position.avgPrice > 0
      ? ((position.currentPrice - position.avgPrice) / position.avgPrice) * 100
      : 0;

  const handleSell = () => {
    // TODO: 실제 매도 API 호출
    console.log('Emergency sell:', position.symbol);
    onClose();
  };

  return (
    <Modal
      open={open}
      onCancel={onClose}
      title={
        <Space>
          <ExclamationCircleOutlined style={{ color: '#ff4d4f', fontSize: 20 }} />
          <Title level={5} style={{ margin: 0, color: '#ff4d4f' }}>
            긴급 매도
          </Title>
        </Space>
      }
      footer={
        <Space style={{ width: '100%', justifyContent: 'flex-end' }}>
          <Button onClick={onClose}>취소</Button>
          <Button
            danger
            type="primary"
            size="large"
            icon={<ThunderboltOutlined />}
            disabled={!confirmed}
            onClick={handleSell}
          >
            {confirmed
              ? '긴급 매도 실행'
              : `확인 대기 (${countdown}s)`}
          </Button>
        </Space>
      }
      styles={{
        header: { borderBottom: '1px solid #ff4d4f33' },
        body: { paddingTop: 16 },
      }}
      width={480}
      destroyOnClose
    >
      <Alert
        title="시장가 매도가 즉시 실행됩니다. 이 작업은 되돌릴 수 없습니다."
        type="error"
        showIcon
        style={{ marginBottom: 16 }}
      />

      <Descriptions column={1} size="small" bordered>
        <Descriptions.Item label="종목">
          <Text strong>{position.symbol.replace('KRW-', '')}</Text>
        </Descriptions.Item>
        <Descriptions.Item label="보유 수량">
          {position.volume.toFixed(8)}
        </Descriptions.Item>
        <Descriptions.Item label="평균 매수가">
          {position.avgPrice.toLocaleString()} KRW
        </Descriptions.Item>
        <Descriptions.Item label="현재가">
          {position.currentPrice.toLocaleString()} KRW
        </Descriptions.Item>
        <Descriptions.Item label="평가 손익">
          <Text style={{ color: pnlColor, fontWeight: 600 }}>
            {position.pnl >= 0 ? '+' : ''}
            {Math.round(position.pnl).toLocaleString()} KRW ({pnlPct >= 0 ? '+' : ''}
            {pnlPct.toFixed(2)}%)
          </Text>
        </Descriptions.Item>
      </Descriptions>
    </Modal>
  );
}
