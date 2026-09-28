FROM node:20-alpine AS build
WORKDIR /app
RUN npm install -g pnpm
COPY package.json pnpm-lock.yaml .npmrc ./
# PNPM_CACHE_BUST=shared → 热构建复用 store；--cold 时传入时间戳 → 空 store 重下
ARG PNPM_CACHE_BUST=shared
RUN --mount=type=cache,id=pnpm-${PNPM_CACHE_BUST},target=/root/.local/share/pnpm/store \
    pnpm install --frozen-lockfile
COPY . .
RUN pnpm build
FROM node:20-alpine
WORKDIR /app
ENV NODE_ENV=production PORT=3009 HOSTNAME=0.0.0.0
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
EXPOSE 3009
CMD ["node","server.js"]