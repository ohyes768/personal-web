/**
 * 分析报告看板页 — 路由 /reports（basePath 下实际为 /macro/reports）
 * 接收 impact skill 推送的 markdown 分析报告，列表 + 详情两栏浏览
 */
'use client';

import Link from 'next/link';
import { ReportBoard } from './components/ReportBoard';

export default function ReportsPage() {
  return (
    <main className="min-h-screen bg-black text-white p-4 sm:p-6 lg:p-8">
      <div className="max-w-7xl mx-auto">
        {/* 头部：返回宏观主页 + 标题 */}
        <header className="mb-8">
          {/* Link href 是 app 内路径，basePath=/macro 自动补全 → 实际跳 /macro/ 主页 */}
          <Link href="/" className="text-gray-400 hover:text-white transition-colors">
            ← 返回宏观主页
          </Link>
          <h1 className="text-4xl font-bold mt-4">分析报告看板</h1>
        </header>

        <ReportBoard />
      </div>
    </main>
  );
}
