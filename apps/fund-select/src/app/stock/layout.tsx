import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: '股基·雪球三分法',
};

export default function StockLayout({ children }: { children: React.ReactNode }) {
  return children;
}
