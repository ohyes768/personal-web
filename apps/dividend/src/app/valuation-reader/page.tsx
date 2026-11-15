/**
 * 估值资料阅读页（独立路由）
 *
 * 线上地址为 /dividend/valuation-reader（nginx 剥前缀转发），应用内路径为 /valuation-reader。
 */
import type { Metadata } from 'next';
import { Suspense } from 'react';
import { ValuationReader } from '@/components/ValuationReader';

export const metadata: Metadata = {
  title: '估值资料阅读 · 股息率',
  description: '按公司连续阅读已生成的四挡位估值报告',
};

export default function ValuationReaderPage() {
  return (
    <Suspense fallback={
      <div className="quality-reader-root">
        <div className="quality-reader-container">
          <p className="quality-reader-state" role="status">正在加载估值资料…</p>
        </div>
      </div>
    }>
      <ValuationReader />
    </Suspense>
  );
}
