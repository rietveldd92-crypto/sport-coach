# Sport Coach v2 — één container met FastAPI (api/) + de PWA-build (web/dist).
# Build:  docker build -t sport-coach .
# Run:    docker run -p 8000:8000 --env-file .env \
#           -e SPORT_DB_PATH=/app/data/history.db -v $(pwd)/data:/app/data \
#           sport-coach

# ── Stage 1: frontend (Vite → web/dist) ──────────────────────────────────
FROM node:22-alpine AS webbuild
WORKDIR /build/web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

# ── Stage 2: api + statics ────────────────────────────────────────────────
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY . .
COPY --from=webbuild /build/web/dist ./web/dist

# api/main.py serveert web/dist met SPA-fallback; /api blijft de REST-laag.
# $PORT wordt door Railway geïnjecteerd; lokaal valt hij terug op 8000.
EXPOSE 800