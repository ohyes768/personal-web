/**
 * 资金流向图表组件
 * 使用 TradingView Lightweight Charts
 */
'use client';

import { useEffect, useRef } from 'react';
import { createChart, IChartApi, ISeriesApi, LineData, LineSeries } from 'lightweight-charts';
import type { ChartData, TimeRange } from '@/lib/modules/fund-flow/types';

interface FundFlowChartProps {
  data: ChartData[];
  timeRange: TimeRange;
}

// 根据时间范围过滤数据
function filterByTimeRange(data: ChartData[], range: TimeRange): ChartData[] {
  if (range === 'ALL') return data;

  // 使用数据中最后的时间作为基准，而不是当前时间
  if (data.length === 0) return data;

  const lastTime = data[data.length - 1].time * 1000; // 转换为毫秒
  const ranges: Record<TimeRange, number> = {
    '1M': 30 * 24 * 60 * 60 * 1000,   // 30天（毫秒）
    '3M': 90 * 24 * 60 * 60 * 1000,   // 90天
    '6M': 180 * 24 * 60 * 60 * 1000,  // 180天
    '1Y': 365 * 24 * 60 * 60 * 1000,  // 365天
    'ALL': Infinity,
  };

  const startTime = lastTime - ranges[range];
  return data.filter((item) => item.time * 1000 >= startTime);
}

export function FundFlowChart({ data, timeRange }: FundFlowChartProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesNorthRef = useRef<ISeriesApi<'Line'> | null>(null);
  const seriesSouthRef = useRef<ISeriesApi<'Line'> | null>(null);
  const seriesNetRef = useRef<ISeriesApi<'Line'> | null>(null);

  useEffect(() => {
    if (!chartContainerRef.current) return;

    // 创建图表
    const chart = createChart(chartContainerRef.current, {
      width: chartContainerRef.current.clientWidth,
      height: 500,
      layout: {
        background: { color: '#131722' },
        textColor: '#d1d4dc',
      },
      grid: {
        vertLines: { color: '#2a2e39' },
        horzLines: { color: '#2a2e39' },
      },
      crosshair: {
        mode: 1,
      },
      rightPriceScale: {
        borderColor: '#2a2e39',
      },
      timeScale: {
        borderColor: '#2a2e39',
        timeVisible: true,
        secondsVisible: false,
      },
    });

    chartRef.current = chart;

    // 创建北向资金曲线（绿色）
    const seriesNorth = chart.addSeries(LineSeries, {
      color: '#26a69a',
      lineWidth: 2,
      title: '北向',
    });
    seriesNorthRef.current = seriesNorth;

    // 创建南向资金曲线（红色）
    const seriesSouth = chart.addSeries(LineSeries, {
      color: '#ef5350',
      lineWidth: 2,
      title: '南向',
    });
    seriesSouthRef.current = seriesSouth;

    // 创建净流入曲线（蓝色）
    const seriesNet = chart.addSeries(LineSeries, {
      color: '#2962ff',
      lineWidth: 2,
      title: '净流入',
    });
    seriesNetRef.current = seriesNet;

    // 响应窗口大小变化
    const handleResize = () => {
      if (chartContainerRef.current) {
        chart.applyOptions({
          width: chartContainerRef.current.clientWidth,
        });
      }
    };

    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      chart.remove();
    };
  }, []);

  // 更新图表数据
  useEffect(() => {
    if (!chartRef.current || !seriesNorthRef.current || !seriesSouthRef.current || !seriesNetRef.current) {
      return;
    }

    const filteredData = filterByTimeRange(data, timeRange);

    // 转换为图表数据格式
    const northData: LineData[] = filteredData.map((item) => ({
      time: item.time as any,
      value: item.northNet,
    }));

    const southData: LineData[] = filteredData.map((item) => ({
      time: item.time as any,
      value: item.southNet,
    }));

    const netData: LineData[] = filteredData.map((item) => ({
      time: item.time as any,
      value: item.netFlow,
    }));

    seriesNorthRef.current.setData(northData);
    seriesSouthRef.current.setData(southData);
    seriesNetRef.current.setData(netData);

    // 调整时间范围到最新数据
    if (filteredData.length > 0) {
      chartRef.current.timeScale().fitContent();
    }
  }, [data, timeRange]);

  return (
    <div className="bg-[#131722] border border-[#2a2e39] rounded-lg overflow-hidden">
      <div ref={chartContainerRef} className="w-full" />
    </div>
  );
}