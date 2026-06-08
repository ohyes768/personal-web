FROM node:20-alpine AS base

# 安装 pnpm
RUN npm install -g pnpm

# 依赖阶段
FROM base AS deps
WORKDIR /app
# ★ 用 pnpm-workspace.yaml 的 nodeLinker: hoisted 展平依赖
#   （pnpm 8+ 标准写法，替代 deprecated 的 shamefully-hoist=true）
# monorepo 必需：workspace 配置 + lockfile + 共享包源码 + 当前 app 的 package.json
COPY pnpm-workspace.yaml pnpm-lock.yaml ./
COPY packages/ ./packages/
COPY apps/douyin/package.json ./apps/douyin/package.json
RUN pnpm install --frozen-lockfile

# 构建阶段
FROM base AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY --from=deps /app/packages/ ./packages/
COPY apps/douyin/ ./apps/douyin/
# ★ pnpm --filter 在 root context 执行，自动 prepend node_modules/.bin 到 PATH
#   比 'cd apps/douyin && pnpm build' 可靠（避免子包下 .bin 找不到）
RUN pnpm --filter @personal-web/app-douyin build

# 运行阶段
FROM base AS runner
WORKDIR /app
ENV NODE_ENV=production

RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 nextjs

# standalone 输出（Next.js 15 monorepo 模式：入口是根的 server.js）
COPY --from=builder --chown=nextjs:nodejs /app/apps/douyin/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/apps/douyin/.next/static ./apps/douyin/.next/static

USER nextjs

EXPOSE 3004
ENV PORT=3004

# ★ 关键：Next.js standalone 入口是根的 server.js（不是 apps/<x>/server.js）
CMD ["node", "server.js"]
