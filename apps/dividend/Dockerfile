FROM node:20-alpine AS base

# 安装 pnpm
RUN npm install -g pnpm

# 依赖阶段
FROM base AS deps
WORKDIR /app
# monorepo 必需：workspace 配置 + lockfile + 共享包源码 + 当前 app 的 package.json
COPY pnpm-workspace.yaml pnpm-lock.yaml ./
COPY packages/ ./packages/
COPY apps/dividend/package.json ./apps/dividend/package.json
RUN pnpm install --frozen-lockfile

# 构建阶段
FROM base AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY --from=deps /app/apps/dividend/node_modules ./apps/dividend/node_modules
COPY --from=deps /app/packages/ ./packages/
COPY apps/dividend/ ./apps/dividend/
RUN cd apps/dividend && pnpm build

# 运行阶段
FROM base AS runner
WORKDIR /app
ENV NODE_ENV=production

RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 nextjs

# ★ 显式复制完整 node_modules（pnpm + monorepo 软链下 standalone trace 不全）
# standalone 输出里 next 软链到 .pnpm/next@...，docker COPY 不保证软链完整
# 多带点 node_modules 是 docker 部署 next.js standalone 的常见做法
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/apps/dividend/node_modules ./apps/dividend/node_modules
COPY --from=builder /app/packages ./packages

# standalone 输出（server.js 在 apps/dividend/server.js）
COPY --from=builder --chown=nextjs:nodejs /app/apps/dividend/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/apps/dividend/.next/static ./apps/dividend/.next/static

USER nextjs

EXPOSE 3003
ENV PORT=3003

CMD ["node", "apps/dividend/server.js"]
