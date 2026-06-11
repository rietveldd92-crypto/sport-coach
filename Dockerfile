# Sport Coach v2 — één container met FastAPI (api/) + de PWA-build (web/dist).
# Build:  docker build -t sport-coach .
# Run:    docker run -p 8000:8000 --env-file .env \
#           -e SPORT_DB_PATH=/app/data/history.db -v $(pwd)/data:/app/data \
#           sport-coach

# ── Stage 1: frontend (Vite → web/dist) ──────────────────────────────────
# bookworm-slim (glibc) i.p.v. alpine (musl): de package-lock is op glibc
# gegenereerd; rollup's platform-specifieke optional dep ontbreekt anders
# (npm bug #4828 → "Cannot find module @rollup/rollup-linux-x64-musl").
FROM node:22-bookworm-slim AS webbuild
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
RUN pip install -r requir