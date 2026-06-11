# Sport Coach Web (PWA)

React-frontend voor de Sport Coach API. Mobile-first, dark, installeerbaar als PWA.

## Dev

```bash
# Backend (repo-root) — fixture-modus voor offline ontwikkelen:
INTERVALS_FAKE=1 uvicorn api.main:app --port 8000
# Windows PowerShell: $env:INTERVALS_FAKE="1"; uvicorn api.main:app --port 8000

# Frontend (deze map):
npm install
npm run dev          # http://localhost:5173, proxied naar :8000
```

## Build & preview

```bash
npm run build        # tsc --noEmit + vite build → dist/ (incl. service worker)
npm run preview      # serveert dist/ op :4173
```

## Env / config

- `INTERVALS_FAKE=1` (backend) — intervals.icu vervangen door fixture-data (zelfde bron als tests/mock_intervals.py)
- `API_TOKEN` (backend) — bearer-token; leeg = alleen localhost
- `SCHEDULER_ENABLED=1` (backend) — APScheduler (dagelijkse feedback, zondagse herijking)
- Dev-proxy naar `localhost:8000` staat in `vite.config.ts`

## Structuur

- `src/screens/` — Today, Week (+ stubs Season/Jij voor fase 5)
- `src/features/` — CheckinSheet, SwapSheet, MoveDiffSheet, AvailabilitySheet
- `src/api/` — client, TanStack Query hooks, types (volgen api/routers responses)
- `src/lib/` — datum- en workout-helpers (zones, duur, beschrijving-parser)
