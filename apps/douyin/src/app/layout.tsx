import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "抖音视频文字稿",
  description: "财经博主视频转文字稿",
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