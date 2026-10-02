import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "滨房地图 - 杭州滨江·萧山接壤板块房价地图",
  description: "杭州滨江区与萧山接壤板块（钱江世纪城/开发区/宁围/闻堰）房价地图，实时更新小区价格，标注周边配套设施，综合打分帮你选房",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}