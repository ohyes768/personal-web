/**
 * 日期计算工具函数
 */
import type { TimeRange } from '../types/economic';

/** 时间范围到天数映射 */
export const TIME_RANGE_MAP: Record<TimeRange, number | null> = {
  '1M': 30,
  '3M': 90,
  '6M': 180,
  '1Y': 365,
  '3Y': 1095,
  'ALL': null,
};

/** 缓存TTL（毫秒） */
export const CACHE_TTL = 3600000; // 1小时

/** 缓存Key */
export const CACHE_KEY = 'economic_data_cache';

/**
 * 根据时间范围计算起止日期
 */
export function calculateDateRange(timeRange: TimeRange): {
  startDate: string | null;
  endDate: string;
} {
  const endDate = new Date().toISOString().split('T')[0];

  if (timeRange === 'ALL') {
    return { startDate: null, endDate };
  }

  const days = TIME_RANGE_MAP[timeRange];
  if (days === null) {
    return { startDate: null, endDate };
  }

  const startDate = new Date();
  startDate.setDate(startDate.getDate() - days);

  return {
    startDate: startDate.toISOString().split('T')[0],
    endDate,
  };
}

/**
 * 检查缓存是否过期
 */
export function isCacheExpired(timestamp: number, ttl: number = CACHE_TTL): boolean {
  return Date.now() - timestamp > ttl;
}

/**
 * 从缓存读取数据
 */
export function readFromCache(timeRange: TimeRange): any | null {
  if (typeof window === 'undefined') return null;

  try {
    const cacheStr = localStorage.getItem(CACHE_KEY);
    if (!cacheStr) return null;

    const cache: any[] = JSON.parse(cacheStr);
    const entry = cache.find(
      (e) => e.timeRange === timeRange && !isCacheExpired(e.timestamp)
    );

    return entry?.data || null;
  } catch (error) {
    console.error('读取缓存失败:', error);
    return null;
  }
}

/**
 * 写入缓存
 */
export function writeToCache(timeRange: TimeRange, data: any): void {
  if (typeof window === 'undefined') return;

  try {
    const cacheStr = localStorage.getItem(CACHE_KEY);
    const cache: any[] = cacheStr ? JSON.parse(cacheStr) : [];

    // 移除旧的同时间范围缓存
    const filtered = cache.filter((e) => e.timeRange !== timeRange);

    // 添加新缓存
    filtered.push({
      timeRange,
      data,
      timestamp: Date.now(),
    });

    localStorage.setItem(CACHE_KEY, JSON.stringify(filtered));
  } catch (error) {
    console.error('写入缓存失败:', error);
  }
}

/**
 * 清除缓存
 */
export function clearCache(): void {
  if (typeof window === 'undefined') return;

  try {
    localStorage.removeItem(CACHE_KEY);
  } catch (error) {
    console.error('清除缓存失败:', error);
  }
}
