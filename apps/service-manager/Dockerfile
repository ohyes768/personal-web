FROM node:20-alpine AS build
WORKDIR /app
RUN npm install -g pnpm
COPY package.json pnpm-lock.yaml* ./
ARG PNPM_CACHE_BUST=shared
RUN --mount=type=cache,id=pnpm-${PNPM_CACHE_BUST},target=/root/.local/share/pnpm/store \
    pnpm install --no-frozen-lockfile
COPY . .
ARG SERVICE_MANAGER_API_ORIGIN=http://service-manager-backend:8102
ENV SERVICE_MANAGER_API_ORIGIN=${SERVICE_MANAGER_API_ORIGIN}
RUN pnpm build

FROM node:20-alpine
WORKDIR /app
ENV NODE_ENV=production PORT=3012 HOSTNAME=0.0.0.0
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
EXPOSE 3012
CMD ["node","server.js"]
