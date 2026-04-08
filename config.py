"""Central secrets/config layer for Sport Coach.

Reads secrets from Streamlit st.secrets first (cloud deploy), then from
environment variables (local .env via python-dotenv), then from defaults.

Callers must use get_secret() / get_bool() instead of calling os.environ
or st.secrets directly, so the lookup order is consistent everywhere.
"""
from __future__ import annotations

import os
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

try:
    import streamlit as st
    _HAS_STREAMLIT = True
except ImportError:
    _HAS_STREAMLIT = False


class ConfigError(RuntimeError):
    """Raised when a required config value is missing."""


def _from_streamlit(name: str) -> Optional[str]:
    """Read from st.secrets, tolerating the 'no secrets.toml' case."""
    if not _HAS_STREAMLIT:
        return None
    try:
        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:
        # st.secrets raises FileNotFoundError / StreamlitSecretNotFoundError
        # when no secrets.toml exists; that's fine, fall through to env.
        pass
    return None


def get_secret(
    name: str,
    default: Optional[str] = None,
    required: bool = False,
) -> Optional[str]:
    """Look up a secret by name.

    Order: st.secrets → os.environ → default.
    Raises ConfigError if required=True and the value is missing.
    """
    value = _from_streamlit(name)
    if value is None:
        value = os.environ.get(name)
    if value is None:
        value = default

    if required and value is None:
        raise ConfigError(
            f"Required secret '{name}' is not set. "
            f"Add it to .streamlit/secrets.toml or .env."
        )
    return value


def get_bool(name: str, default: bool = False) -> bool:
    """Read a boolean flag. Accepts true/false, 1/0, yes/no, on/off."""
    raw = get_secret(name)
    if raw is None:
        return default
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}
