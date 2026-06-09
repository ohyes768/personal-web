import './globals.css';
import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: '资金流向',
  description: '沪深港通北向/南向资金流向数据',
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