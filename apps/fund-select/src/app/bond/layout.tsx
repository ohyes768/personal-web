import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: '债基',
};

export default function BondLayout({ children }: { children: React.ReactNode }) {
  return children;
}
