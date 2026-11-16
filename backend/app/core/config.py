"""Settings from the environment (backend/.env is read if present; it is gitignored).

DATABASE_URL        postgresql+psycopg://railopt:<password>@localhost:5432/railopt
                    (unset: a local SQLite file for development, with a warning)
JWT_SECRET          signing key for the session cookies (unset: random per process, so every
                    restart signs everyone out - set it in .env)
COOKIE_SECURE       true when served over HTTPS (cookies then carry the Secure flag)
ACCESS_TOKEN_MIN    access-token lifetime, default 15 min
REFRESH_TOKEN_HOURS refresh-token lifetime, default 8 h
RAILOPT_ADMIN_EMAIL / RAILOPT_ADMIN_PASSWORD  optional: first admin, created at start-up only
                    when no admin exists (or use: python -m app.cli create-admin)
"""
from __future__ import annotations

import logging
import os
import secrets
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
log = logging.getLogger("railopt.config")


def _load_dotenv() -> None:
    env = BACKEND_DIR / ".env"
    if env.exists():
        from dotenv import load_dotenv
        load_dotenv(env, override=False)


def _bool(v: str | None) -> bool:
    return (v or "").strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Settings:
    database_url: str
    database_url_is_default: bool
    jwt_secret: str
    jwt_secret_is_random: bool
    cookie_secure: bool
    access_token_min: int
    refresh_token_hours: int
    login_max_failures: int = 5          # failed logins for one email ...
    login_window_min: int = 15           # ... within this many minutes ...
    login_lockout_min: int = 15          # ... refuse further attempts for this long


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    _load_dotenv()
    url = os.environ.get("DATABASE_URL", "").strip()
    default = not url
    if default:
        url = f"sqlite:///{(BACKEND_DIR / 'data' / 'railopt-dev.sqlite3').as_posix()}"
        log.warning("DATABASE_URL is not set: using the development SQLite file %s", url)
    secret = os.environ.get("JWT_SECRET", "").strip()
    random_secret = not secret
    if random_secret:
        secret = secrets.token_urlsafe(48)
        log.warning("JWT_SECRET is not set: using a random key (sessions end when the API restarts)")
    return Settings(database_url=url, database_url_is_default=default, jwt_secret=secret,
                    jwt_secret_is_random=random_secret, cookie_secure=_bool(os.environ.get("COOKIE_SECURE")),
                    access_token_min=int(os.environ.get("ACCESS_TOKEN_MIN", "15")),
                    refresh_token_hours=int(os.environ.get("REFRESH_TOKEN_HOURS", "8")))
