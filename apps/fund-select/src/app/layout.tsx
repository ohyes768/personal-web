import './globals.css';
import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: '基金筛选',
  description: '债券 / 股票基金筛选与对比',
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
