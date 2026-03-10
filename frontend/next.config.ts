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

  // 注意：代理逻辑已移至 src/app/api/macro/[...path]/route.ts
  // 使用 API Routes 而非 rewrites，因为 rewrites 在构建时执行无法读取运行时环境变量
}

export default nextConfig
