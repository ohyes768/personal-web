FROM node:20-alpine AS deps
WORKDIR /app
RUN npm install -g pnpm
COPY package.json pnpm-lock.yaml ./
# PNPM_CACHE_BUST=shared → 热构建复用 store；--cold 时传入时间戳 → 空 store 重下
ARG PNPM_CACHE_BUST=shared
RUN --mount=type=cache,id=pnpm-${PNPM_CACHE_BUST},target=/root/.local/share/pnpm/store \
    pnpm install --frozen-lockfile

FROM node:20-alpine AS builder
WORKDIR /app
RUN npm install -g pnpm
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# 无 NEXT_PUBLIC_* 构建参数：API 请求由 Nginx 反代 /api/skills/* 直转后端，
# 前端只做相对路径 fetch；管理密码（SKILL_MANAGER_ADMIN_PASSWORD）绝不进入前端镜像
RUN pnpm build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 nextjs

# Next.js standalone 模式产物：next.config.js 中 output: 'standalone'
# server.js 是入口；.next/static 必须单独拷（standalone 不自动包含静态资源）
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs
EXPOSE 3008
ENV PORT=3008
ENV HOSTNAME="0.0.0.0"

CMD ["node", "server.js"]
