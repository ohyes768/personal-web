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
# 高德地图 key：NEXT_PUBLIC_* 需构建期 inline（build args 由 compose 从根 .env 传入）
ARG NEXT_PUBLIC_GAODE_MAP_KEY
ARG NEXT_PUBLIC_GAODE_MAP_SECURITY_KEY
ENV NEXT_PUBLIC_GAODE_MAP_KEY=$NEXT_PUBLIC_GAODE_MAP_KEY
ENV NEXT_PUBLIC_GAODE_MAP_SECURITY_KEY=$NEXT_PUBLIC_GAODE_MAP_SECURITY_KEY
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
COPY --from=builder --chown=nextjs:nodejs /app/public ./public

USER nextjs
EXPOSE 3007
ENV PORT=3007
ENV HOSTNAME="0.0.0.0"

CMD ["node", "server.js"]
