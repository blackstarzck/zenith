import { Typography, Empty } from 'antd';
import { FundProjectionScreenOutlined } from '@ant-design/icons';

const { Title, Text } = Typography;

/**
 * 거래소 간 괴리(Dislocation) 모의매매 페이지.
 * 기능 구현 전 플레이스홀더입니다.
 */
export default function DislocationPaperPage() {
  return (
    <div style={{ padding: 24 }}>
      <Title level={3}>
        <FundProjectionScreenOutlined style={{ marginRight: 8 }} />
        거래소 괴리 모의매매
      </Title>
      <Empty
        description={
          <Text type="secondary">
            거래소 간 가격 괴리를 활용한 모의매매 기능이 준비 중입니다.
          </Text>
        }
        style={{ marginTop: 80 }}
      />
    </div>
  );
}
