# legacy_streamlit — gearchiveerde v1-UI

De oorspronkelijke Streamlit-app (`app.py` + `ui_components.py` + `viz/`),
in Fase 5 verplaatst toen de React PWA (`web/`) alle dagelijkse en
wekelijkse flows overnam (UPGRADE_PLAN §8).

- **Status: bevroren.** Geen nieuwe features; alleen hier laten staan als
  referentie voor de oude flows en de design-tokens.
- Nog draaien kan: `streamlit run legacy_streamlit/app.py` vanaf de
  repo-root (app.py zet zelf de repo-root op `sys.path`).
- `viz/workout_chart.py` wordt nog door `tests/test_workout_chart.py`
  getest (import via `legacy_streamlit.viz.workout_chart`); de parser kan
  later naar `core/` verhuizen als de PWA een workout-chart krijgt.
- De Streamlit-dependencies (`streamlit`, `altair`, `plotly`) staan nog in
  `requirements.txt`; opruimen kan zodra dit pakket echt weg mag.
