import './globals.css';
import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Skill 发布管理台',
  description: '自研与 GitHub Agent Skills 双栏发布工作台',
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
