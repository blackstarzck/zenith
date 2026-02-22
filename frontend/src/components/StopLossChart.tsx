import { useEffect, useRef, useCallback } from 'react';
import {
  createChart,
  LineSeries,
  CrosshairMode,
  LineStyle,
  type IChartApi,
  type ISeriesApi,
  type LineData,
  type Time,
} from 'lightweight-charts';
import { Card, Typography, Empty, Spin } from 'antd';
import dayjs from 'dayjs';
import type { PriceSnapshot } from '../types/database';

const { Text } = Typography;

/* ── Helpers ───────────────────────────────────────────── */

function toUnix(iso: string): Time {
  return Math.floor(new Date(iso).getTime() / 1000) as Time;
}

/* ── Props ─────────────────────────────────────────────── */

interface Props {
  symbol?: string;
  data?: PriceSnapshot[];
  loading?: boolean;
}

/* ── Component ─────────────────────────────────────────── */

export default function StopLossChart({ symbol, data, loading }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const tooltipRef = useRef<HTMLDivElement>(null);
  const seriesRefs = useRef<{
    price: ISeriesApi<'Line'> | null;
    stopLoss: ISeriesApi<'Line'> | null;
    takeProfit: ISeriesApi<'Line'> | null;
  }>({ price: null, stopLoss: null, takeProfit: null });

  /* ── Create chart (lazy — only when container is visible) */
  const ensureChart = useCallback(() => {
    if (chartRef.current) return; // already created
    if (!containerRef.current) return;

    const chart = createChart(containerRef.current, {
      height: 280,
      autoSize: true,
      layout: {
        background: { type: 'solid' as const, color: '#141414' },
        textColor: 'rgba(255,255,255,0.5)',
        fontSize: 11,
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
        scaleMargins: { top: 0.08, bottom: 0.05 },
      },
      timeScale: {
        borderVisible: false,
        rightOffset: 3,
        barSpacing: 6,
        minBarSpacing: 2,
        timeVisible: true,
        secondsVisible: false,
      },
      handleScroll: { mouseWheel: true, pressedMouseMove: true, horzTouchDrag: true, vertTouchDrag: false },
      handleScale: { axisPressedMouseMove: true, mouseWheel: true, pinch: true },
    });

    // 현재가 (primary line)
    const priceSeries = chart.addSeries(LineSeries, {
      color: '#1668dc',
      lineWidth: 2,
      crosshairMarkerVisible: true,
      crosshairMarkerRadius: 3,
      crosshairMarkerBackgroundColor: '#1668dc',
      crosshairMarkerBorderColor: '#fff',
      crosshairMarkerBorderWidth: 1,
      priceFormat: { type: 'price', precision: 0, minMove: 1 },
    });

    // 손절선 (ATR) - 빨간 점선
    const stopLossSeries = chart.addSeries(LineSeries, {
      color: '#ff4d4f',
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      crosshairMarkerVisible: false,
      lastValueVisible: false,
      priceLineVisible: false,
      priceFormat: { type: 'price', precision: 0, minMove: 1 },
    });

    // 익절선 (BB Upper) - 초록 점선
    const takeProfitSeries = chart.addSeries(LineSeries, {
      color: '#52c41a',
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      crosshairMarkerVisible: false,
      lastValueVisible: false,
      priceLineVisible: false,
      priceFormat: { type: 'price', precision: 0, minMove: 1 },
    });

    /* ── Tooltip ──────────────────────────────────────────── */
    chart.subscribeCrosshairMove((param) => {
      const tooltip = tooltipRef.current;
      if (!tooltip) return;

      if (!param.point || !param.time || param.point.x < 0 || param.point.y < 0) {
        tooltip.style.display = 'none';
        return;
      }

      const priceData = param.seriesData.get(priceSeries) as LineData<Time> | undefined;
      const slData = param.seriesData.get(stopLossSeries) as LineData<Time> | undefined;
      const tpData = param.seriesData.get(takeProfitSeries) as LineData<Time> | undefined;

      if (!priceData) {
        tooltip.style.display = 'none';
        return;
      }

      const time = dayjs.unix(Number(param.time)).format('MM/DD HH:mm');
      const price = priceData.value;

      let html = `<div style="font-size:11px;color:rgba(255,255,255,0.5);margin-bottom:4px">${time}</div>`;
      html += `<div style="display:flex;align-items:center;gap:6px;margin-bottom:2px">`;
      html += `<span style="width:8px;height:2px;background:#1668dc;display:inline-block;border-radius:1px"></span>`;
      html += `<span style="font-size:13px;font-weight:600;color:#fff">현재가 ${price.toLocaleString()}</span>`;
      html += `</div>`;

      if (slData) {
        html += `<div style="display:flex;align-items:center;gap:6px;margin-bottom:2px">`;
        html += `<span style="width:8px;height:2px;background:#ff4d4f;display:inline-block;border-radius:1px;border-top:1px dashed #ff4d4f"></span>`;
        html += `<span style="font-size:12px;color:#ff4d4f">손절 ${slData.value.toLocaleString()}</span>`;
        html += `</div>`;
      }

      if (tpData) {
        html += `<div style="display:flex;align-items:center;gap:6px">`;
        html += `<span style="width:8px;height:2px;background:#52c41a;display:inline-block;border-radius:1px;border-top:1px dashed #52c41a"></span>`;
        html += `<span style="font-size:12px;color:#52c41a">익절 ${tpData.value.toLocaleString()}</span>`;
        html += `</div>`;
      }

      // PnL from stop-loss distance
      if (slData) {
        const diff = price - slData.value;
        const pct = ((diff / slData.value) * 100).toFixed(2);
        const diffColor = diff >= 0 ? '#52c41a' : '#ff4d4f';
        html += `<div style="font-size:11px;color:${diffColor};margin-top:4px;border-top:1px solid rgba(255,255,255,0.06);padding-top:4px">`;
        html += `손절까지 ${diff >= 0 ? '+' : ''}${diff.toLocaleString()} (${diff >= 0 ? '+' : ''}${pct}%)`;
        html += `</div>`;
      }

      tooltip.innerHTML = html;
      tooltip.style.display = 'block';

      const container = containerRef.current!;
      const cw = container.clientWidth;
      const tw = 180;
      let left = param.point.x + 16;
      if (left + tw > cw) left = param.point.x - tw - 16;
      if (left < 0) left = 4;
      let top = param.point.y - 20;
      if (top < 0) top = 4;

      tooltip.style.left = `${left}px`;
      tooltip.style.top = `${top}px`;
    });

    chartRef.current = chart;
    seriesRefs.current = { price: priceSeries, stopLoss: stopLossSeries, takeProfit: takeProfitSeries };
  }, []);

  /* ── Cleanup on unmount ──────────────────────────────── */
  useEffect(() => {
    return () => {
      if (chartRef.current) {
        chartRef.current.remove();
        chartRef.current = null;
        seriesRefs.current = { price: null, stopLoss: null, takeProfit: null };
      }
    };
  }, []);

  /* ── Create chart + set data when data arrives ────────── */
  useEffect(() => {
    if (!data || data.length === 0) return;

    // Lazily create chart on first data arrival (container is now visible)
    ensureChart();

    const { price, stopLoss, takeProfit } = seriesRefs.current;
    if (!price) return;

    const priceData: LineData<Time>[] = [];
    const slData: LineData<Time>[] = [];
    const tpData: LineData<Time>[] = [];

    for (const p of data) {
      const t = toUnix(p.created_at);
      priceData.push({ time: t, value: p.price });
      if (p.stop_loss != null) slData.push({ time: t, value: p.stop_loss });
      if (p.take_profit != null) tpData.push({ time: t, value: p.take_profit });
    }

    price.setData(priceData);
    if (stopLoss && slData.length > 0) stopLoss.setData(slData);
    if (takeProfit && tpData.length > 0) takeProfit.setData(tpData);

    chartRef.current?.timeScale().fitContent();
  }, [data, ensureChart]);

  /* ── Render ─────────────────────────────────────────── */
  const hasData = !loading && data && data.length > 0;

  if (loading) {
    return (
      <Card
        title={
          <span>
            가격 &amp; 손절선{' '}
            {symbol && (
              <Text type="secondary" style={{ fontSize: 13 }}>
                {symbol.replace('KRW-', '')}
              </Text>
            )}
          </span>
        }
        variant="borderless"
      >
        <div style={{ textAlign: 'center', padding: 40 }}>
          <Spin />
        </div>
      </Card>
    );
  }

  if (!hasData) {
    return (
      <Card
        title={
          <span>
            가격 &amp; 손절선{' '}
            {symbol && (
              <Text type="secondary" style={{ fontSize: 13 }}>
                {symbol.replace('KRW-', '')}
              </Text>
            )}
          </span>
        }
        variant="borderless"
      >
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description={
            <Text type="secondary">
              보유 종목이 있을 때 가격 · 손절선 데이터가 자동으로 기록됩니다
            </Text>
          }
          style={{ padding: 40 }}
        />
      </Card>
    );
  }

  return (
    <Card
      title={
        <span>
          가격 &amp; 손절선{' '}
          {symbol && (
            <Text type="secondary" style={{ fontSize: 13 }}>
              {symbol.replace('KRW-', '')}
            </Text>
          )}
        </span>
      }
      variant="borderless"
    >
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
            minWidth: 160,
            lineHeight: 1.5,
          }}
        />
      </div>
    </Card>
  );
}
