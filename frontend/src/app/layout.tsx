import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "个人资讯网站",
  description: "宏观经济、新闻分析、视频文字稿",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body className="antialiased">
        {children}
      </body>
    </html>
  );
}
