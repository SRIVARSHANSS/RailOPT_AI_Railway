"""Passwords (bcrypt) and session tokens (JWT, HS256). Plain Python, no FastAPI.

bcrypt is used directly: passlib 1.7.4 does not work with bcrypt 5. bcrypt reads at most 72
bytes, so longer passwords are refused instead of silently truncated."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
from jose import ExpiredSignatureError, JWTError, jwt

ALGORITHM = "HS256"
MIN_PASSWORD = 10
MAX_PASSWORD_BYTES = 72


class TokenError(Exception):
    def __init__(self, message: str, expired: bool = False):
        super().__init__(message)
        self.expired = expired


def password_problem(password: str) -> str | None:
    if len(password) < MIN_PASSWORD:
        return f"Password must be at least {MIN_PASSWORD} characters."
    if len(password.encode("utf-8")) > MAX_PASSWORD_BYTES:
        return f"Password must be at most {MAX_PASSWORD_BYTES} bytes."
    return None


def hash_password(password: str) -> str:
    problem = password_problem(password)
    if problem:
        raise ValueError(problem)
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("ascii")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8")[:MAX_PASSWORD_BYTES], hashed.encode("ascii"))
    except ValueError:
        return False


def make_token(*, user_id: int, role: str, token_version: int, kind: str, lifetime: timedelta,
               secret: str, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    claims = {"sub": str(user_id), "role": role, "tv": token_version, "type": kind,
              "iat": int(now.timestamp()), "exp": int((now + lifetime).timestamp()), "jti": uuid.uuid4().hex}
    return jwt.encode(claims, secret, algorithm=ALGORITHM)


def decode_token(token: str, *, secret: str, kind: str) -> dict:
    try:
        claims = jwt.decode(token, secret, algorithms=[ALGORITHM])
    except ExpiredSignatureError:
        raise TokenError("Session expired - sign in again.", expired=True)
    except JWTError:
        raise TokenError("Invalid session - sign in again.")
    if claims.get("type") != kind:
        raise TokenError("Invalid session - sign in again.")
    return claims


_DUMMY: str | None = None


def burn_time(password: str) -> None:
    """Check against a dummy hash, so an unknown email takes as long as a wrong password."""
    global _DUMMY
    if _DUMMY is None:
        _DUMMY = bcrypt.hashpw(b"railopt-dummy-password", bcrypt.gensalt(rounds=12)).decode("ascii")
    verify_password(password, _DUMMY)
