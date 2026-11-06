const backend = process.env.TASK_WEB_API_ORIGIN || "http://localhost:8101";

const nextConfig = {
  output: "standalone",
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
