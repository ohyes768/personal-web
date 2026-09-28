FROM node:20-alpine AS build
WORKDIR /app
COPY package.json ./
RUN npm install
COPY . .
RUN npm run build
FROM node:20-alpine
WORKDIR /app
ENV NODE_ENV=production PORT=3009 HOSTNAME=0.0.0.0
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
EXPOSE 3009
CMD ["node","server.js"]