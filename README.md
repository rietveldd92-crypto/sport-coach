# Sport Coach

Adaptieve trainingscoach (Delahaije-blokperiodisering) met intervals.icu als
backend-of-record. v2 = FastAPI (`api/`) + React PWA (`web/`) over de
bestaande agents (`agents/`, `core/`). Zie `UPGRADE_PLAN.md` voor de
architectuur en `DECISIONS.md` voor de keuzes.

## Draaien

### Ontwikkelen (API + frontend los)

```bash
# API op :8000 (eenmalig: pip install -r requirements.txt requirements-dev.txt)
uvicorn api.main:app --reload

# Frontend op :5173, proxy't /api naar :8000
cd web && npm install && npm run dev
```

Offline ontwikkelen zonder intervals.icu: `INTERVALS_FAKE=1` zet een
deterministische in-memory fixture aan (`core/fake_intervals.py`).
Nuttige env-vars: `API_TOKEN` (bearer-auth, leeg = geen auth),
`SCHEDULER_ENABLED` (APScheduler), `TP_SYNC_ENABLED` + `TP_AUTH_COOKIE`
(TrainingPeaks→Zwift), `SPORT_DB_PATH` (locatie history.db),
`GOOGLE_API_KEY` (Gemini-coachfeedback).

### Productie (één container)

De multi-stage `Dockerfile` bouwt `web/dist` (node) en serveert API +
statics uit één uvicorn-proces; niet-/api-routes vallen terug op
`index.html` (SPA), zodat de PWA installeerbaar is vanaf hetzelfde domein.

```bash
docker build -t sport-coach .
docker run -p 8000:8000 --env-file .env \
  -e SPORT_DB_PATH=/app/data/history.db -v $(pwd)/data:/app/data \
  sport-coach
```

Zonder Docker: `cd web && npm run build`, daarna `uvicorn api.main:app` —
de app pikt `web/dist` automatisch op (of zet `WEB_DIST_DIR`).

### Tests

```bash
python -m pytest          # volledige suite (mock-intervals, eigen tmp-DB)
cd web && npm run build   # tsc --noEmit + vite build
```

## Structuur

| Map | Wat |
|---|---|
| `api/` | FastAPI-routers (UPGRADE_PLAN §7) + scheduler + SPA-serving |
| `core/` | views, slot-solver, goal-engine, periodisatie-generator, replan |
| `agents/` | coaches, injury_guard, load_manager, feedback_engine |
| `web/` | React PWA (Vite + TS + Tailwind): Today · Week · Season · Jij |
| `tests/` | pytest-suite incl. API-integratietests tegen mock-intervals |
| `legacy_streamlit/` | gearchiveerde Streamlit-UI (v1, bevroren) |
