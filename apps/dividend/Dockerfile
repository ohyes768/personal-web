FROM node:20-alpine AS base

# 安装 pnpm
RUN npm install -g pnpm

# 依赖阶段
FROM base AS deps
WORKDIR /app
# ★ 关键：禁用 pnpm 软链，展平所有依赖为真实文件
# 否则 docker COPY 时 .pnpm 软链会断，runner 阶段 require('next') 失败
RUN pnpm config set shamefully-hoist true
# monorepo 必需：workspace 配置 + lockfile + 共享包源码 + 当前 app 的 package.json
COPY pnpm-workspace.yaml pnpm-lock.yaml ./
COPY packages/ ./packages/
COPY apps/dividend/package.json ./apps/dividend/package.json
RUN pnpm install --frozen-lockfile

# 构建阶段
FROM base AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY --from=deps /app/packages/ ./packages/
COPY apps/dividend/ ./apps/dividend/
RUN cd apps/dividend && pnpm build

# 运行阶段
FROM base AS runner
WORKDIR /app
ENV NODE_ENV=production

RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 nextjs

# standalone 输出（Next.js 15 monorepo 模式：入口是根的 server.js）
COPY --from=builder --chown=nextjs:nodejs /app/apps/dividend/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/apps/dividend/.next/static ./apps/dividend/.next/static

USER nextjs

EXPOSE 3003
ENV PORT=3003

# ★ 关键：Next.js standalone 入口是根的 server.js（不是 apps/<x>/server.js）
CMD ["node", "server.js"]
