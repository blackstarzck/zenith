import { useEffect, useRef, useCallback } from 'react';
import {
  createChart,
  AreaSeries,
  CrosshairMode,
  type IChartApi,
  type ISeriesApi,
  type AreaData,
  type Time,
} from 'lightweight-charts';
import dayjs from 'dayjs';

/* ── Types ─────────────────────────────────────────────── */

export interface AssetDataPoint {
  date: string;       // 'YYYY-MM-DD' or ISO 8601
  balance: number;
  netProfit?: number;  // optional PnL info for tooltip
}

/** DashboardPage의 chartRange 값과 동일 */
export type ChartRange = '1h' | '1d' | 7 | 30;

interface Props {
  data: AssetDataPoint[];
  height?: number;
  chartRange?: ChartRange;
}

/* ── Helpers ───────────────────────────────────────────── */

/** 모든 날짜를 unix seconds로 통일 */
function toChartTime(dateStr: string): Time {
  return Math.floor(new Date(dateStr).getTime() / 1000) as Time;
}

function formatKRW(v: number): string {
  if (v >= 1_0000_0000) return `${(v / 1_0000_0000).toFixed(2)}억`;
  if (v >= 1_0000) {
    const man = Math.floor(v / 1_0000);
    const chun = Math.floor((v % 1_0000) / 1000);
    if (chun > 0) return `${man}만 ${chun}천`;
    return `${man}만`;
  }
  return Math.round(v).toLocaleString();
}
/** 기간별 x축 tick 포맷 */
function formatTick(time: Time, range: ChartRange): string {
  const d = dayjs.unix(Number(time));
  switch (range) {
    case '1h':
      // 00:00 / 01:00 / 02:00 ...
      return d.format('HH:mm');
    case '1d':
      // 1, 2, 3 ... 30, 31 (일)
      return String(d.date());
    case 7:
      // 1월 1주 / 2주 / 3주 ...
      return `${d.month() + 1}월 ${Math.ceil(d.date() / 7)}주`;
    case 30:
    default:
      // 1월, 2월, 3월 ... (월별)
      return `${d.month() + 1}월`;
  }
}

/** 기간별 tooltip 날짜 포맷 */
function formatTooltipDate(time: number, range: ChartRange): string {
  const d = dayjs.unix(time);
  switch (range) {
    case '1h':
      return d.format('MM/DD HH:mm');
    case '1d':
      return d.format('M월 D일 HH:mm');
    case 7:
      return `${d.month() + 1}월 ${Math.ceil(d.date() / 7)}주 (${d.format('MM/DD')})`;
    case 30:
    default:
      return d.format('YYYY-MM-DD');
  }
}

/* ── Component ─────────────────────────────────────────── */

export default function AssetGrowthChart({ data, height = 340, chartRange = 30 }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<'Area'> | null>(null);
  const tooltipRef = useRef<HTMLDivElement>(null);

  /* ── Create chart ──────────────────────────────────────── */
  const initChart = useCallback(() => {
    if (!containerRef.current) return;

    const chart = createChart(containerRef.current, {
      height,
      autoSize: true,
      layout: {
        background: { type: 'solid' as const, color: '#141414' },
        textColor: 'rgba(255,255,255,0.5)',
        fontSize: 12,
      },
      grid: {
        vertLines: { color: 'rgba(255,255,255,0.04)' },
        horzLines: { color: 'rgba(255,255,255,0.04)' },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: {
          width: 1,
          color: 'rgba(255,255,255,0.15)',
          labelBackgroundColor: '#1668dc',
        },
        horzLine: {
          color: 'rgba(255,255,255,0.15)',
          labelBackgroundColor: '#1668dc',
        },
      },
      rightPriceScale: {
        borderVisible: false,
        scaleMargins: { top: 0.1, bottom: 0.05 },
      },
      timeScale: {
        borderVisible: false,
        rightOffset: 5,
        barSpacing: 8,
        minBarSpacing: 2,
        timeVisible: true,
        secondsVisible: false,
        tickMarkFormatter: (time: Time) => formatTick(time, chartRange),
      },
      handleScroll: { mouseWheel: true, pressedMouseMove: true, horzTouchDrag: true, vertTouchDrag: false },
      handleScale: { axisPressedMouseMove: true, mouseWheel: true, pinch: true },
    });

    const series = chart.addSeries(AreaSeries, {
      lineColor: '#1668dc',
      lineWidth: 2,
      topColor: 'rgba(22,104,220,0.35)',
      bottomColor: 'rgba(22,104,220,0.02)',
      crosshairMarkerVisible: true,
      crosshairMarkerRadius: 4,
      crosshairMarkerBackgroundColor: '#1668dc',
      crosshairMarkerBorderColor: '#fff',
      crosshairMarkerBorderWidth: 2,
      priceFormat: { type: 'custom', formatter: (price: number) => formatKRW(price) },
    });

    /* ── Tooltip ──────────────────────────────────────────── */
    chart.subscribeCrosshairMove((param) => {
      const tooltip = tooltipRef.current;
      if (!tooltip) return;

      if (!param.point || !param.time || param.point.x < 0 || param.point.y < 0) {
        tooltip.style.display = 'none';
        return;
      }

      const d = param.seriesData.get(series) as AreaData<Time> | undefined;
      if (!d) {
        tooltip.style.display = 'none';
        return;
      }

      const balance = d.value;

      // Find matching source data for netProfit
      const timeVal = Number(param.time);
      const srcPoint = data.find((p) => {
        const ct = Number(toChartTime(p.date));
        return ct === timeVal;
      });

      const dateStr = formatTooltipDate(timeVal, chartRange);

      let html = `<div style="font-size:11px;color:rgba(255,255,255,0.5);margin-bottom:4px">${dateStr}</div>`;
      html += `<div style="font-size:15px;font-weight:600;color:#fff">${formatKRW(balance)} 원</div>`;

      if (srcPoint?.netProfit !== undefined) {
        const pnl = srcPoint.netProfit;
        const pnlColor = pnl >= 0 ? '#52c41a' : '#ff4d4f';
        const pnlSign = pnl >= 0 ? '+' : '';
        html += `<div style="font-size:12px;color:${pnlColor};margin-top:2px">당일 손익 ${pnlSign}${formatKRW(pnl)}</div>`;
      }

      tooltip.innerHTML = html;
      tooltip.style.display = 'block';

      // Position tooltip
      const container = containerRef.current!;
      const cw = container.clientWidth;
      const tw = 170;
      let left = param.point.x + 16;
      if (left + tw > cw) left = param.point.x - tw - 16;
      if (left < 0) left = 4;
      let top = param.point.y - 20;
      if (top < 0) top = 4;

      tooltip.style.left = `${left}px`;
      tooltip.style.top = `${top}px`;
    });

    chartRef.current = chart;
    seriesRef.current = series;
  }, [height, chartRange]); // eslint-disable-line react-hooks/exhaustive-deps

  /* ── Init / cleanup ──────────────────────────────────── */
  useEffect(() => {
    initChart();
    return () => {
      if (chartRef.current) {
        chartRef.current.remove();
        chartRef.current = null;
        seriesRef.current = null;
      }
    };
  }, [initChart]);

  /* ── Update data ─────────────────────────────────────── */
  useEffect(() => {
    if (!seriesRef.current || data.length === 0) return;

    const chartData = data.map((d) => ({
      time: toChartTime(d.date),
      value: d.balance,
    }));

    seriesRef.current.setData(chartData);
    const timeScale = chartRef.current?.timeScale();

    // 1시간 뷰: 고정 범위 설정하여 정기적인 시간 tick 표시
    if (chartRange === '1h' && data.length > 0) {
      const now = dayjs();
      const oneHourAgo = now.subtract(1, 'hour');
      timeScale?.setVisibleRange({
        from: oneHourAgo.unix() as Time,
        to: now.unix() as Time,
      });
    } else {
      timeScale?.fitContent();
    }
  }, [data, chartRange]);

  return (
    <div ref={containerRef} style={{ position: 'relative', width: '100%' }}>
      <div
        ref={tooltipRef}
        style={{
          display: 'none',
          position: 'absolute',
          zIndex: 10,
          pointerEvents: 'none',
          padding: '8px 12px',
          borderRadius: 6,
          background: 'rgba(20,20,20,0.92)',
          border: '1px solid rgba(255,255,255,0.08)',
          backdropFilter: 'blur(8px)',
          minWidth: 150,
          lineHeight: 1.5,
        }}
      />
    </div>
  );
}
