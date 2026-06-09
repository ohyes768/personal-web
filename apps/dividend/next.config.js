/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  // basePath: '' （Nginx 配 location /dividend/ 末尾加 / 剥前缀，前端不用关心部署路径）
  // monorepo: workspace 包入口是 .ts 源码（package.json: main: ./src/index.ts）
  // Next.js standalone 默认不会转译这些 .ts 包，必须显式声明
  transpilePackages: [
    '@personal-web/api-client',
    '@personal-web/shared-ui',
    '@personal-web/shared-types',
    '@personal-web/shared-utils',
  ],
};

module.exports = nextConfig;

