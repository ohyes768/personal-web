const backend = process.env.INDEX_TRENDS_API_ORIGIN || "http://localhost:8100";

const nextConfig = {
  output: "standalone",
  basePath: "/index-trends",
  async rewrites() {
    return [
      {
        source: "/api/index-trends/:path*",
        destination: `${backend}/api/:path*`,
        basePath: false,
      },
    ];
  },
};

export default nextConfig;
