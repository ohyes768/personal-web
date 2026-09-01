import './globals.css';
import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: '债基筛选',
  description: '31 只精选债基筛选与对比',
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
