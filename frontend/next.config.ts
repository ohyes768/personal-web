/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  reactStrictMode: true,

  // 启用 Server Actions（如果使用）
  experimental: {
    serverActions: {
      bodySizeLimit: '2mb',
    },
  },

  // 配置代理
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: 'http://localhost:8094/api/:path*',
      },
    ];
  },
}

export default nextConfig
