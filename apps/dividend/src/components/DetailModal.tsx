/**
 * 详情弹框组件
 * 共享组件，支持三种详情类型：季度详情、板块/行业、年度详情
 */
'use client';

import { Modal } from '@personal-web/shared-ui';
import { Button } from '@personal-web/shared-ui';
import { useState, useEffect, useCallback, useMemo } from 'react';
import { dividendApi } from '@/lib/api';
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
    // 动态计算前4个已过去季度，最新在前
    const now = new Date();
    const year = now.getFullYear();
    const month = now.getMonth() + 1;
    const currentQuarter = Math.ceil(month / 3);

    interface QuarterData {
      name: string;
      data: { avg_price?: number | null; dividend?: number | null; yield_pct?: number | null } | null;
    }
    const quarters: QuarterData[] = [];
    // 从上一个完整季度开始往前数4个
    let q = currentQuarter - 1;
    let y = year;
    if (q === 0) { q = 4; y--; }
    for (let i = 0; i < 4; i++) {
      const key = ['q1', 'q2', 'q3', 'q4'][i];
      quarters.push({
        name: `${y} Q${q}`,
        data: stock.quarterly?.[key as keyof typeof stock.quarterly] ?? null,
      });
      q--;
      if (q === 0) { q = 4; y--; }
    }

    return (
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {quarters.map((q) => (
          <div
            key={q.name}
            className="bg-gray-800 border border-gray-700 rounded-lg p-4 text-center"
          >
            <div className="text-sm font-semibold text-gray-200 mb-3">{q.name}</div>
            <div className="space-y-2">
              <div>
                <div className="text-xs text-gray-400 mb-1">平均股价</div>
                <div className="text-base font-semibold text-gray-100">
                  {q.data?.avg_price ? `¥${formatValue(q.data.avg_price)}` : '-'}
                </div>
              </div>
              <div>
                <div className="text-xs text-gray-400 mb-1">分红金额</div>
                <div className="text-base font-semibold text-gray-100">
                  {q.data?.dividend ? `¥${formatValue(q.data.dividend)}` : '-'}
                </div>
              </div>
              <div>
                <div className="text-xs text-gray-400 mb-1">股息率</div>
                <div className="text-base font-semibold text-green-400">
                  {q.data?.yield_pct ? `${formatValue(q.data.yield_pct)}%` : '-'}
                </div>
              </div>
            </div>
          </div>
        ))}
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
      className={(type === 'yearly' || type === 'quarterly' || type === 'volatility' || type === 'sector') ? '!max-w-[600px]' : ''}
    >
      {renderContent()}
    </Modal>
  );
}