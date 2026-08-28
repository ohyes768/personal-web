/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  basePath: '/macro',
  async rewrites() {
    return [
      {
        // 宏观后端接口:本地 dev 由 Next 代理到 8094(改后端后页面直接看效果);
        // 后端 router 前缀是 /api(无 macro 段),与生产 nginx 一致地剥掉 /macro 转发;
        // 生产请求被 nginx 先拦截反代,不会走到这条 rewrite
        source: '/api/macro/:path*',
        destination: `${process.env.MACRO_API_ORIGIN || 'http://localhost:8094'}/api/:path*`,
        basePath: false,
      },
    ];
  },
};

module.exports = nextConfig;