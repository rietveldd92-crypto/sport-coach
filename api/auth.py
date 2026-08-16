"""Auth — wachtwoord-login met een ondertekende sessie-cookie.

Drie manieren om binnen te komen, in deze volgorde:

- **Sessie-cookie** (de app op je telefoon). Je logt één keer in met een
  wachtwoord; de server zet een httpOnly-cookie die een jaar meegaat. De
  cookie is HMAC-ondertekend, dus hij is niet te vervalsen zonder het
  servergeheim, en JavaScript kan er niet bij.
- **Bearer-token** (scripts, curl, de oude ``?token=``-link). Blijft werken.
- **Localhost** — alleen als er geen wachtwoord is geconfigureerd (dev).

Waarom de cookie er is: de token stond eerst in de URL en in localStorage.
Dat lekt via je adresbalk, je history en elke chat waarin je de link plakt,
en bij het wissen van je browserdata was je de app kwijt zonder weg terug.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time

from fastapi import HTTPException, Request, Response

import config

# 'testclient' is de host die Starlette's TestClient meegeeft.
LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}

SESSION_COOKIE = "coach_session"
SESSION_MAX_AGE = 60 * 60 * 24 * 365   # een jaar; dit is een single-user app
CLOCK_SKEW_SEC = 300                   # cookie uit de "toekomst" mag iets

# Brute-force-rem. Het wachtwoord is single-user en dus waarschijnlijk kort;
# zonder rem is een login-endpoint op het open internet zo doorgeraden.
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_SEC = 60
_failed: dict[str, list] = {}


def _password() -> str | None:
    """Het inlogwachtwoord. Valt terug op API_TOKEN zodat een bestaande
    deploy zonder nieuwe env-var meteen werkt."""
    return config.get_secret("APP_PASSWORD") or config.get_secret("API_TOKEN")


def _signing_secret() -> str:
    return (config.get_secret("SESSION_SECRET")
            or config.get_secret("API_TOKEN")
            or config.get_secret("APP_PASSWORD")
            or "")


def auth_enabled() -> bool:
    return bool(_password())


def _sign(issued_at: str) -> str:
    return hmac.new(_signing_secret().encode(), issued_at.encode(),
                    hashlib.sha256).hexdigest()


def issue_session() -> str:
    issued_at = str(int(time.time()))
    return f"{issued_at}.{_sign(issued_at)}"


def session_is_valid(raw: str | None) -> bool:
    if not raw:
        return False
    issued_at, _, signature = raw.partition(".")
    if not signature or not issued_at.isdigit():
        return False
    if not secrets.compare_digest(signature, _sign(issued_at)):
        return False
    age = time.time() - int(issued_at)
    return -CLOCK_SKEW_SEC <= age <= SESSION_MAX_AGE


def _bearer_is_valid(request: Request) -> bool:
    token = config.get_secret("API_TOKEN")
    if not token:
        return False
    scheme, _, supplied = (
        request.headers.get("authorization") or "").partition(" ")
    return (scheme.lower() == "bearer"
            and secrets.compare_digest(supplied.strip(), str(token)))


def is_authenticated(request: Request) -> bool:
    if not auth_enabled():
        host = request.client.host if request.client else ""
        return host in LOCAL_HOSTS
    return (session_is_valid(request.cookies.get(SESSION_COOKIE))
            or _bearer_is_valid(request))


def require_auth(request: Request) -> None:
    """FastAPI-dependency: 401 als er geen geldige sessie of token is."""
    if is_authenticated(request):
        return
    if not auth_enabled():
        raise HTTPException(
            status_code=401,
            detail="Geen wachtwoord geconfigureerd — alleen localhost toegestaan",
        )
    raise HTTPException(status_code=401, detail="Niet ingelogd")


# ── login / logout ─────────────────────────────────────────────────────────

def _locked_out(client: str) -> bool:
    attempts = [t for t in _failed.get(client, [])
                if time.time() - t < LOCKOUT_SEC]
    _failed[client] = attempts
    return len(attempts) >= MAX_FAILED_ATTEMPTS


def login(request: Request, response: Response, password: str) -> None:
    """Zet de sessie-cookie bij het juiste wachtwoord, anders 401."""
    expected = _password()
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="Geen APP_PASSWORD/API_TOKEN geconfigureerd op de server",
        )

    client = request.client.host if request.client else "?"
    if _locked_out(client):
        raise HTTPException(
            status_code=429,
            detail=f"Te veel pogingen. Wacht {LOCKOUT_SEC} seconden.",
        )

    if not secrets.compare_digest(password.strip(), str(expected)):
        _failed.setdefault(client, []).append(time.time())
        raise HTTPException(status_code=401, detail="Onjuist wachtwoord")

    _failed.pop(client, None)
    response.set_cookie(
        SESSION_COOKIE,
        issue_session(),
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        # Op localhost draait de app over http; daar zou een Secure-cookie
        # nooit teruggestuurd worden.
        secure=request.url.scheme == "https",
        path="/",
    )


def logout(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")
