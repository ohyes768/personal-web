import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "NAS 服务管理台",
  description: "NAS 上 Docker Compose 服务的台账、端口、域名证书与发布动态",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>
        <header className="site-header">
          <a href="/" className="back-home">
            ← 返回首页
          </a>
          <span className="site-title">NAS 服务管理台</span>
          <nav>
            {/* basePath=/services 由 Next 自动拼接；写 /services 会变成 /services/services */}
            <Link href="/">服务</Link>
            <Link href="/resources">资源总览</Link>
            <Link href="/discovery">发现导入</Link>
            <Link href="/settings">设置</Link>
          </nav>
        </header>
        <main className="container">{children}</main>
      </body>
    </html>
  );
}
