# 构建阶段 - 使用国内镜像源
FROM node:20-alpine AS builder

WORKDIR /app

# 使用阿里云 npm 镜像
RUN npm config set registry https://registry.npmmirror.com

# 安装 pnpm
RUN npm install -g pnpm

# 配置 pnpm 使用阿里云镜像
RUN pnpm config set registry https://registry.npmmirror.com

# 复制依赖文件
COPY package.json pnpm-lock.yaml* package-lock.json* ./

# 安装依赖（使用国内镜像）
RUN pnpm install --frozen-lockfile || npm install

# 复制源代码
COPY . .

# 确保 public 目录存在
RUN mkdir -p public

# 构建 Next.js 应用（传入 API 地址）
ARG NEXT_PUBLIC_API_BASE_URL
ENV NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL}
RUN pnpm build || npm run build

# 生产阶段
FROM node:20-alpine AS runner

WORKDIR /app

# 安装 pnpm
RUN npm install -g pnpm

# 创建非 root 用户
RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 nextjs

# 复制必要文件
COPY --from=builder /app/next.config.ts ./
COPY --from=builder /app/package.json ./
COPY --from=builder /app/pnpm-lock.yaml* ./

# 创建并复制 public 目录
RUN mkdir -p ./public
COPY --from=builder /app/public/ ./public/

# 复制 .next 目录
RUN mkdir -p .next
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

# 设置环境变量
ENV NODE_ENV=production
ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

# 切换用户
USER nextjs

# 暴露端口
EXPOSE 3000

# 启动应用
CMD ["node", "server.js"]
