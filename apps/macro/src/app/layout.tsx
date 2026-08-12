import './globals.css';
import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: '宏观经济数据',
  description: '美国国债收益率与汇率数据趋势分析',
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