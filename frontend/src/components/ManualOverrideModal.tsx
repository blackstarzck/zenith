import {
  Modal,
  Button,
  Typography,
  Space,
  Alert,
  Tag,
  Switch,
} from 'antd';
import {
  PauseCircleOutlined,
  PlayCircleOutlined,
  CloseCircleOutlined,
} from '@ant-design/icons';

const { Text, Title } = Typography;

export type BotStatus = 'active' | 'paused' | 'stopped';

interface PositionSummary {
  symbol: string;
  pnl: number;
}

interface Props {
  open: boolean;
  onClose: () => void;
  botStatus: BotStatus;
  onBotToggle: (paused: boolean) => void;
  positions: PositionSummary[];
  onClosePosition: (symbol: string) => void;
}

export default function ManualOverrideModal({
  open,
  onClose,
  botStatus,
  onBotToggle,
  positions,
  onClosePosition,
}: Props) {
  const isActive = botStatus === 'active';

  return (
    <Modal
      open={open}
      onCancel={onClose}
      title={
        <Space>
          {isActive ? (
            <PauseCircleOutlined style={{ color: '#faad14', fontSize: 20 }} />
          ) : (
            <PlayCircleOutlined style={{ color: '#52c41a', fontSize: 20 }} />
          )}
          <Title level={5} style={{ margin: 0 }}>
            수동 제어
          </Title>
        </Space>
      }
      footer={
        <Button onClick={onClose}>닫기</Button>
      }
      width={500}
      destroyOnHidden
    >
      {/* Bot control */}
      <Alert
title={
          isActive
            ? '봇이 현재 실행 중입니다. 일시정지하면 신규 진입이 중단됩니다.'
            : '봇이 일시정지 상태입니다. 재시작하면 자동 매매가 재개됩니다.'
        }
        type={isActive ? 'success' : 'warning'}
        showIcon
        style={{ marginBottom: 16 }}
      />

      <Space
        style={{
          width: '100%',
          justifyContent: 'space-between',
          padding: '12px 0',
          borderBottom: '1px solid #303030',
          marginBottom: 16,
        }}
      >
        <Text strong style={{ fontSize: 15 }}>
          자동 매매
        </Text>
        <Space>
          <Tag color={isActive ? 'green' : 'orange'}>
            {isActive ? '실행 중' : '일시정지'}
          </Tag>
          <Switch
            checked={isActive}
            onChange={(checked) => onBotToggle(!checked)}
            checkedChildren={<PlayCircleOutlined />}
            unCheckedChildren={<PauseCircleOutlined />}
          />
        </Space>
      </Space>

      {/* Position list */}
      <Text strong style={{ fontSize: 14, display: 'block', marginBottom: 8 }}>
        보유 포지션 ({positions.length})
      </Text>

      {positions.length > 0 ? (
        <div>
          {positions.map((pos) => {
            const pnlColor = pos.pnl >= 0 ? '#52c41a' : '#ff4d4f';
            return (
              <div
                key={pos.symbol}
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  padding: '8px 0',
                  borderBottom: '1px solid #303030',
                }}
              >
                <div>
                  <Text strong>{pos.symbol.replace('KRW-', '')}</Text>
                  <br />
                  <Text style={{ color: pnlColor, fontSize: 12 }}>
                    {pos.pnl >= 0 ? '+' : ''}
                    {Math.round(pos.pnl).toLocaleString()} KRW
                  </Text>
                </div>
                <Button
                  danger
                  size="small"
                  icon={<CloseCircleOutlined />}
                  onClick={() => onClosePosition(pos.symbol)}
                >
                  종료
                </Button>
              </div>
            );
          })}
        </div>
      ) : (
        <Text type="secondary" style={{ display: 'block', textAlign: 'center', padding: 24 }}>
          보유 포지션 없음
        </Text>
      )}
    </Modal>
  );
}
