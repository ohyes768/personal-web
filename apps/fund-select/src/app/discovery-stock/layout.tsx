import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: '股基·市场',
};

export default function DiscoveryStockLayout({ children }: { children: React.ReactNode }) {
  return children;
}
