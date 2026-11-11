const backend = process.env.SERVICE_MANAGER_API_ORIGIN || "http://localhost:8102";

const nextConfig = {
  // Docker 部署依赖 standalone 产物；Windows 本机无 symlink 特权时 trace 拷贝
  // 会 EPERM，本机构建可用 SERVICE_MANAGER_NO_STANDALONE=1 跳过。
  output: process.env.SERVICE_MANAGER_NO_STANDALONE ? undefined : "standalone",
  basePath: "/services",
  async rewrites() {
    return [
      {
        // 对外是 /api/services/*，后端 router 前缀是 /api/*
        source: "/api/services/:path*",
        destination: `${backend}/api/:path*`,
        basePath: false,
      },
    ];
  },
};

export default nextConfig;
