/**
 * 股息率展示页面
 */
'use client';

import { useState, useEffect, useCallback } from 'react';
import Link from 'next/link';
import { useDividendData, useDetailModal } from '@/lib/modules/dividend/hooks';
import { DividendTable } from '@/components/modules/dividend/DividendTable';
import { DetailModal } from '@/components/modules/dividend/DetailModal';
import { Button } from '@/components/ui/Button';
import type { DividendQueryParams } from '@/lib/modules/dividend/types';

export default function DividendPage() {
  const { data, total, loading, error, refetch } = useDividendData();
  const { isOpen, modalType, stock, open, close } = useDetailModal();

  const [minYield, setMinYield] = useState(3);
  const [exchange, setExchange] = useState<string>('');

  // 固定的交易所选项
  const exchanges = ['沪市主板', '深市主板'];

  // 处理阈值输入
  const handleMinYieldChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const value = parseFloat(e.target.value);
    setMinYield(isNaN(value) || value < 0 ? 0 : value);
  }, []);

  // 查询
  const handleSearch = useCallback(() => {
    const params: DividendQueryParams = {
      min_yield: minYield,
      exchange: exchange === '全部' ? undefined : exchange,
    };
    refetch(params);
  }, [minYield, exchange, refetch]);

  // 回车触发查询
  const handleMinYieldKeyDown = useCallback((e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      handleSearch();
    }
  }, [handleSearch]);

  // 骨架屏
  if (loading && data.length === 0) {
    return (
      <div className="container mx-auto px-4 py-8 min-h-[600px]">
        <div className="mb-6">
          <div className="h-8 bg-gray-800 rounded w-48 mb-2 animate-pulse"></div>
          <div className="h-5 bg-gray-800 rounded w-32 animate-pulse"></div>
        </div>
        <div className="mb-6">
          <div className="h-10 bg-gray-800 rounded w-48 animate-pulse"></div>
        </div>
        <div className="border border-gray-700 rounded-lg overflow-hidden h-[600px]">
          <div className="h-full bg-gray-800 animate-pulse"></div>
        </div>
      </div>
    );
  }

  // 错误状态
  if (error && data.length === 0) {
    return (
      <div className="container mx-auto px-4 py-8 min-h-[600px]">
        <div className="text-center py-16">
          <p className="text-red-400 mb-4">{error}</p>
          <Button onClick={() => refetch()}>重试</Button>
        </div>
      </div>
    );
  }

  return (
    <div className="container mx-auto px-8 lg:px-16 py-8 min-h-[600px]">
      {/* 头部导航 */}
      <div className="mb-6 max-w-6xl mx-auto">
        <div className="flex justify-between items-start">
          <div>
            <Link href="/" className="text-gray-400 hover:text-white transition-colors">
              ← 返回首页
            </Link>
            <h1 className="text-4xl font-bold mt-4">股息率数据展示</h1>
          </div>
          <div className="text-right">
            <span className="text-gray-400">共 {total} 条数据</span>
          </div>
        </div>
      </div>

      {/* 错误提示（有数据时） */}
      {error && data.length > 0 && (
        <div className="mb-4 max-w-6xl mx-auto bg-yellow-900/50 border border-yellow-700 text-yellow-200 px-4 py-3 rounded">
          {error}
        </div>
      )}

      {/* 表格 */}
      <div className="flex justify-center">
        <div className="w-full max-w-6xl">
          {/* 筛选工具栏 */}
          <div className="mb-2 flex items-center justify-end gap-2">
            <label htmlFor="exchange" className="text-sm text-gray-300 whitespace-nowrap">
              交易所
            </label>
            <select
              id="exchange"
              value={exchange}
              onChange={(e) => setExchange(e.target.value)}
              className="px-2 py-1 text-sm border border-gray-600 rounded bg-gray-800 text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="">全部</option>
              {exchanges.map((ex) => (
                <option key={ex} value={ex}>
                  {ex}
                </option>
              ))}
            </select>
            <label htmlFor="min-yield" className="text-sm text-gray-300 whitespace-nowrap ml-2">
              最小股息率
            </label>
            <input
              id="min-yield"
              type="number"
              min={0}
              step={0.1}
              value={minYield}
              onChange={handleMinYieldChange}
              onKeyDown={handleMinYieldKeyDown}
              className="w-20 px-2 py-1 text-sm border border-gray-600 rounded bg-gray-800 text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <span className="text-sm text-gray-400">%</span>
            <Button onClick={handleSearch} className="px-3 py-1 text-sm">
              查询
            </Button>
          </div>

          {data.length > 0 ? (
            <DividendTable
              data={data}
              onOpenModal={open}
            />
          ) : (
            <div className="border border-gray-700 rounded-lg overflow-hidden bg-gray-900 h-[300px]">
              <div className="h-full flex items-center justify-center text-gray-400">
                暂无数据，请尝试调整筛选条件
              </div>
            </div>
          )}
        </div>
      </div>

      {/* 详情弹框 */}
      <DetailModal
        isOpen={isOpen}
        onClose={close}
        type={modalType}
        stock={stock}
      />
    </div>
  );
}