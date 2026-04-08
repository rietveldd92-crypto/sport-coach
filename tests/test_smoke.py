"""Smoke test — verifies pytest discovery and sys.path wiring work."""
from __future__ import annotations


def test_pytest_runs():
    assert True


def test_project_imports_resolve():
    """If this fails, tests/conftest.py is not adding project root to sys.path."""
    import config  # noqa: F401

    assert hasattr(config, "get_secret")
    assert hasattr(config, "get_bool")
