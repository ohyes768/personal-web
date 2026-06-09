import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "新闻联播分析",
  description: "政策推荐指数、板块影响分析",
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