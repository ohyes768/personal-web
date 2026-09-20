/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  basePath: '/skills',
  async rewrites() {
    // 仅开发环境代理到本地 FastAPI（8097）；生产由 Nginx 反代 /api/skills
    if (process.env.NODE_ENV !== 'development') {
      return [];
    }
    return [
      {
        source: '/api/skills/:path*',
        destination: 'http://localhost:8097/api/skills/:path*',
        basePath: false,
      },
    ];
  },
};

module.exports = nextConfig;
