const backend = process.env.TASK_WEB_API_ORIGIN || "http://localhost:8101";

const nextConfig = {
  // Docker 部署依赖 standalone 产物；Windows 本机无 symlink 特权时 trace 拷贝
  // 会 EPERM（与 spec 记录的 WinError 1314 同源），本机构建用
  // TASK_WEB_NO_STANDALONE=1 跳过，部署环境不受影响。
  output: process.env.TASK_WEB_NO_STANDALONE ? undefined : "standalone",
  basePath: "/tasks",
  async rewrites() {
    return [
      {
        source: "/api/task-web/:path*",
        destination: `${backend}/api/:path*`,
        basePath: false,
      },
    ];
  },
};

export default nextConfig;
