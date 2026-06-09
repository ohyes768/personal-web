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
# ★ 手动 cp workspace 包到 node_modules/@personal-web/（绕开 pnpm 软链断裂）
#  背景：nodeLinker: hoisted 下 pnpm 对 workspace 包仍用软链，docker COPY
#   软链 target 失效导致 next resolve 失败。cp -rL 复制真实文件最稳
RUN mkdir -p /app/node_modules/@personal-web && \
    cp -rL /app/packages/* /app/node_modules/@personal-web/
# ★ 绕过 pnpm .bin/ 软链缺失：直接绝对路径调用 next 启动器
RUN cd /app/apps/douyin && /app/node_modules/next/dist/bin/next build

# 运行阶段
FROM base AS runner
WORKDIR /app
ENV NODE_ENV=production

RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 nextjs

# standalone 输出（Next.js 15 monorepo 模式：入口是根的 server.js）
COPY --from=builder --chown=nextjs:nodejs /app/apps/douyin/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/apps/douyin/.next/static ./.next/static

# ★ runner 阶段也要带 node_modules + packages
#  原因：server.js require('next') + workspace 包 @personal-web/* 都要能找到
#  standalone 输出里 .bin/ 软链在 docker COPY 跨 stage 时断裂
#  用 builder 阶段真实文件（已 cp workspace 包到 node_modules/，见 builder 段）
COPY --from=builder --chown=nextjs:nodejs /app/node_modules ./node_modules
COPY --from=builder --chown=nextjs:nodejs /app/packages ./packages

USER nextjs

EXPOSE 3004
ENV PORT=3004

# ★ 关键：Next.js standalone 入口是根的 server.js（不是 apps/<x>/server.js）
CMD ["node", "server.js"]
