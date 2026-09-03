import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: '债券基金筛选',
};

export default function BondLayout({ children }: { children: React.ReactNode }) {
  return children;
}
