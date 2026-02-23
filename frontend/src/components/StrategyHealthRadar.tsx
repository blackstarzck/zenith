import { memo } from 'react';
import { Radar } from '@ant-design/charts';
import { Card, Typography } from 'antd';

const { Text } = Typography;

interface StrategyHealthData {
  rsi: number;         // 0-100
  bbPosition: number;  // 0-100 (0=lower, 50=middle, 100=upper)
  volatility: number;  // 0-100 (normalized volatility ratio)
  volume: number;      // 0-100 (relative volume strength)
  momentum: number;    // 0-100 (RSI slope normalized)
}

interface Props {
  data?: StrategyHealthData;
}

const defaultData: StrategyHealthData = {
  rsi: 45,
  bbPosition: 55,
  volatility: 30,
  volume: 60,
  momentum: 50,
};

export default memo(function StrategyHealthRadar({ data = defaultData }: Props) {
  const chartData = [
    { indicator: 'RSI', value: data.rsi },
    { indicator: 'BB 위치', value: data.bbPosition },
    { indicator: '변동성', value: data.volatility },
    { indicator: '거래량', value: data.volume },
    { indicator: '모멘텀', value: data.momentum },
  ];

  const config = {
    data: chartData,
    xField: 'indicator',
    yField: 'value',
    height: 260,
    theme: 'classicDark',
    meta: {
      value: {
        min: 0,
        max: 100,
      },
    },
    area: {
      style: {
        fill: 'rgba(22, 104, 220, 0.25)',
      },
    },
    line: {
      style: {
        stroke: '#1668dc',
        lineWidth: 2,
      },
    },
    point: {
      style: {
        fill: '#1668dc',
        r: 3,
      },
    },
    xAxis: {
      label: {
        style: {
          fill: '#999',
          fontSize: 12,
        },
      },
      line: null,
      grid: {
        line: {
          style: {
            stroke: '#303030',
          },
        },
      },
    },
    yAxis: {
      label: null,
      grid: {
        line: {
          style: {
            stroke: '#303030',
          },
        },
        alternateColor: ['rgba(255,255,255,0.02)', 'transparent'],
      },
    },
  };

  const getHealthStatus = () => {
    const avg = (data.rsi + data.bbPosition + data.volume + data.momentum) / 4;
    const volPenalty = data.volatility > 70 ? -20 : 0;
    const score = avg + volPenalty;

    if (score >= 60) return { label: '양호', color: '#52c41a' };
    if (score >= 40) return { label: '보통', color: '#faad14' };
    return { label: '주의', color: '#ff4d4f' };
  };

  const status = getHealthStatus();

  return (
    <Card
      title="전략 적합도"
      variant="borderless"
      extra={
        <Text style={{ color: status.color, fontWeight: 600 }}>
          {status.label}
        </Text>
      }
    >
      <Radar {...config} />
    </Card>
  );
});
