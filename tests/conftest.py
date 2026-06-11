"""Pytest configuration.

Adds the project root to sys.path so tests can import top-level modules
(config, intervals_client, trainingpeaks_client, workout_converter, ...)
without needing an installable package layout.
"""
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture(autouse=True)
def _isolated_history_db(tmp_path, monkeypatch):
    """Elke test krijgt een eigen, lege history.db.

    Sinds Fase 0 leven athlete_state en de TP-synclog in SQLite; zonder
    deze fixture zouden tests naar de echte history.db schrijven.
    """
    import history_db
    monkeypatch.setattr(history_db, "DB_PATH", tmp_path / "history_test.db")
