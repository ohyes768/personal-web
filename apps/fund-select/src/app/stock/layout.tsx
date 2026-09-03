import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: '股票基金筛选',
};

export default function StockLayout({ children }: { children: React.ReactNode }) {
  return children;
}
