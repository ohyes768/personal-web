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

  // 配置代理（开发环境使用，生产环境使用 API Routes）
  async rewrites() {
    const macroServiceUrl = process.env.MACRO_SERVICE_URL || 'http://localhost:8094'
    return [
      {
        source: '/api/macro/:path*',
        destination: `${macroServiceUrl}/api/macro/:path*`,
      },
    ]
  },
}

export default nextConfig
