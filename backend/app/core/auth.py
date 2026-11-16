"""Auth dependencies, roles, the audit log and login rate limiting (Phase 8).

Roles (docs/ASSUMPTIONS.md 80-):
  ADMIN       users, audit log, network management (and every read view)
  CONTROLLER  events, optimize, accept/reject, scenario reset, what-if (and every read view)
  ANALYST     every read view, what-if, reports
Session: an access JWT (short) and a refresh JWT, both in httpOnly SameSite=Lax cookies.
A user's token_version is in every token; logout, deactivation and a password reset bump it,
which ends every existing session of that user."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import TokenError, decode_token
from app.db import models as m
from app.db.session import get_db

ACCESS_COOKIE = "railopt_access"
REFRESH_COOKIE = "railopt_refresh"
REFRESH_PATH = "/api/auth"

ADMIN, CONTROLLER, ANALYST = "ADMIN", "CONTROLLER", "ANALYST"
READ = (ADMIN, CONTROLLER, ANALYST)
CONTROL = (CONTROLLER,)
WHATIF = (CONTROLLER, ANALYST)
ADMIN_ONLY = (ADMIN,)


def actor(user) -> dict:
    """What the store and the audit log record about the user."""
    return {"id": getattr(user, "id", None), "email": getattr(user, "email", None)}


def client_ip(request: Request | None) -> str | None:
    return request.client.host if request is not None and request.client else None


def audit(db: Session, action: str, *, user=None, email: str | None = None, detail: dict | None = None,
          request: Request | None = None, commit: bool = True) -> None:
    db.add(m.AuditLog(user_id=getattr(user, "id", None), email=email or getattr(user, "email", None),
                      action=action, detail=detail or {}, ip=client_ip(request)))
    if commit:
        db.commit()


def current_user(request: Request, db: Session = Depends(get_db)) -> m.User:
    token = request.cookies.get(ACCESS_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="Not signed in. Sign in to use RailOpt AI.")
    try:
        claims = decode_token(token, secret=get_settings().jwt_secret, kind="access")
    except TokenError as exc:
        raise HTTPException(status_code=401, detail=str(exc),
                            headers={"X-Session-Expired": "1"} if exc.expired else None)
    user = db.get(m.User, int(claims["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="This account is deactivated or no longer exists.")
    if user.token_version != claims.get("tv"):
        raise HTTPException(status_code=401, detail="Session ended (signed out elsewhere or password reset) - sign in again.")
    return user


def require(*roles: str):
    """Dependency: the signed-in user must have one of `roles` (403 otherwise)."""
    def dep(user: m.User = Depends(current_user)) -> m.User:
        if user.role not in roles:
            need = " or ".join(roles)
            raise HTTPException(status_code=403,
                                detail=f"This action needs the {need} role; you are signed in as {user.role}.")
        return user
    dep.roles = roles        # read by the permission-matrix test
    return dep


def stand_in_user(role: str = CONTROLLER) -> SimpleNamespace:
    """A stand-in user for unit tests that do not exercise auth."""
    return SimpleNamespace(id=None, email=f"pytest-{role.lower()}@local", role=role, display_name="pytest",
                           is_active=True, token_version=0)


# ---------------------------------------------------------------------------
# login rate limiting
# ---------------------------------------------------------------------------
def lockout_until(db: Session, email: str, now: datetime | None = None) -> datetime | None:
    """After `login_max_failures` failed logins for one email within `login_window_min`
    minutes, further attempts are refused for `login_lockout_min` minutes after the last of
    them. Failures before the last successful login do not count; refused attempts are not
    failures (they do not extend the lockout)."""
    s = get_settings()
    now = now or datetime.now(timezone.utc)
    since = now - timedelta(minutes=s.login_window_min + s.login_lockout_min)
    rows = db.execute(select(m.AuditLog.action, m.AuditLog.at)
                      .where(m.AuditLog.email == email, m.AuditLog.at >= since,
                             m.AuditLog.action.in_(("LOGIN", "LOGIN_FAILED")))
                      .order_by(m.AuditLog.at)).all()
    fails: list[datetime] = []
    for action, at in rows:
        at = at if at.tzinfo else at.replace(tzinfo=timezone.utc)      # SQLite drops the zone
        if action == "LOGIN":
            fails = []
        else:
            fails.append(at)
    n = s.login_max_failures
    for k in range(len(fails) - n, -1, -1):
        window = fails[k:k + n]
        if window[-1] - window[0] < timedelta(minutes=s.login_window_min):
            until = window[-1] + timedelta(minutes=s.login_lockout_min)
            return until if until > now else None
    return None
