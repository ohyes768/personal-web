// 后端端口走 env（参考 index-trends），不硬编码进组件代码
const backend = process.env.DAILY_REVIEW_API_ORIGIN || "http://127.0.0.1:8103";

const nextConfig = {
  output: "standalone",
  basePath: "/review",
  async rewrites() {
    return [
      {
        // basePath 生效时 rewrite source 自动带 /review 前缀：
        // /review/api/today → ${backend}/api/review/today
        source: "/api/:path*",
        destination: `${backend}/api/review/:path*`,
      },
    ];
  },
};

export default nextConfig;
