/**
 * 详情弹框组件
 * 共享组件，支持三种详情类型：季度详情、板块/行业、年度详情
 */
'use client';

import { Modal } from './shared-ui/Modal';
import { Button } from './shared-ui/Button';
import { useState, useEffect, useCallback, useMemo } from 'react';
import { dividendApi } from '@/lib/api';
import {
  ComposedChart,
  Bar,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';
import type { DividendStock, BoardInfo, BoardInfoResponse } from '@/lib/types';

export interface DetailModalProps {
  isOpen: boolean;
  onClose: () => void;
  type: 'quarterly' | 'sector' | 'yearly' | 'volatility' | null;
  stock: DividendStock | null;
}

const formatValue = (value: number | null | undefined): string => {
  if (value === null || value === undefined) return '-';
  return value.toFixed(2);
};

// 缓存相关配置
const CACHE_KEY_PREFIX = 'dividend-board-info-';
const CACHE_DURATION = 24 * 60 * 60 * 1000; // 1天（毫秒）

export function DetailModal({ isOpen, onClose, type, stock }: DetailModalProps) {
  const [stockInfo, setBoardInfo] = useState<BoardInfo | null>(null);
  const [stockDetail, setStockDetail] = useState<DividendStock | null>(null);
  const [loading, setLoading] = useState(false);

  // 从 localStorage 读取缓存
  const getCache = useCallback((code: string): BoardInfo | null => {
    try {
      const cached = localStorage.getItem(`${CACHE_KEY_PREFIX}${code}`);
      if (!cached) return null;

      const data: BoardInfo & { timestamp: number } = JSON.parse(cached);
      const now = Date.now();

      // 检查缓存是否过期
      if (now - data.timestamp > CACHE_DURATION) {
        localStorage.removeItem(`${CACHE_KEY_PREFIX}${code}`);
        return null;
      }

      const { timestamp, ...info } = data;
      return info;
    } catch {
      return null;
    }
  }, []);

  // 保存到 localStorage
  const setCache = useCallback((info: BoardInfo) => {
    try {
      const data = { ...info, timestamp: Date.now() };
      localStorage.setItem(`${CACHE_KEY_PREFIX}${info.code}`, JSON.stringify(data));
    } catch (err) {
      console.error('Failed to save cache:', err);
    }
  }, []);

  // 获取股票信息
  useEffect(() => {
    if (!isOpen || !stock || type !== 'sector') {
      return;
    }

    // 先检查缓存
    const cached = getCache(stock.code);
    if (cached) {
      setBoardInfo(cached);
      return;
    }

    // 从 API 获取
    setLoading(true);
    dividendApi.getBoardInfo({ code: stock.code })
      .then((response: BoardInfoResponse) => {
        if (response.items.length > 0) {
          const info = response.items[0];
          setBoardInfo(info);
          setCache(info);
        }
      })
      .catch((err: unknown) => {
        console.error('Failed to fetch stock info:', err);
      })
      .finally(() => {
        setLoading(false);
      });
  }, [isOpen, stock, type, getCache, setCache]);

  // 获取股票详情（分红历史）
  useEffect(() => {
    if (!isOpen || !stock || type !== 'quarterly') {
      setStockDetail(null);
      return;
    }

    setLoading(true);
    dividendApi.getStockDetail(stock.code)
      .then((response) => {
        setStockDetail(response.data);
      })
      .catch((err: unknown) => {
        console.error('Failed to fetch stock detail:', err);
      })
      .finally(() => {
        setLoading(false);
      });
  }, [isOpen, stock, type]);

  if (!stock || !type) return null;

  const getModalTitle = () => {
    const titles = {
      quarterly: '季度股息率详情',
      sector: '板块',
      yearly: '年度详情',
      volatility: '价格波动详情',
    };
    return `${stock.name} (${stock.code}) - ${titles[type]}`;
  };

  const renderQuarterlyContent = () => {
    const history = stockDetail?.dividend_history ?? stock?.dividend_history ?? null;

    if (loading) {
      return <div className="flex items-center justify-center py-8 text-gray-400">加载中...</div>;
    }

    if (!history || history.length === 0) {
      return <div className="flex items-center justify-center py-8 text-gray-400">暂无分红数据</div>;
    }

    // 按除权除息日期升序排列（ oldest first for chart )
    const sortedHistory = [...history].sort(
      (a, b) => new Date(a.ex_date).getTime() - new Date(b.ex_date).getTime()
    );

    // 生成固定36个月的时间序列 (2023年1月 ~ 2025年12月)
    const months: string[] = [];
    for (let i = 35; i >= 0; i--) {
      const d = new Date(2025, 11 - i, 1); // 固定2023-01到2025-12
      months.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`);
    }

    // 只保留2023年及以后的分红数据
    const recentHistory = sortedHistory.filter(
      (item) => new Date(item.ex_date).getTime() >= new Date('2023-01-01').getTime()
    );

    // 构建月份到股息数据的映射
    const dividendByMonth: Record<string, number> = {};
    recentHistory.forEach((item) => {
      const monthKey = item.ex_date.slice(0, 7); // YYYY-MM
      dividendByMonth[monthKey] = item.ratio;
    });

    // 获取近4年每年股息率 (2022-2025)
    const getYearlyYield = (year: number): number | null => {
      const key = `yield_${year}` as keyof DividendStock;
      return stock?.[key] as number | null;
    };

    // chart data - 36个月的固定序列，年度股息率作为折线
    const chartData = months.map((month) => {
      const year = parseInt(month.slice(0, 4));
      const monthlyYield = getYearlyYield(year);
      return {
        month,
        ratio: dividendByMonth[month] || 0,
        yearlyYield: monthlyYield ?? null,
      };
    });

    // 最近的5条记录用于展示（过滤掉2022年财年的记录）
    const recentItems = recentHistory.filter(item => item.fiscal_year >= 2023).slice(-5).reverse();

    return (
      <div className="space-y-6">
        {/* 柱状+折线组合图 */}
        <div className="bg-gray-800/50 rounded-lg p-4">
          <h3 className="text-sm font-semibold text-gray-200 mb-3">分红派息趋势</h3>
          <ResponsiveContainer width="100%" height={200}>
            <ComposedChart data={chartData} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#E8E3D8" />
              <XAxis
                dataKey="month"
                tick={{ fill: '#6B6864', fontSize: 10, textAnchor: 'end' }}
                tickFormatter={(val) => val.replace('-', '.')} // YYYY.MM
                angle={-45}
                height={60}
                interval={2}
              />
              <YAxis
                yAxisId="left"
                tick={{ fill: '#6B6864', fontSize: 11 }}
                tickFormatter={(val) => `${val}元`}
              />
              <YAxis
                yAxisId="right"
                orientation="right"
                tick={{ fill: '#6B6864', fontSize: 11 }}
                tickFormatter={(val) => `${val}%`}
              />
              <Tooltip
                contentStyle={{ backgroundColor: '#FFFFFF', border: '1px solid #E8E3D8', borderRadius: '6px' }}
                labelStyle={{ color: '#1F1E1B' }}
                formatter={(value, name) => {
                  if (name === '每股派息') {
                    return [`${value} 元/股`, '每股派息'];
                  }
                  return [`${value}%`, '年度股息率'];
                }}
                labelFormatter={(label) => `月份: ${label}`}
              />
              <Legend />
              <Bar dataKey="ratio" name="每股派息" yAxisId="left" fill="#C9951F" radius={[2, 2, 0, 0]} />
              <Line type="stepAfter" dataKey="yearlyYield" name="年度股息率" yAxisId="right" stroke="#3F7D58" strokeWidth={2} dot={{ fill: '#3F7D58', r: 2 }} connectNulls={false} />
            </ComposedChart>
          </ResponsiveContainer>
        </div>

        {/* 明细表格 */}
        <div className="bg-gray-800/50 rounded-lg p-4">
          <h3 className="text-sm font-semibold text-gray-200 mb-3">分红明细</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-700">
                  <th className="text-left py-2 text-gray-400 font-medium">除权除息日</th>
                  <th className="text-left py-2 text-gray-400 font-medium">财年</th>
                  <th className="text-right py-2 text-gray-400 font-medium">派息 (元/股)</th>
                  <th className="text-right py-2 text-gray-400 font-medium">单次股息率</th>
                  <th className="text-right py-2 text-gray-400 font-medium">年度股息率</th>
                </tr>
              </thead>
              <tbody>
                {recentItems.map((item, idx) => {
                  // 用财年获取平均价和年度股息率（2022年数据不全，跳过年度股息率）
                  const fiscalYear = item.fiscal_year;
                  const avgPriceKey = `avg_price_${fiscalYear}` as keyof DividendStock;
                  const yieldKey = `yield_${fiscalYear}` as keyof DividendStock;
                  const avgPrice = stock?.[avgPriceKey] as number | null;
                  const yearlyYield = fiscalYear >= 2023 ? (stock?.[yieldKey] as number | null) : null;
                  const singleYield = avgPrice ? ((item.ratio / avgPrice) * 100).toFixed(2) : null;
                  return (
                    <tr key={idx} className="border-b border-gray-700/50 hover:bg-gray-700/20">
                      <td className="py-2 text-gray-300">{item.ex_date}</td>
                      <td className="py-2 text-gray-300">{item.fiscal_year}年</td>
                      <td className="py-2 text-right text-amber-400 font-semibold">{item.ratio}</td>
                      <td className="py-2 text-right text-green-400">{singleYield !== null ? `${singleYield}%` : '-'}</td>
                      <td className="py-2 text-right text-blue-400">{yearlyYield !== null ? `${yearlyYield.toFixed(2)}%` : '-'}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    );
  };

  const renderSectorContent = () => {
    // 概念板块和行业板块从 stockInfo 获取（点击板块时才获取）
    const conceptBoards = stockInfo?.concept_board
      ? stockInfo.concept_board.split(/[,;]+/).map((b) => b.trim()).filter(Boolean)
      : [];
    const industryBoards = stockInfo?.industry_board
      ? stockInfo.industry_board.split(/[,;]+/).map((b) => b.trim()).filter(Boolean)
      : [];

    return (
      <div className="space-y-6">
        {/* 概念板块 */}
        {loading && (
          <div className="flex items-center justify-center py-4">
            <div className="text-gray-400 text-sm">加载板块信息...</div>
          </div>
        )}

        {!loading && conceptBoards.length > 0 && (
          <div>
            <h3 className="text-base font-semibold text-gray-200 mb-3">概念板块</h3>
            <div className="flex flex-wrap gap-2">
              {conceptBoards.map((board, index) => (
                <span
                  key={index}
                  className="px-3 py-1.5 bg-blue-900/30 border border-blue-700 text-blue-300 rounded-full text-sm"
                >
                  {board}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* 行业板块 */}
        {!loading && industryBoards.length > 0 && (
          <div>
            <h3 className="text-base font-semibold text-gray-200 mb-3">行业板块</h3>
            <div className="flex flex-wrap gap-2">
              {industryBoards.map((board, index) => (
                <span
                  key={index}
                  className="px-3 py-1.5 bg-green-900/30 border border-green-700 text-green-300 rounded-full text-sm"
                >
                  {board}
                </span>
              ))}
            </div>
          </div>
        )}

        {!loading && conceptBoards.length === 0 && industryBoards.length === 0 && (
          <p className="text-sm text-gray-400">暂无板块信息</p>
        )}
      </div>
    );
  };

  const renderYearlyContent = () => {
    const years = [
      {
        name: '2025',
        dividend: stock.dividend_2025,
        count: stock.dividend_count_2025,
        yield: stock.yield_2025,
        avgPrice: stock.avg_price_2025,
      },
      {
        name: '2024',
        dividend: stock.dividend_2024,
        count: stock.dividend_count_2024,
        yield: stock.yield_2024,
        avgPrice: stock.avg_price_2024,
      },
      {
        name: '2023',
        dividend: stock.dividend_2023,
        count: stock.dividend_count_2023,
        yield: stock.yield_2023,
        avgPrice: stock.avg_price_2023,
      },
    ];

    return (
      <div className="grid grid-cols-3 gap-3">
        {years.map((y) => (
          <div
            key={y.name}
            className="bg-gray-800 border border-gray-700 rounded-lg p-4 text-center"
          >
            <div className="text-sm font-semibold text-gray-200 mb-3">{y.name}年</div>
            <div className="space-y-2">
              <div>
                <div className="text-xs text-gray-400 mb-1">平均价</div>
                <div className="text-base font-semibold text-gray-100">
                  {y.avgPrice ? `¥${formatValue(y.avgPrice)}` : '-'}
                </div>
              </div>
              <div>
                <div className="text-xs text-gray-400 mb-1">分红金额</div>
                <div className="text-base font-semibold text-gray-100">
                  {y.dividend ? `¥${formatValue(y.dividend)}` : '-'}
                </div>
              </div>
              <div>
                <div className="text-xs text-gray-400 mb-1">分红次数</div>
                <div className="text-base font-semibold text-gray-100">
                  {y.count ?? '-'}
                </div>
              </div>
              <div>
                <div className="text-xs text-gray-400 mb-1">股息率</div>
                <div className="text-base font-semibold text-green-400">
                  {y.yield ? `${formatValue(y.yield)}%` : '-'}
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>
    );
  };

  const renderVolatilityContent = () => {
    const priceCards = [
      { label: '2025最高价', value: stock.high_price_2025 },
      { label: '2025最低价', value: stock.low_price_2025 },
      { label: '2025平均价', value: stock.avg_price_2025 },
      { label: '近3年平均价', value: stock.avg_price_3y },
    ];

    const changeCards = [
      { label: '最高涨幅', value: stock.high_change_pct_2025, isPositive: true },
      { label: '最高跌幅', value: stock.low_change_pct_2025, isPositive: false },
    ];

    return (
      <div className="space-y-6">
        {/* 价格卡片 */}
        <div>
          <h3 className="text-base font-semibold text-gray-200 mb-3">价格信息</h3>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {priceCards.map((card) => (
              <div key={card.label} className="bg-gray-800 border border-gray-700 rounded-lg p-4 text-center">
                <div className="text-sm text-gray-400 mb-1">{card.label}</div>
                <div className="text-lg font-semibold text-gray-100">
                  {card.value !== null && card.value !== undefined ? `¥${formatValue(card.value)}` : '-'}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* 涨跌幅卡片 */}
        <div>
          <h3 className="text-base font-semibold text-gray-200 mb-3">波动幅度</h3>
          <div className="grid grid-cols-2 gap-3">
            {changeCards.map((card) => (
              <div
                key={card.label}
                className={`rounded-lg p-4 text-center border ${
                  card.isPositive
                    ? 'bg-green-900/20 border-green-800'
                    : 'bg-red-900/20 border-red-800'
                }`}
              >
                <div className="text-sm text-gray-400 mb-1">{card.label}</div>
                <div
                  className={`text-lg font-semibold ${
                    card.isPositive
                      ? 'text-green-400'
                      : 'text-red-400'
                  }`}
                >
                  {card.value !== null && card.value !== undefined
                    ? `${formatValue(card.isPositive ? card.value : -card.value)}%`
                    : '-'}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  };

  const renderContent = () => {
    switch (type) {
      case 'quarterly':
        return renderQuarterlyContent();
      case 'sector':
        return renderSectorContent();
      case 'yearly':
        return renderYearlyContent();
      case 'volatility':
        return renderVolatilityContent();
      default:
        return null;
    }
  };

  // 根据类型选择合适的尺寸
  const getModalSize = () => {
    switch (type) {
      case 'yearly':
      case 'quarterly':
        return 'xs';
      case 'volatility':
        return 'xs';
      default:
        return 'sm';
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={getModalTitle()}
      size="md"
      className={(type === 'yearly' || type === 'quarterly' || type === 'volatility' || type === 'sector') ? (type === 'quarterly' ? '!max-w-[700px]' : '!max-w-[600px]') : ''}
    >
      {renderContent()}
    </Modal>
  );
}
