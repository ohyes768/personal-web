import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "定时任务管理",
  description: "NAS 定时任务调度、执行记录与日志",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>
        <header className="site-header">
          <a href="/" className="back-home">← 返回首页</a>
          <span className="site-title">定时任务管理</span>
          <nav>
            <Link href="/tasks">任务</Link>
            <Link href="/schedule">排期日历</Link>
            <Link href="/runs">运行记录</Link>
          </nav>
        </header>
        <main className="container">{children}</main>
      </body>
    </html>
  );
}
