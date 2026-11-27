FROM node:20-alpine AS build
WORKDIR /app
RUN npm install -g pnpm
COPY package.json pnpm-lock.yaml ./
ARG PNPM_CACHE_BUST=shared
RUN --mount=type=cache,id=pnpm-${PNPM_CACHE_BUST},target=/root/.local/share/pnpm/store \
    pnpm install --frozen-lockfile
COPY . .
ARG DAILY_REVIEW_API_ORIGIN=http://daily-review-backend:8103
ENV DAILY_REVIEW_API_ORIGIN=${DAILY_REVIEW_API_ORIGIN}
RUN pnpm build

FROM node:20-alpine
WORKDIR /app
ENV NODE_ENV=production PORT=3013 HOSTNAME=0.0.0.0
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
EXPOSE 3013
CMD ["node","server.js"]
