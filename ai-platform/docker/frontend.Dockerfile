# ─── Builder ───────────────────────────────────────────────
FROM node:22-alpine AS builder

WORKDIR /build

COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci

COPY frontend/ .
RUN npm run build

# ─── Runtime ───────────────────────────────────────────────
FROM nginx:alpine AS runtime

COPY --from=builder /build/dist /usr/share/nginx/html
COPY docker/frontend.nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

HEALTHCHECK --interval=15s --timeout=5s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://localhost:80/ || exit 1
