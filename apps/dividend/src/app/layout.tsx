import './globals.css';
import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: '股息率',
  description: '高股息率股票筛选与 M120 技术指标分析',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}