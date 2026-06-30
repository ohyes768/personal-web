/**
 * 经济数据过滤 Hook — 纯 useMemo 计算，零网络请求
 * 输入：fullData + timeRange + tabType
 * 输出：按时间范围 + Tab 类型裁剪后的 data
 *
 * 与 useFullEconomicData 配合使用：
 *   page.tsx 顶层调 useFullEconomicData 拿 fullData
 *   各 Tab 用 useFilteredEconomicData 拿自己需要的 data
 *   timeRange/tabType 变化时只重算 useMemo，不发请求
 *
 * bonds tabType 内部自动调 filterMonthlyData（按月级切分德债日债数据）
 */
'use client';

import { useMemo } from 'react';
import type { EconomicDataResponse, TimeRange, TabType } from '../types/economic';
import { calculateDateRange, TIME_RANGE_MAP } from '../utils/dateCalculators';
import { filterDataByTab, filterMonthlyData } from '../utils/dataFilterUtils';

// 默认空数据（保证 slice 时不报 undefined.length）
function getDefaultEconomicData(): EconomicDataResponse {
  return {
    dates: [],
    us_treasuries: { '3m': [], '2y': [], '10y': [] },
    eu_treasuries: { '3m': [], '2y': [], '10y': [] },
    jp_treasuries: { '3m': [], '2y': [], '10y': [] },
    exchange_rates: {
      dollar_index: [],
      usd_cny: [],
      usd_jpy: [],
      usd_eur: [],
    },
    vix: [],
    commodities: { gold: [], silver: [], oil: [], copper: [] },
    indices: { HKHSI: [], SH000001: [], SPX: [], IXIC: [], DJI: [] },
    tga: [],
    hibor: [],
  };
}

export function useFilteredEconomicData(
  fullData: EconomicDataResponse | null,
  timeRange: TimeRange,
  tabType: TabType = 'treasury-exchange'
): EconomicDataResponse | null {
  return useMemo(() => {
    if (!fullData || fullData.dates.length === 0) {
      return null;
    }

    // 1. bonds Tab 先做月度切分
    let processedData: EconomicDataResponse = fullData;
    if (tabType === 'bonds') {
      processedData = filterMonthlyData(fullData);
    }

    const { startDate, endDate } = calculateDateRange(timeRange);

    // ALL：直接返回 processedData 按 tabType 过滤
    if (timeRange === 'ALL') {
      const result = filterDataByTab(processedData, tabType, timeRange);
      return result || getDefaultEconomicData();
    }

    // 2. 按 timeRange 切片
    const dates = processedData.dates;
    let startIndex = 0;
    let endIndex = dates.length;

    // 用数据最后一天作为 endDate 基准（如果数据比 today 旧，caller 传的 endDate 会让 findIndex 全失败）
    // 这样 startDate 倒推也有意义
    const dataLastDate = dates[dates.length - 1];
    const effectiveEndDate =
      dataLastDate && (!endDate || dataLastDate < endDate)
        ? dataLastDate
        : endDate;

    if (startDate && effectiveEndDate) {
      // 从 effectiveEndDate 倒推 days 天作为新的 startDate
      const days = TIME_RANGE_MAP[timeRange];
      if (days && Number.isFinite(days)) {
        const t = new Date(effectiveEndDate);
        t.setDate(t.getDate() - days);
        const adjustedStart = t.toISOString().split('T')[0];
        startIndex = dates.findIndex((d) => d >= adjustedStart);
        if (startIndex === -1) {
          // 兜底：从末尾往回数（按交易日密度 0.7 估算）
          startIndex = Math.max(0, dates.length - Math.floor(days * 0.7));
        }
      } else {
        startIndex = dates.findIndex((d) => d >= startDate);
        if (startIndex === -1) startIndex = 0;
      }
    }

    if (effectiveEndDate) {
      endIndex = dates.findIndex((d) => d > effectiveEndDate);
      if (endIndex === -1) endIndex = dates.length;
    }

    // 3. 过滤数据（先按时间范围，再按 Tab 类型）
    const filteredDates = dates.slice(startIndex, endIndex);

    const timeFiltered: EconomicDataResponse = {
      ...processedData,
      dates: filteredDates,
      us_treasuries: {
        '3m': processedData.us_treasuries?.['3m']?.slice(startIndex, endIndex) ?? [],
        '2y': processedData.us_treasuries?.['2y']?.slice(startIndex, endIndex) ?? [],
        '10y': processedData.us_treasuries?.['10y']?.slice(startIndex, endIndex) ?? [],
      },
      eu_treasuries: {
        '3m': processedData.eu_treasuries?.['3m']?.slice(startIndex, endIndex) ?? [],
        '2y': processedData.eu_treasuries?.['2y']?.slice(startIndex, endIndex) ?? [],
        '10y': processedData.eu_treasuries?.['10y']?.slice(startIndex, endIndex) ?? [],
      },
      jp_treasuries: {
        '3m': processedData.jp_treasuries?.['3m']?.slice(startIndex, endIndex) ?? [],
        '2y': processedData.jp_treasuries?.['2y']?.slice(startIndex, endIndex) ?? [],
        '10y': processedData.jp_treasuries?.['10y']?.slice(startIndex, endIndex) ?? [],
      },
      exchange_rates: processedData.exchange_rates
        ? {
            dollar_index:
              processedData.exchange_rates.dollar_index?.slice(startIndex, endIndex) ?? [],
            usd_cny:
              processedData.exchange_rates.usd_cny?.slice(startIndex, endIndex) ?? [],
            usd_jpy:
              processedData.exchange_rates.usd_jpy?.slice(startIndex, endIndex) ?? [],
            usd_eur:
              processedData.exchange_rates.usd_eur?.slice(startIndex, endIndex) ?? [],
          }
        : undefined,
      vix: processedData.vix?.slice(startIndex, endIndex) ?? [],
      // 以下字段对比模块需要，必须保留
      fund_flow: processedData.fund_flow
        ? {
            north_net_flow:
              processedData.fund_flow.north_net_flow?.slice(startIndex, endIndex) ?? [],
            north_buy:
              processedData.fund_flow.north_buy?.slice(startIndex, endIndex) ?? [],
            north_sell:
              processedData.fund_flow.north_sell?.slice(startIndex, endIndex) ?? [],
            south_net_flow:
              processedData.fund_flow.south_net_flow?.slice(startIndex, endIndex) ?? [],
            south_buy:
              processedData.fund_flow.south_buy?.slice(startIndex, endIndex) ?? [],
            south_sell:
              processedData.fund_flow.south_sell?.slice(startIndex, endIndex) ?? [],
          }
        : undefined,
      china_bond: processedData.china_bond
        ? {
            '10y':
              processedData.china_bond['10y']?.slice(startIndex, endIndex) ?? [],
            'spread_10y_2y':
              processedData.china_bond.spread_10y_2y?.slice(startIndex, endIndex) ?? [],
          }
        : undefined,
      ted_spread: processedData.ted_spread
        ? {
            sofr: processedData.ted_spread.sofr?.slice(startIndex, endIndex) ?? [],
            us_3m: processedData.ted_spread.us_3m?.slice(startIndex, endIndex) ?? [],
            ted_spread:
              processedData.ted_spread.ted_spread?.slice(startIndex, endIndex) ?? [],
          }
        : undefined,
      commodities: processedData.commodities
        ? {
            gold: processedData.commodities.gold?.slice(startIndex, endIndex) ?? [],
            silver: processedData.commodities.silver?.slice(startIndex, endIndex) ?? [],
            oil: processedData.commodities.oil?.slice(startIndex, endIndex) ?? [],
            copper: processedData.commodities.copper?.slice(startIndex, endIndex) ?? [],
          }
        : undefined,
      indices: processedData.indices
        ? {
            HKHSI: processedData.indices.HKHSI?.slice(startIndex, endIndex) ?? [],
            SH000001:
              processedData.indices.SH000001?.slice(startIndex, endIndex) ?? [],
            SPX: processedData.indices.SPX?.slice(startIndex, endIndex) ?? [],
            IXIC: processedData.indices.IXIC?.slice(startIndex, endIndex) ?? [],
            DJI: processedData.indices.DJI?.slice(startIndex, endIndex) ?? [],
          }
        : undefined,
      tga: processedData.tga?.slice(startIndex, endIndex) ?? [],
      hibor: processedData.hibor?.slice(startIndex, endIndex) ?? [],
    };

    const result = filterDataByTab(timeFiltered, tabType, timeRange);
    return result || getDefaultEconomicData();
  }, [fullData, timeRange, tabType]);
}
