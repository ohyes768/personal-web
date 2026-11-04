/**
 * 基本面资料阅读页（独立路由）
 *
 * 线上地址为 /dividend/quality-reader（nginx 剥前缀转发），应用内路径为 /quality-reader。
 */
import type { Metadata } from 'next';
import { Suspense } from 'react';
import { QualityReader } from '@/components/QualityReader';

export const metadata: Metadata = {
  title: '基本面资料阅读 · 股息率',
  description: '按公司连续阅读已生成的基本面五维评级报告',
};

export default function QualityReaderPage() {
  return (
    <Suspense fallback={
      <div className="quality-reader-root">
        <div className="quality-reader-container">
          <p className="quality-reader-state" role="status">正在加载基本面资料…</p>
        </div>
      </div>
    }>
      <QualityReader />
    </Suspense>
  );
}
