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
COPY apps/dividend/package.json ./apps/dividend/package.json
RUN pnpm install --frozen-lockfile

# 构建阶段
FROM base AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY --from=deps /app/packages/ ./packages/
COPY apps/dividend/ ./apps/dividend/
# ★ 绕过 pnpm .bin/ 软链缺失问题：直接绝对路径调用 next 启动器
#   背景：nodeLinker: hoisted 下 next 是真实目录，但 pnpm 没建 .bin/next 软链
#   用 'pnpm --filter ... build' 找不到 next；用绝对路径最稳
RUN cd /app/apps/dividend && /app/node_modules/next/dist/bin/next build

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
