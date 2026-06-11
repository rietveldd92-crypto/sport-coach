# Sport Coach v2 — één container met FastAPI (api/) + de PWA-build (web/dist).
# Build:  docker build -t sport-coach .
# Run:    docker run -p 8000:8000 --env-file .env \
#           -e SPORT_DB_PATH=/app/data/history.db -v $(pwd)/data:/app/data \
#           sport-coach

# ── Stage 1: frontend (Vite → web/dist) ──────────────────────────────────
# bookworm-slim (glibc) en `npm install` i.p.v. `npm ci`: geen lockfile-
# afhankelijkheid in het image — voorkomt platform-mismatch van rollup's
# optionele binaries (npm bug #4828) en lock-desync-fouten.
FROM node:22-bookworm-slim AS webbuild
WORKDIR /build/web
COPY web/package.json ./
RUN npm install --no-audit --no-fund
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
EXPOSE 8000
CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
