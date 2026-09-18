/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  basePath: '/map',
  async rewrites() {
    return [
      {
        // 本地 dev: Next 代理 /api/map/* → localhost:8096/api/*；
        // 生产请求被 nginx 先拦截反代(剥 /api/map 前缀转后端)，不会走到这条 rewrite
        source: '/api/map/:path*',
        destination: `${process.env.HOUSING_API_ORIGIN || 'http://localhost:8096'}/api/:path*`,
        basePath: false,
      },
    ];
  },
};

module.exports = nextConfig;
