# 构建阶段
FROM node:20-alpine AS builder

WORKDIR /app

# 复制依赖文件
COPY package.json ./

# 安装 pnpm
RUN npm install -g pnpm

# 安装依赖
RUN pnpm install

# 复制源代码
COPY . .

# 构建应用
RUN pnpm build

# 生产阶段
FROM node:20-alpine AS runner

WORKDIR /app

# 安装 pnpm
RUN npm install -g pnpm

# 复制必要文件
COPY --from=builder /app/next.config.ts ./
COPY --from=builder /app/public ./public
COPY --from=builder /app/package.json ./

# 复制构建产物
COPY --from=builder --chown=node:node /app/.next/standalone ./
COPY --from=builder --chown=node:node /app/.next/static ./.next/static

# 设置环境变量
ENV NODE_ENV=production
ENV PORT=3000

# 暴露端口
EXPOSE 3000

# 启动应用
CMD ["node", "server.js"]
