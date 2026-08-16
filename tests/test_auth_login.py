"""Wachtwoord-login met sessie-cookie.

De token stond eerst in de URL en in localStorage: dat lekt via je history
en je adresbalk, en bij het wissen van browserdata was de app onbruikbaar
zonder weg terug. Deze tests bewaken de vervanger.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import config
from api import auth


@pytest.fixture()
def env(monkeypatch):
    monkeypatch.setattr(config, "_from_streamlit", lambda name: None)
    for var in ("API_TOKEN", "APP_PASSWORD", "SESSION_SECRET",
                "SCHEDULER_ENABLED"):
        monkeypatch.delenv(var, raising=False)
    auth._failed.clear()
    yield monkeypatch


@pytest.fixture()
def client(env):
    env.setenv("APP_PASSWORD", "geheim")
    env.setenv("SESSION_SECRET", "servergeheim")
    from api.main import create_app

    with TestClient(create_app()) as c:
        yield c


def test_zonder_login_geen_toegang(client):
    assert client.get("/api/season").status_code == 401


def test_login_geeft_toegang_en_blijft_hangen(client):
    r = client.post("/api/auth/login", json={"password": "geheim"})

    assert r.status_code == 200
    assert client.get("/api/auth/status").json()["authenticated"] is True
    # De cookie reist mee: geen header, geen token, tóch binnen.
    assert client.get("/api/season").status_code != 401


def test_cookie_is_httponly_en_bevat_het_wachtwoord_niet(client):
    r = client.post("/api/auth/login", json={"password": "geheim"})

    raw = r.headers["set-cookie"]
    assert "httponly" in raw.lower()
    assert "geheim" not in raw          # geen wachtwoord in de cookie
    assert "servergeheim" not in raw    # en zeker geen servergeheim


def test_fout_wachtwoord_wordt_geweigerd(client):
    r = client.post("/api/auth/login", json={"password": "fout"})

    assert r.status_code == 401
    assert client.get("/api/season").status_code == 401


def test_vervalste_cookie_komt_er_niet_in(client):
    client.cookies.set(auth.SESSION_COOKIE, "9999999999.nephandtekening")

    assert client.get("/api/auth/status").json()["authenticated"] is False
    assert client.get("/api/season").status_code == 401


def test_cookie_ondertekend_met_ander_geheim_is_ongeldig(env):
    """Draai je SESSION_SECRET om, dan zijn alle sessies meteen dood."""
    env.setenv("APP_PASSWORD", "geheim")
    env.setenv("SESSION_SECRET", "geheim-A")
    gestolen = auth.issue_session()

    env.setenv("SESSION_SECRET", "geheim-B")

    assert auth.session_is_valid(gestolen) is False


def test_logout_gooit_je_eruit(client):
    client.post("/api/auth/login", json={"password": "geheim"})

    client.post("/api/auth/logout")

    assert client.get("/api/auth/status").json()["authenticated"] is False


def test_brute_force_wordt_afgeknepen(client):
    for _ in range(auth.MAX_FAILED_ATTEMPTS):
        client.post("/api/auth/login", json={"password": "fout"})

    r = client.post("/api/auth/login", json={"password": "fout"})
    assert r.status_code == 429
    # En ook het juiste wachtwoord komt er tijdens de lockout niet doorheen.
    assert client.post("/api/auth/login",
                       json={"password": "geheim"}).status_code == 429


def test_bearer_token_blijft_werken_voor_scripts(env):
    """curl, cron en de oude ?token=-link mogen niet stukgaan."""
    env.setenv("API_TOKEN", "geheim-token")
    from api.main import create_app

    with TestClient(create_app()) as c:
        assert c.get("/api/season").status_code == 401
        r = c.get("/api/season",
                  headers={"Authorization": "Bearer geheim-token"})
        assert r.status_code != 401


def test_api_token_werkt_ook_als_wachtwoord(env):
    """Bestaande deploy zonder nieuwe env-var moet meteen kunnen inloggen."""
    env.setenv("API_TOKEN", "geheim-token")
    from api.main import create_app

    with TestClient(create_app()) as c:
        r = c.post("/api/auth/login", json={"password": "geheim-token"})
        assert r.status_code == 200
        assert c.get("/api/auth/status").json()["authenticated"] is True
