import { Button, Typography, Flex, Card } from 'antd';
import { useAuth } from '../contexts/AuthContext';

const { Title, Text } = Typography;

export default function LoginPage() {
  const { login } = useAuth();

  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: '#0a0a0a',
      }}
    >
      <Card
        variant="borderless"
        style={{
          width: 400,
          textAlign: 'center',
          background: '#1a1a1a',
          borderRadius: 12,
          border: '1px solid #303030',
        }}
      >
        <Flex vertical gap={24} style={{ width: '100%' }}>
          <div>
            <Title
              level={2}
              style={{ margin: 0, color: '#fff', letterSpacing: 4 }}
            >
              ZENITH
            </Title>
            <Text type="secondary" style={{ fontSize: 13 }}>
              Crypto Auto-Trading Dashboard
            </Text>
          </div>

          <Text style={{ color: '#999', fontSize: 14 }}>
            카카오 계정으로 로그인하여
            <br />
            대시보드에 접속하세요.
          </Text>

          <Button
            type="primary"
            size="large"
            block
            onClick={login}
            style={{
              height: 48,
              fontSize: 16,
              fontWeight: 600,
              background: '#FEE500',
              color: '#191919',
              border: 'none',
              borderRadius: 8,
            }}
          >
            카카오 로그인
          </Button>

          <Text type="secondary" style={{ fontSize: 11 }}>
            로그인 시 카카오톡 알림 전송 권한이 함께 부여됩니다.
          </Text>
        </Flex>
      </Card>
    </div>
  );
}
