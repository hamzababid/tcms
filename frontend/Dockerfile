# Web image. `dev` runs the Vite dev server (docker-compose); `runtime` serves the built SPA with nginx.
FROM node:24-alpine AS base
RUN npm install -g pnpm@12.16.1
WORKDIR /app/frontend

FROM base AS deps
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

FROM deps AS dev
COPY frontend/ ./
EXPOSE 5173
CMD ["pnpm", "dev"]

FROM deps AS build
COPY frontend/ ./
RUN pnpm build

FROM nginx:1.29-alpine AS runtime
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/frontend/dist /usr/share/nginx/html
EXPOSE 8080
