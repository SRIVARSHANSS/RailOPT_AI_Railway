"""POST /api/auth/login, /refresh, /logout and GET /api/auth/me (Phase 8)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import ACCESS_COOKIE, REFRESH_COOKIE, REFRESH_PATH, audit, current_user, lockout_until
from app.core.config import get_settings
from app.core.security import TokenError, burn_time, decode_token, make_token, verify_password
from app.db import models as m
from app.db.session import get_db

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=200)


class UserOut(BaseModel):
    id: int | None
    email: str
    display_name: str
    role: str
    is_active: bool = True
    last_login_at: datetime | None = None
    created_at: datetime | None = None


def user_out(u) -> UserOut:
    return UserOut(id=u.id, email=u.email, display_name=u.display_name, role=u.role, is_active=u.is_active,
                   last_login_at=getattr(u, "last_login_at", None), created_at=getattr(u, "created_at", None))


def _set_session(response: Response, user: m.User) -> None:
    s = get_settings()
    access = make_token(user_id=user.id, role=user.role, token_version=user.token_version, kind="access",
                        lifetime=timedelta(minutes=s.access_token_min), secret=s.jwt_secret)
    refresh = make_token(user_id=user.id, role=user.role, token_version=user.token_version, kind="refresh",
                         lifetime=timedelta(hours=s.refresh_token_hours), secret=s.jwt_secret)
    common = {"httponly": True, "samesite": "lax", "secure": s.cookie_secure}
    response.set_cookie(ACCESS_COOKIE, access, max_age=s.access_token_min * 60, path="/", **common)
    response.set_cookie(REFRESH_COOKIE, refresh, max_age=s.refresh_token_hours * 3600, path=REFRESH_PATH, **common)


def _clear_session(response: Response) -> None:
    s = get_settings()
    response.delete_cookie(ACCESS_COOKIE, path="/", httponly=True, samesite="lax", secure=s.cookie_secure)
    response.delete_cookie(REFRESH_COOKIE, path=REFRESH_PATH, httponly=True, samesite="lax", secure=s.cookie_secure)


def normalise_email(email: str) -> str:
    return email.strip().lower()


@router.post("/login", response_model=UserOut)
def login(req: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    email = normalise_email(req.email)
    until = lockout_until(db, email)
    if until is not None:
        wait = max(1, int((until - datetime.now(timezone.utc)).total_seconds() // 60) + 1)
        audit(db, "LOGIN_RATE_LIMITED", email=email, detail={"until_utc": until.isoformat(timespec="seconds")},
              request=request)
        raise HTTPException(status_code=429, headers={"Retry-After": str(wait * 60)},
                            detail=f"Too many failed sign-in attempts for this account. Try again in {wait} min.")
    user = db.scalars(select(m.User).where(func.lower(m.User.email) == email)).first()
    if user is None:
        burn_time(req.password)
    if user is None or not verify_password(req.password, user.password_hash):
        audit(db, "LOGIN_FAILED", email=email, detail={"reason": "wrong email or password"}, request=request)
        raise HTTPException(status_code=401, detail="Wrong email or password.")
    if not user.is_active:
        audit(db, "LOGIN_FAILED", user=user, detail={"reason": "account deactivated"}, request=request)
        raise HTTPException(status_code=401, detail="This account is deactivated. Ask an administrator.")
    user.last_login_at = datetime.now(timezone.utc)
    audit(db, "LOGIN", user=user, detail={"role": user.role}, request=request, commit=False)
    db.commit()
    _set_session(response, user)
    return user_out(user)


@router.post("/refresh", response_model=UserOut)
def refresh(request: Request, response: Response, db: Session = Depends(get_db)):
    token = request.cookies.get(REFRESH_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="Not signed in. Sign in to use RailOpt AI.")
    try:
        claims = decode_token(token, secret=get_settings().jwt_secret, kind="refresh")
    except TokenError as exc:
        _clear_session(response)
        raise HTTPException(status_code=401, detail=str(exc))
    user = db.get(m.User, int(claims["sub"]))
    if user is None or not user.is_active or user.token_version != claims.get("tv"):
        raise HTTPException(status_code=401, detail="Session ended - sign in again.")
    _set_session(response, user)
    return user_out(user)


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    """Ends every session of the user (token_version + 1) and clears the cookies."""
    s = get_settings()
    user = None
    for cookie, kind in ((ACCESS_COOKIE, "access"), (REFRESH_COOKIE, "refresh")):
        token = request.cookies.get(cookie)
        if token and user is None:
            try:
                claims = decode_token(token, secret=s.jwt_secret, kind=kind)
            except TokenError:
                continue
            u = db.get(m.User, int(claims["sub"]))
            if u is not None and u.token_version == claims.get("tv"):
                user = u
    if user is not None:
        user.token_version += 1
        audit(db, "LOGOUT", user=user, request=request, commit=False)
        db.commit()
    _clear_session(response)
    return {"signed_out": True}


@router.get("/me", response_model=UserOut)
def me(user=Depends(current_user)):
    return user_out(user)
