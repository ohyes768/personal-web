/**
 * 股息率展示页面
 */
'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import Link from 'next/link';
import { useDividendData, useDetailModal, useTechnicalData, useRefreshPrice, useStockInfo, useCompare } from '@/lib/modules/dividend/hooks';
import { DividendTable } from '@/components/modules/dividend/DividendTable';
import { DetailModal } from '@/components/modules/dividend/DetailModal';
import { CompareFloatingBar } from '@/components/modules/dividend/CompareFloatingBar';
import { CompareDrawer } from '@/components/modules/dividend/CompareDrawer';
import { Button } from '@/components/ui/Button';
import type { DividendQueryParams, TechnicalIndicators, DividendStockWithTechnical, DividendStock } from '@/lib/modules/dividend/types';

const MAX_COMPARE = 5;

export default function DividendPage() {
  const { data, total, loading, error, refetch } = useDividendData();
  const { isOpen, modalType, stock, open, close } = useDetailModal();

  // 获取技术指标数据（PE、M120 等）
  const stockCodes = data.map(s => s.code);
  const { technicalData: rawTechnicalData } = useTechnicalData(stockCodes);
  const { stockInfoMap } = useStockInfo(stockCodes);

  // 刷新功能
  const { refresh, getRefreshState, getCache } = useRefreshPrice();

  // 对比功能
  const {
    selectedStocks,
    isDrawerOpen,
    toggleStock,
    clearSelection,
    openDrawer,
    closeDrawer,
    removeStock,
    isSelected,
  } = useCompare(MAX_COMPARE);

  const drawerRef = useRef<HTMLDivElement>(null);

  // 状态管理
  const [minYield, setMinYield] = useState(5);
  const [exchange, setExchange] = useState<string>('');
  const [technicalData, setTechnicalData] = useState<Map<string, TechnicalIndicators>>(rawTechnicalData);

  // 将股票信息合并到数据中
  const dataWithInfo = data.map(stock => {
    const info = stockInfoMap.get(stock.code);
    return {
      ...stock,
      exchange: info?.exchange || stock.exchange,
      sw_level1: info?.sw_level1 || null,
      sw_level2: info?.sw_level2 || null,
      sw_level3: info?.sw_level3 || null,
      // concept_board 和 industry_board 不在列表中显示，点击板块时再获取
      concept_board: null,
      industry_board: null,
    };
  });

  // 监听技术指标数据变化
  useEffect(() => {
    setTechnicalData(rawTechnicalData);
  }, [rawTechnicalData]);

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

  // 刷新实时股价
  const handleRefresh = useCallback(async (code: string, m120: number) => {
    const result = await refresh({ code, m120 });

    if (result) {
      // 更新技术指标数据中的实时价格字段
      setTechnicalData(prev => {
        const newMap = new Map(prev);
        const existing = newMap.get(code) || {};

        newMap.set(code, {
          ...existing,
          realtimeClose: result.close,
          realtimeDeviation: result.deviation,
          m120: m120,
        });

        return newMap;
      });
    }

    return result;
  }, [refresh]);

  // 切换对比选中
  const handleToggleCompare = useCallback((stock: DividendStock) => {
    toggleStock(stock);
  }, [toggleStock]);

  // 打开对比抽屉
  const handleOpenCompare = useCallback(() => {
    const success = openDrawer();
    if (!success) {
      alert('请至少选择 2 只股票进行对比');
    }
  }, [openDrawer]);

  // 获取带技术指标的对比数据
  const getStocksWithTechnical = useCallback((): DividendStockWithTechnical[] => {
    return selectedStocks.map(stock => {
      const technical = technicalData.get(stock.code);
      return {
        ...stock,
        technical: technical || undefined,
      };
    });
  }, [selectedStocks, technicalData]);

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

          {dataWithInfo.length > 0 ? (
            <DividendTable
              data={dataWithInfo}
              technicalData={technicalData}
              onOpenModal={open}
              onRefresh={handleRefresh}
              getRefreshState={getRefreshState}
              selectedStockCodes={selectedStocks.map(s => s.code)}
              maxSelect={MAX_COMPARE}
              onToggleCompare={handleToggleCompare}
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

      {/* 对比浮动栏 */}
      <CompareFloatingBar
        selectedCount={selectedStocks.length}
        selectedStocks={selectedStocks}
        maxSelect={MAX_COMPARE}
        onOpenCompare={handleOpenCompare}
        onClear={clearSelection}
        isVisible={selectedStocks.length > 0}
      />

      {/* 对比抽屉 */}
      <CompareDrawer
        isOpen={isDrawerOpen}
        onClose={closeDrawer}
        stocks={getStocksWithTechnical()}
        onRemove={removeStock}
        drawerRef={drawerRef}
      />
    </div>
  );
}