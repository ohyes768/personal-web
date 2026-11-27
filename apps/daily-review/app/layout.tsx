import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "每日工作回顾",
  description: "两机 DSH 工作活动、日报周报与项目聚合",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body className="bg-gray-50 text-gray-900 min-h-screen">
        <header className="flex items-center gap-4 px-6 py-3 bg-white border-b border-gray-200">
          {/* 返回根驾驶舱：固定指向 monorepo 首页，不用 Next Link（ basePath 无关） */}
          <a href="/" className="text-sm text-gray-500 hover:text-gray-900 no-underline">
            ← 返回首页
          </a>
          <span className="font-semibold">每日工作回顾</span>
          <nav className="ml-auto flex gap-2 text-sm">
            <NavLink href="/">报告</NavLink>
            <NavLink href="/projects">项目</NavLink>
          </nav>
        </header>
        <main className="max-w-[1400px] mx-auto px-4 py-5">{children}</main>
      </body>
    </html>
  );
}

function NavLink({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <Link
      href={href}
      className="px-3 py-1 rounded-md text-gray-700 hover:bg-gray-100 no-underline"
    >
      {children}
    </Link>
  );
}
