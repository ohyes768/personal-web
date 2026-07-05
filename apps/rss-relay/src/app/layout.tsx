import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "个人 RSS 中转",
  description: "agent 采集推送的 markdown 内容中转站",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body className="antialiased">
        {children}
      </body>
    </html>
  );
}
