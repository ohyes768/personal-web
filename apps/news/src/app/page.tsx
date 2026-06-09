'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { Loading } from '@/components/shared-ui/Loading';
import { usePolicyRanking, useSentimentDistribution } from '@/lib/hooks';
import type { PolicyRankingData, SentimentDistribution } from '@/lib/types';

const TIME_RANGES = ['1M', '3M', '6M', '1Y'] as const;
const TOP_N_OPTIONS = [10, 20, 50] as const;

export default function NewsPage() {
  const [timeRange, setTimeRange] = useState<string>('1M');
  const [topN, setTopN] = useState<number>(20);

  const { data: rankingData, loading: rankingLoading, error: rankingError, refetch: refetchRanking } = usePolicyRanking(timeRange, topN);
  const { data: sentimentData, loading: sentimentLoading, error: sentimentError, refetch: refetchSentiment } = useSentimentDistribution(timeRange);

  useEffect(() => {
    refetchRanking();
    refetchSentiment();
  }, [timeRange, topN, refetchRanking, refetchSentiment]);

  const getGradeColor = (grade: string) => {
    switch (grade) {
      case '强烈推荐':
        return 'bg-green-600 text-white';
      case '推荐':
        return 'bg-green-500 text-white';
      case '中性':
        return 'bg-yellow-500 text-black';
      case '不推荐':
        return 'bg-red-500 text-white';
      case '强烈不推荐':
        return 'bg-red-600 text-white';
      default:
        return 'bg-gray-500 text-white';
    }
  };

  return (
    <main className="min-h-screen bg-gray-900 text-white">
      <div className="max-w-7xl mx-auto p-8">
        {/* 头部导航 */}
        <div className="mb-8">
          <Link href="/" className="text-gray-400 hover:text-white transition-colors">
            ← 返回首页
          </Link>
          <h1 className="text-4xl font-bold mt-4">新闻联播分析</h1>
          <p className="text-gray-400 mt-2">政策推荐指数、板块影响分析</p>
        </div>

        {/* 筛选控件 */}
        <div className="mb-8 flex flex-wrap gap-4 items-center">
          <div>
            <label className="block text-sm text-gray-400 mb-1">时间范围</label>
            <select
              value={timeRange}
              onChange={(e) => setTimeRange(e.target.value)}
              className="bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 focus:outline-none focus:border-blue-500"
            >
              {TIME_RANGES.map((range) => (
                <option key={range} value={range}>
                  {range === '1M' ? '1 个月' : range === '3M' ? '3 个月' : range === '6M' ? '6 个月' : '1 年'}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm text-gray-400 mb-1">显示数量</label>
            <select
              value={topN}
              onChange={(e) => setTopN(Number(e.target.value))}
              className="bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 focus:outline-none focus:border-blue-500"
            >
              {TOP_N_OPTIONS.map((n) => (
                <option key={n} value={n}>
                  前 {n} 个
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* 错误提示 */}
        {(rankingError || sentimentError) && (
          <div className="mb-8 p-4 bg-red-900/50 border border-red-700 rounded-lg">
            <p className="text-red-200">
              {rankingError || sentimentError}
            </p>
          </div>
        )}

        {/* 情感分布 */}
        <div className="mb-8 bg-gray-800 rounded-lg p-6">
          <h2 className="text-2xl font-bold mb-4">情感分布</h2>
          {sentimentLoading ? (
            <Loading />
          ) : sentimentData ? (
            <div className="flex gap-4">
              <div className="flex-1 bg-green-900/50 rounded-lg p-4 text-center">
                <div className="text-3xl font-bold text-green-400">{sentimentData.bullish.toFixed(1)}%</div>
                <div className="text-gray-400 mt-1">看涨</div>
              </div>
              <div className="flex-1 bg-yellow-900/50 rounded-lg p-4 text-center">
                <div className="text-3xl font-bold text-yellow-400">{sentimentData.neutral.toFixed(1)}%</div>
                <div className="text-gray-400 mt-1">中性</div>
              </div>
              <div className="flex-1 bg-red-900/50 rounded-lg p-4 text-center">
                <div className="text-3xl font-bold text-red-400">{sentimentData.bearish.toFixed(1)}%</div>
                <div className="text-gray-400 mt-1">看跌</div>
              </div>
            </div>
          ) : (
            <p className="text-gray-400">暂无数据</p>
          )}
        </div>

        {/* 政策推荐排行榜 */}
        <div className="bg-gray-800 rounded-lg p-6">
          <h2 className="text-2xl font-bold mb-4">政策推荐指数排行榜</h2>
          {rankingLoading ? (
            <Loading />
          ) : rankingData && rankingData.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-gray-700">
                    <th className="text-left py-3 px-4">排名</th>
                    <th className="text-left py-3 px-4">板块代码</th>
                    <th className="text-left py-3 px-4">板块名称</th>
                    <th className="text-left py-3 px-4">板块类型</th>
                    <th className="text-right py-3 px-4">政策得分</th>
                    <th className="text-left py-3 px-4">推荐等级</th>
                    <th className="text-right py-3 px-4">看涨比例</th>
                    <th className="text-right py-3 px-4">平均重要性</th>
                  </tr>
                </thead>
                <tbody>
                  {rankingData.map((item, index) => (
                    <tr key={item.board_code} className="border-b border-gray-700 hover:bg-gray-700/50">
                      <td className="py-3 px-4">{index + 1}</td>
                      <td className="py-3 px-4 font-mono">{item.board_code}</td>
                      <td className="py-3 px-4">{item.board_name}</td>
                      <td className="py-3 px-4">{item.board_type}</td>
                      <td className="py-3 px-4 text-right">{item.policy_score.toFixed(2)}</td>
                      <td className="py-3 px-4">
                        <span className={`px-2 py-1 rounded-full text-sm ${getGradeColor(item.recommendation_grade)}`}>
                          {item.recommendation_grade}
                        </span>
                      </td>
                      <td className="py-3 px-4 text-right">{(item.bullish_ratio * 100).toFixed(1)}%</td>
                      <td className="py-3 px-4 text-right">{item.avg_importance.toFixed(2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-gray-400">暂无数据</p>
          )}
        </div>
      </div>
    </main>
  );
}