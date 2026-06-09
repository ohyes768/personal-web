/**
 * 德债日债图表调试组件
 */
'use client';

import { useEffect, useState } from 'react';
import type { EconomicDataResponse } from '@/lib/types/economic';

interface BondChartDebugProps {
  data: EconomicDataResponse;
}

export function BondChartDebug({ data }: BondChartDebugProps) {
  const [debugInfo, setDebugInfo] = useState<any>(null);

  useEffect(() => {
    // 调试信息
    const debug = {
      // 基本信息
      datesCount: data.dates?.length || 0,
      euTreasuriesKeys: data.eu_treasuries ? Object.keys(data.eu_treasuries) : [],
      jpTreasuriesKeys: data.jp_treasuries ? Object.keys(data.jp_treasuries) : [],

      // 德债数据详情
      euTreasuryDetail: {
        '3m': {
          length: data.eu_treasuries?.['3m']?.length || 0,
          nonNullCount: data.eu_treasuries?.['3m'] ? data.eu_treasuries['3m'].filter((v: any) => v !== null && v !== undefined).length : 0,
          first5: data.eu_treasuries?.['3m']?.slice(0, 5),
        },
        '2y': {
          length: data.eu_treasuries?.['2y']?.length || 0,
          nonNullCount: data.eu_treasuries?.['2y'] ? data.eu_treasuries['2y'].filter((v: any) => v !== null && v !== undefined).length : 0,
          first5: data.eu_treasuries?.['2y']?.slice(0, 5),
        },
        '10y': {
          length: data.eu_treasuries?.['10y']?.length || 0,
          nonNullCount: data.eu_treasuries?.['10y'] ? data.eu_treasuries['10y'].filter((v: any) => v !== null && v !== undefined).length : 0,
          first5: data.eu_treasuries?.['10y']?.slice(0, 5),
        },
      },

      // 日债数据详情
      jpTreasuryDetail: {
        '10y': {
          length: data.jp_treasuries?.['10y']?.length || 0,
          nonNullCount: data.jp_treasuries?.['10y'] ? data.jp_treasuries['10y'].filter((v: any) => v !== null && v !== undefined).length : 0,
          first5: data.jp_treasuries?.['10y']?.slice(0, 5),
        },
      },

      // 日期样本
      dateSamples: data.dates?.slice(0, 5),
    };

    setDebugInfo(debug);
  }, [data]);

  return (
    <div className="p-4 bg-gray-100 rounded-lg">
      <h3 className="text-lg font-bold mb-4">BondChart 调试信息</h3>

      {debugInfo && (
        <div className="space-y-4">
          <div>
            <h4 className="font-semibold">基本信息</h4>
            <p>日期数量: {debugInfo.datesCount}</p>
            <p>德债keys: {JSON.stringify(debugInfo.euTreasuriesKeys)}</p>
            <p>日债keys: {JSON.stringify(debugInfo.jpTreasuriesKeys)}</p>
          </div>

          <div>
            <h4 className="font-semibold">德债数据详情</h4>
            <pre className="bg-white p-2 rounded text-xs overflow-auto">
              {JSON.stringify(debugInfo.euTreasuryDetail, null, 2)}
            </pre>
          </div>

          <div>
            <h4 className="font-semibold">日债数据详情</h4>
            <pre className="bg-white p-2 rounded text-xs overflow-auto">
              {JSON.stringify(debugInfo.jpTreasuryDetail, null, 2)}
            </pre>
          </div>

          <div>
            <h4 className="font-semibold">日期样本</h4>
            <p>{JSON.stringify(debugInfo.dateSamples, null, 2)}</p>
          </div>
        </div>
      )}
    </div>
  );
}