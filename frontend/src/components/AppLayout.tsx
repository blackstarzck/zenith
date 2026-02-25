import { useState } from 'react';
import { Layout, Menu, Typography, Tooltip, Progress, Avatar, Dropdown, Drawer, Badge, Tag, Empty, DatePicker, Button, Spin, Space } from 'antd';
import {
  DashboardOutlined,
  SwapOutlined,
  BarChartOutlined,
  SettingOutlined,
  ApiOutlined,
  UserOutlined,
  LogoutOutlined,
  CodeOutlined,
  CheckCircleOutlined,
  WarningOutlined,
  CloseCircleOutlined,
  ThunderboltOutlined,
  LeftOutlined,
  RightOutlined,
  InfoCircleOutlined,
  FileTextOutlined,
} from '@ant-design/icons';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useSystemLogs, useBotState } from '../hooks/useSupabase';
import type { SystemLog, UpbitStatus, KakaoStatus } from '../types/database';
import dayjs from 'dayjs';
import type { Dayjs } from 'dayjs';

const { Sider, Header, Content } = Layout;
const { Text } = Typography;

const menuItems = [
  { key: '/', icon: <DashboardOutlined />, label: 'Dashboard' },
  { key: '/trading', icon: <SwapOutlined />, label: 'Trading' },
  { key: '/analytics', icon: <BarChartOutlined />, label: 'Analytics' },
  { key: '/settings', icon: <SettingOutlined />, label: 'Settings' },
  { key: '/reports', icon: <FileTextOutlined />, label: 'Reports' },
];

/* ── 업비트 · 카카오 상태 라벨 ─────────────────────────── */
const UPBIT_STATUS_LABEL: Record<UpbitStatus, { text: string; color: string }> = {
  connected:    { text: '연결됨',     color: '#52c41a' },
  auth_failed:  { text: '인증실패',   color: '#ff4d4f' },
  rate_limited: { text: '요청제한',   color: '#faad14' },
  error:        { text: '오류',       color: '#ff4d4f' },
  unknown:      { text: '확인 중',    color: '#666' },
};

const KAKAO_STATUS_LABEL: Record<KakaoStatus, { text: string; color: string }> = {
  connected:     { text: '연결됨',       color: '#52c41a' },
  token_expired: { text: '토큰만료',     color: '#ff4d4f' },
  send_failed:   { text: '전송실패',     color: '#faad14' },
  no_token:      { text: '미설정',       color: '#666' },
  unknown:       { text: '확인 중',      color: '#666' },
};

/* ── 로그 레벨별 시각 설정 ─────────────────────────────── */
const LOG_LEVEL_CONFIG: Record<
  SystemLog['level'],
  {
    icon: React.ReactNode;
    tagColor: string;
    textColor: string;
    rowBg: string;
    borderLeft: string;
  }
> = {
  INFO: {
    icon: <CheckCircleOutlined style={{ color: '#52c41a', fontSize: 12 }} />,
    tagColor: 'green',
    textColor: '#bbb',
    rowBg: 'transparent',
    borderLeft: '2px solid transparent',
  },
  WARNING: {
    icon: <WarningOutlined style={{ color: '#faad14', fontSize: 12 }} />,
    tagColor: 'orange',
    textColor: '#faad14',
    rowBg: 'rgba(250, 173, 20, 0.04)',
    borderLeft: '2px solid #faad14',
  },
  ERROR: {
    icon: <CloseCircleOutlined style={{ color: '#ff4d4f', fontSize: 12 }} />,
    tagColor: 'red',
    textColor: '#ff6b6b',
    rowBg: 'rgba(255, 77, 79, 0.06)',
    borderLeft: '2px solid #ff4d4f',
  },
  CRITICAL: {
    icon: <ThunderboltOutlined style={{ color: '#ff1744', fontSize: 12 }} />,
    tagColor: '#a8071a',
    textColor: '#ff4d6a',
    rowBg: 'rgba(255, 23, 68, 0.10)',
    borderLeft: '2px solid #ff1744',
  },
};

function getLogConfig(level: SystemLog['level']) {
  return LOG_LEVEL_CONFIG[level] ?? LOG_LEVEL_CONFIG.INFO;
}

export default function AppLayout() {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, logout } = useAuth();
  const { botState } = useBotState();
  const [apiUsage] = useState(35);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [selectedDate, setSelectedDate] = useState<string>(dayjs().format('YYYY-MM-DD'));
  const { logs, loading: logsLoading } = useSystemLogs(selectedDate, 500, drawerOpen);
  const isToday = selectedDate === dayjs().format('YYYY-MM-DD');

  const upbitStatus: UpbitStatus = botState?.upbit_status ?? 'unknown';
  const kakaoStatus: KakaoStatus = botState?.kakao_status ?? 'unknown';
  const upbitLabel = UPBIT_STATUS_LABEL[upbitStatus] ?? UPBIT_STATUS_LABEL.unknown;
  const kakaoLabel = KAKAO_STATUS_LABEL[kakaoStatus] ?? KAKAO_STATUS_LABEL.unknown;
  const apiColor = apiUsage < 50 ? '#52c41a' : apiUsage < 80 ? '#faad14' : '#ff4d4f';

  const goToPrevDay = () => {
    setSelectedDate(dayjs(selectedDate).subtract(1, 'day').format('YYYY-MM-DD'));
  };

  const goToNextDay = () => {
    if (!isToday) {
      setSelectedDate(dayjs(selectedDate).add(1, 'day').format('YYYY-MM-DD'));
    }
  };

  const handleDateChange = (date: Dayjs | null) => {
    if (date) {
      setSelectedDate(date.format('YYYY-MM-DD'));
    }
  };

  const userMenuItems = [
    {
      key: 'logout',
      icon: <LogoutOutlined />,
      label: '로그아웃',
      onClick: logout,
    },
  ];

  return (
    <Layout style={{ height: '100vh', overflow: 'hidden' }}>
      <Sider
        breakpoint="lg"
        collapsedWidth={64}
        style={{
          background: '#141414',
          borderRight: '1px solid #303030',
          height: '100vh',
          overflowY: 'auto',
        }}
      >
        <div
          style={{
            height: 64,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            borderBottom: '1px solid #303030',
          }}
        >
          <Text strong style={{ color: '#fff', fontSize: 20, letterSpacing: 2 }}>
            ZENITH
          </Text>
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[location.pathname]}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
          style={{ background: '#141414', borderRight: 'none' }}
        />
      </Sider>

      <Layout style={{ overflow: 'hidden' }}>
        <Header
          style={{
            background: '#1a1a1a',
            borderBottom: '1px solid #303030',
            padding: '0 24px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'flex-end',
            gap: 16,
          }}
        >
          {/* 업비트 연결 상태 */}
          <Tooltip title={`업비트 API: ${upbitLabel.text}`} destroyOnHidden>
            <Tag
              style={{
                background: 'transparent',
                borderColor: upbitLabel.color,
                color: upbitLabel.color,
                fontSize: 11,
                margin: 0,
              }}
            >
              Upbit · {upbitLabel.text}
            </Tag>
          </Tooltip>

          {/* 카카오 인증 상태 */}
          <Tooltip title={`카카오 알림: ${kakaoLabel.text}`} destroyOnHidden>
            <Tag
              style={{
                background: 'transparent',
                borderColor: kakaoLabel.color,
                color: kakaoLabel.color,
                fontSize: 11,
                margin: 0,
              }}
            >
              Kakao · {kakaoLabel.text}
            </Tag>
          </Tooltip>

          {/* API Health Gauge */}
          <Tooltip title={`API 사용량: ${apiUsage}/100 (잔여 ${100 - apiUsage})`} destroyOnHidden>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <ApiOutlined style={{ color: apiColor, fontSize: 14 }} />
              <Progress
                type="circle"
                percent={apiUsage}
                size={28}
                strokeColor={apiColor}
                format={(pct) => `${pct}`}
                strokeWidth={10}
              />
            </div>
          </Tooltip>

          {/* Log Drawer Toggle */}
          <Tooltip title="백엔드 로그" destroyOnHidden>
            <Badge count={logs.length} size="small" offset={[-4, 4]} color="#1668dc">
              <div
                onClick={() => setDrawerOpen(true)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  cursor: 'pointer',
                  padding: '4px 8px',
                  borderRadius: 6,
                  transition: 'background 0.2s',
                }}
                onMouseEnter={(e) => (e.currentTarget.style.background = '#303030')}
                onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
              >
                <CodeOutlined style={{ color: '#e0e0e0', fontSize: 16 }} />
              </div>
            </Badge>
          </Tooltip>

          {/* User Profile */}
          {user && (
            <Dropdown menu={{ items: userMenuItems }} placement="bottomRight">
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  cursor: 'pointer',
                  padding: '4px 8px',
                  borderRadius: 6,
                  transition: 'background 0.2s',
                }}
                onMouseEnter={(e) => (e.currentTarget.style.background = '#303030')}
                onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
              >
                <Avatar
                  size={28}
                  src={user.profileImage || undefined}
                  icon={!user.profileImage ? <UserOutlined /> : undefined}
                  style={{ background: '#1668dc' }}
                />
                <Text style={{ color: '#e0e0e0', fontSize: 13 }}>
                  {user.nickname}
                </Text>
              </div>
            </Dropdown>
          )}
        </Header>
        <Content
          style={{
            margin: 24,
            overflow: 'auto',
          }}
        >
          <Outlet />
        </Content>
      </Layout>

      {/* Backend Log Drawer */}
      <Drawer
        title={
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <Space size={8}>
              <span style={{ color: '#d0d0d0' }}>
                <CodeOutlined style={{ marginRight: 8 }} />
                백엔드 로그
              </span>
              <Tooltip
                destroyOnHidden
                title={
                  <div>
                    <div style={{ marginBottom: 4, fontWeight: 600 }}>로그 유형 안내</div>
                    <div><CheckCircleOutlined style={{ color: '#52c41a' }} /> <b>INFO</b> — 정상 작동 기록</div>
                    <div><WarningOutlined style={{ color: '#faad14' }} /> <b>WARNING</b> — 주의 필요 (성능 저하, 재시도 등)</div>
                    <div><CloseCircleOutlined style={{ color: '#ff4d4f' }} /> <b>ERROR</b> — 오류 발생 (기능 일부 실패)</div>
                    <div><ThunderboltOutlined style={{ color: '#ff1744' }} /> <b>CRITICAL</b> — 심각한 장애 (봇 중단 가능)</div>
                  </div>
                }
              >
                <InfoCircleOutlined style={{ fontSize: 13, color: '#666', cursor: 'pointer' }} />
              </Tooltip>
            </Space>
            <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              <Button
                type="text"
                size="small"
                icon={<LeftOutlined style={{ color: '#aaa' }} />}
                onClick={goToPrevDay}
              />
              <DatePicker
                value={dayjs(selectedDate)}
                onChange={handleDateChange}
                size="small"
                allowClear={false}
                disabledDate={(current) => current && current > dayjs().endOf('day')}
                style={{
                  background: '#1f1f1f',
                  borderColor: '#303030',
                  width: 130,
                }}
              />
              <Button
                type="text"
                size="small"
                icon={<RightOutlined style={{ color: isToday ? '#444' : '#aaa' }} />}
                onClick={goToNextDay}
                disabled={isToday}
              />
              {!isToday && (
                <Button
                  type="link"
                  size="small"
                  onClick={() => setSelectedDate(dayjs().format('YYYY-MM-DD'))}
                  style={{ fontSize: 11, padding: '0 4px' }}
                >
                  오늘
                </Button>
              )}
            </div>
          </div>
        }
        placement="right"
        size={480}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        styles={{
          header: { background: '#141414', borderBottom: '1px solid #303030' },
          body: { background: '#0d0d0d', padding: 0 },
        }}
      >
        {logsLoading ? (
          <div style={{ textAlign: 'center', padding: 40 }}>
            <Spin size="small" />
            <div style={{ marginTop: 8 }}>
              <Text type="secondary" style={{ fontSize: 12 }}>로그 불러오는 중...</Text>
            </div>
          </div>
        ) : logs.length === 0 ? (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={
              <Text type="secondary">
                {isToday ? '로그가 아직 없습니다' : `${dayjs(selectedDate).format('YYYY년 M월 D일')} 로그가 없습니다`}
              </Text>
            }
            style={{ padding: 40 }}
          />
        ) : (
          <div style={{ fontFamily: "'JetBrains Mono', 'Fira Code', monospace", fontSize: 12, height: 'calc(100vh - 120px)', overflowY: 'auto' }}>
            <div
              style={{
                padding: '6px 12px',
                borderBottom: '1px solid #222',
                color: '#666',
                fontSize: 11,
              }}
            >
              {dayjs(selectedDate).format('YYYY년 M월 D일')} · {logs.length}건
              {isToday && ' · 실시간'}
            </div>
            {logs.map((log: SystemLog) => {
              const cfg = getLogConfig(log.level);
              return (
                <div
                  key={log.id}
                  style={{
                    padding: '6px 12px',
                    borderBottom: '1px solid #1a1a1a',
                    borderLeft: cfg.borderLeft,
                    background: cfg.rowBg,
                    display: 'flex',
                    gap: 8,
                    alignItems: 'flex-start',
                    lineHeight: 1.5,
                    contentVisibility: 'auto' as React.CSSProperties['contentVisibility'],
                    containIntrinsicSize: 'auto 36px',
                  }}
                >
                  <span style={{ flexShrink: 0, marginTop: 2 }}>{cfg.icon}</span>
                  <span style={{ color: '#555', flexShrink: 0 }}>
                    {dayjs(log.created_at).format('HH:mm:ss')}
                  </span>
                  <Tag
                    color={cfg.tagColor}
                    style={{ fontSize: 10, lineHeight: '16px', flexShrink: 0 }}
                  >
                    {log.level}
                  </Tag>
                  <span
                    style={{
                      color: cfg.textColor,
                      wordBreak: 'break-all',
                      fontWeight: log.level === 'CRITICAL' ? 600 : 400,
                    }}
                  >
                    {log.message}
                  </span>
                </div>
              );
            })}
          </div>
        )}
      </Drawer>
    </Layout>
  );
}
