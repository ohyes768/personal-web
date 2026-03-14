/**
 * 详情弹框组件
 * 共享组件，支持三种详情类型：季度详情、板块/行业、年度详情
 */
'use client';

import { Modal } from '@/components/ui/Modal';
import { Button } from '@/components/ui/Button';
import { useState, useEffect, useCallback } from 'react';
import { dividendApi } from '@/lib/modules/dividend/api';
import type { DividendStock, StockInfo } from '@/lib/modules/dividend/types';

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
const CACHE_KEY_PREFIX = 'dividend-stock-info-';
const CACHE_DURATION = 24 * 60 * 60 * 1000; // 1天（毫秒）

export function DetailModal({ isOpen, onClose, type, stock }: DetailModalProps) {
  const [stockInfo, setStockInfo] = useState<StockInfo | null>(null);
  const [loading, setLoading] = useState(false);

  // 从 localStorage 读取缓存
  const getCache = useCallback((code: string): StockInfo | null => {
    try {
      const cached = localStorage.getItem(`${CACHE_KEY_PREFIX}${code}`);
      if (!cached) return null;

      const data: StockInfo & { timestamp: number } = JSON.parse(cached);
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
  const setCache = useCallback((info: StockInfo) => {
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
      setStockInfo(cached);
      return;
    }

    // 从 API 获取
    setLoading(true);
    dividendApi.getStocksInfo({ codes: [stock.code] })
      .then(response => {
        if (response.items.length > 0) {
          const info = response.items[0];
          setStockInfo(info);
          setCache(info);
        }
      })
      .catch(err => {
        console.error('Failed to fetch stock info:', err);
      })
      .finally(() => {
        setLoading(false);
      });
  }, [isOpen, stock, type, getCache, setCache]);

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
    const quarters = [
      { name: '2025 Q4', data: stock.quarterly?.q4 },
      { name: '2025 Q3', data: stock.quarterly?.q3 },
      { name: '2025 Q2', data: stock.quarterly?.q2 },
      { name: '2025 Q1', data: stock.quarterly?.q1 },
    ];

    const rows = [
      { key: 'avg_price', label: '平均股价', format: (v: number | null | undefined) => v ? `¥${formatValue(v)}` : '-' },
      { key: 'dividend', label: '分红金额', format: (v: number | null | undefined) => v ? `¥${formatValue(v)}` : '-' },
      { key: 'yield_pct', label: '股息率', format: (v: number | null | undefined) => v ? `${formatValue(v)}%` : '-' },
    ];

    return (
      <table className="w-full">
        <thead>
          <tr className="border-b border-gray-200 dark:border-gray-700">
            <th className="px-4 py-3 text-left text-sm font-semibold text-gray-700 dark:text-gray-300">指标</th>
            {quarters.map((q) => (
              <th key={q.name} className="px-4 py-3 text-center text-sm font-semibold text-gray-700 dark:text-gray-300">
                {q.name}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.key} className="border-b border-gray-100 dark:border-gray-800">
              <td className="px-4 py-3 text-base font-medium text-gray-900 dark:text-gray-100">{row.label}</td>
              {quarters.map((q) => (
                <td key={q.name} className="px-4 py-3 text-base text-center text-gray-700 dark:text-gray-300">
                  {q.data ? row.format(q.data[row.key as keyof typeof q.data]) : '-'}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
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
            <div className="text-gray-600 dark:text-gray-400 text-sm">加载板块信息...</div>
          </div>
        )}

        {!loading && conceptBoards.length > 0 && (
          <div>
            <h3 className="text-base font-semibold text-gray-700 dark:text-gray-300 mb-3">概念板块</h3>
            <div className="flex flex-wrap gap-2">
              {conceptBoards.map((board, index) => (
                <span
                  key={index}
                  className="px-3 py-1.5 bg-blue-100 dark:bg-blue-900/40 text-blue-800 dark:text-blue-200 rounded-full text-sm"
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
            <h3 className="text-base font-semibold text-gray-700 dark:text-gray-300 mb-3">行业板块</h3>
            <div className="flex flex-wrap gap-2">
              {industryBoards.map((board, index) => (
                <span
                  key={index}
                  className="px-3 py-1.5 bg-green-100 dark:bg-green-900/40 text-green-800 dark:text-green-200 rounded-full text-sm"
                >
                  {board}
                </span>
              ))}
            </div>
          </div>
        )}

        {!loading && conceptBoards.length === 0 && industryBoards.length === 0 && (
          <p className="text-sm text-gray-600 dark:text-gray-400">暂无板块信息</p>
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

    const rows = [
      { key: 'avgPrice', label: '平均价', format: (v: typeof years[0]) => v.avgPrice ? `¥${formatValue(v.avgPrice)}` : '-' },
      { key: 'dividend', label: '分红金额', format: (v: typeof years[0]) => v.dividend ? `¥${formatValue(v.dividend)}` : '-' },
      { key: 'count', label: '次数', format: (v: typeof years[0]) => v.count ?? '-' },
      { key: 'yield', label: '股息率', format: (v: typeof years[0]) => v.yield ? `${formatValue(v.yield)}%` : '-' },
    ];

    return (
      <table className="w-full">
        <thead>
          <tr className="border-b border-gray-200 dark:border-gray-700">
            <th className="px-4 py-3 text-left text-sm font-semibold text-gray-700 dark:text-gray-300">指标</th>
            {years.map((y) => (
              <th key={y.name} className="px-4 py-3 text-center text-sm font-semibold text-gray-700 dark:text-gray-300">
                {y.name}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.key} className="border-b border-gray-100 dark:border-gray-800">
              <td className="px-4 py-3 text-base font-medium text-gray-900 dark:text-gray-100">{row.label}</td>
              {years.map((y) => (
                <td key={y.name} className="px-4 py-3 text-base text-center text-gray-700 dark:text-gray-300">
                  {row.format(y)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
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
          <h3 className="text-base font-semibold text-gray-700 dark:text-gray-300 mb-3">价格信息</h3>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {priceCards.map((card) => (
              <div key={card.label} className="bg-gray-100 dark:bg-gray-800 rounded-lg p-4 text-center">
                <div className="text-sm text-gray-600 dark:text-gray-400 mb-1">{card.label}</div>
                <div className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                  {card.value !== null && card.value !== undefined ? `¥${formatValue(card.value)}` : '-'}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* 涨跌幅卡片 */}
        <div>
          <h3 className="text-base font-semibold text-gray-700 dark:text-gray-300 mb-3">波动幅度</h3>
          <div className="grid grid-cols-2 gap-3">
            {changeCards.map((card) => (
              <div
                key={card.label}
                className={`rounded-lg p-4 text-center ${
                  card.isPositive
                    ? 'bg-green-100 dark:bg-green-900/30'
                    : 'bg-red-100 dark:bg-red-900/30'
                }`}
              >
                <div className="text-sm text-gray-600 dark:text-gray-400 mb-1">{card.label}</div>
                <div
                  className={`text-lg font-semibold ${
                    card.isPositive
                      ? 'text-green-700 dark:text-green-400'
                      : 'text-red-700 dark:text-red-400'
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

  return (
    <Modal isOpen={isOpen} onClose={onClose} title={getModalTitle()}>
      {renderContent()}
    </Modal>
  );
}