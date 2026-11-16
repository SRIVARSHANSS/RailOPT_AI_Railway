"""ADMIN API (Phase 8): users, audit log, network and train management."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.auth_routes import UserOut, normalise_email, user_out
from app.core.auth import ADMIN_ONLY, audit, require
from app.core.security import hash_password, password_problem
from app.core.store import CUSTOM_TIMETABLE, ScenarioStore, get_store
from app.db import models as m
from app.db.session import get_db
from app.services import netadmin

router = APIRouter(prefix="/api/admin", tags=["admin"])
Role = Literal["ADMIN", "CONTROLLER", "ANALYST"]
Kind = Literal["stations", "sections", "trains", "schedule"]
Corridor = Literal["reference", "full_day", "custom", "dg_mdu"]


# ---- users ------------------------------------------------------------------------------------
class UserCreate(BaseModel):
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+$")
    display_name: str = Field(min_length=1, max_length=120)
    role: Role
    password: str = Field(min_length=1, max_length=200)


class UserPatch(BaseModel):
    display_name: str | None = Field(None, min_length=1, max_length=120)
    role: Role | None = None
    is_active: bool | None = None


class PasswordReset(BaseModel):
    password: str = Field(min_length=1, max_length=200)


def _user(db: Session, user_id: int) -> m.User:
    u = db.get(m.User, user_id)
    if u is None:
        raise HTTPException(status_code=404, detail=f"No user with id {user_id}.")
    return u


def _active_admins(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(m.User).where(m.User.role == "ADMIN", m.User.is_active.is_(True)))


@router.get("/users", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), admin=Depends(require(*ADMIN_ONLY))):
    return [user_out(u) for u in db.scalars(select(m.User).order_by(m.User.id))]


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(req: UserCreate, request: Request, db: Session = Depends(get_db), admin=Depends(require(*ADMIN_ONLY))):
    email = normalise_email(req.email)
    if db.scalars(select(m.User).where(func.lower(m.User.email) == email)).first():
        raise HTTPException(status_code=409, detail=f"A user with email {email} already exists.")
    problem = password_problem(req.password)
    if problem:
        raise HTTPException(status_code=422, detail=problem)
    u = m.User(email=email, display_name=req.display_name.strip(), role=req.role,
               password_hash=hash_password(req.password), is_active=True, token_version=0)
    db.add(u)
    db.flush()
    audit(db, "USER_CREATED", user=admin, detail={"user_id": u.id, "email": email, "role": req.role}, request=request,
          commit=False)
    db.commit()
    return user_out(u)


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(user_id: int, req: UserPatch, request: Request, db: Session = Depends(get_db),
                admin=Depends(require(*ADMIN_ONLY))):
    u = _user(db, user_id)
    losing_admin = u.role == "ADMIN" and u.is_active and (
        (req.role is not None and req.role != "ADMIN") or req.is_active is False)
    if losing_admin and _active_admins(db) <= 1:
        raise HTTPException(status_code=409, detail="This is the last active admin; create another admin first.")
    changes = {}
    if req.display_name is not None and req.display_name != u.display_name:
        changes["display_name"] = [u.display_name, req.display_name]
        u.display_name = req.display_name.strip()
    if req.role is not None and req.role != u.role:
        changes["role"] = [u.role, req.role]
        u.role = req.role
        u.token_version += 1                     # the old role's sessions end
    if req.is_active is not None and req.is_active != u.is_active:
        changes["is_active"] = [u.is_active, req.is_active]
        u.is_active = req.is_active
        u.token_version += 1
    if changes:
        action = ("USER_DEACTIVATED" if changes.get("is_active") == [True, False] else
                  "USER_REACTIVATED" if changes.get("is_active") == [False, True] else
                  "USER_ROLE_CHANGED" if "role" in changes else "USER_UPDATED")
        audit(db, action, user=admin, detail={"user_id": u.id, "email": u.email, "changes": changes},
              request=request, commit=False)
    db.commit()
    return user_out(u)


@router.post("/users/{user_id}/password", response_model=UserOut)
def reset_password(user_id: int, req: PasswordReset, request: Request, db: Session = Depends(get_db),
                   admin=Depends(require(*ADMIN_ONLY))):
    u = _user(db, user_id)
    problem = password_problem(req.password)
    if problem:
        raise HTTPException(status_code=422, detail=problem)
    u.password_hash = hash_password(req.password)
    u.token_version += 1                         # every session of that user ends
    audit(db, "PASSWORD_RESET", user=admin, detail={"user_id": u.id, "email": u.email}, request=request, commit=False)
    db.commit()
    return user_out(u)


# ---- audit log -------------------------------------------------------------------------------
@router.get("/audit")
def audit_log(action: str | None = None, email: str | None = None,
              limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0),
              db: Session = Depends(get_db), admin=Depends(require(*ADMIN_ONLY))):
    q = select(m.AuditLog)
    if action:
        q = q.where(m.AuditLog.action == action)
    if email:
        q = q.where(m.AuditLog.email.ilike(f"%{email.strip()}%"))
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    rows = db.scalars(q.order_by(m.AuditLog.at.desc(), m.AuditLog.id.desc()).limit(limit).offset(offset)).all()
    actions = [a for (a,) in db.execute(select(m.AuditLog.action).distinct().order_by(m.AuditLog.action))]
    return {"total": total, "limit": limit, "offset": offset, "actions": actions,
            "rows": [{"id": r.id, "at": r.at.isoformat(timespec="seconds"), "user_id": r.user_id, "email": r.email,
                      "action": r.action, "detail": r.detail, "ip": r.ip} for r in rows]}


@router.get("/audit.csv")
def audit_csv(request: Request, action: str | None = None, email: str | None = None,
              db: Session = Depends(get_db), admin=Depends(require(*ADMIN_ONLY))):
    """The audit log (same filters as /audit, every matching row, newest first) as CSV."""
    import csv
    import io
    import json

    from fastapi.responses import Response
    q = select(m.AuditLog)
    if action:
        q = q.where(m.AuditLog.action == action)
    if email:
        q = q.where(m.AuditLog.email.ilike(f"%{email.strip()}%"))
    rows = db.scalars(q.order_by(m.AuditLog.at.desc(), m.AuditLog.id.desc())).all()
    buf = io.StringIO()
    buf.write("﻿")                          # BOM: spreadsheet programs then read UTF-8
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["id", "at_utc", "user_id", "email", "action", "ip", "detail"])
    for r in rows:
        w.writerow([r.id, r.at.isoformat(timespec="seconds"), r.user_id or "", r.email or "", r.action, r.ip or "",
                    json.dumps(r.detail or {}, sort_keys=True)])
    audit(db, "REPORT_EXPORTED", user=admin, request=request,
          detail={"report": "audit.csv", "action": action, "email": email, "rows": len(rows)})
    return Response(buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="railopt_audit_log.csv"'})


# ---- network and train management ------------------------------------------------------------
class TableRows(BaseModel):
    rows: list[dict[str, str | int | float | None]] = Field(max_length=netadmin.MAX_ROWS)


class CsvImport(BaseModel):
    csv: str = Field(max_length=1_000_000, description="CSV text with a header row")


def _corridor(name: str, db: Session) -> dict:
    tables = netadmin.db_tables(db) if name == netadmin.EDITABLE else netadmin.csv_tables(name)
    return {"name": name, **netadmin.sources(name), "columns": netadmin.COLUMNS, "tables": tables}


def _not_in_use(store: ScenarioStore) -> None:
    if store.timetable == CUSTOM_TIMETABLE:
        raise HTTPException(status_code=409, detail="The running scenario uses the custom corridor. Reset the "
                                                    "scenario to another timetable before editing it.")


def _saved(name: str, kind: str, ok: bool, errors: list[dict], db: Session, store: ScenarioStore,
           admin, request: Request, how: str, rows: int) -> dict:
    if not ok:
        audit(db, "NETWORK_IMPORT_REJECTED" if how == "import" else "NETWORK_EDIT_REJECTED", user=admin,
              detail={"table": kind, "rows": rows, "errors": len(errors)}, request=request)
        raise HTTPException(status_code=422, detail={
            "message": f"{len(errors)} problem(s) found; nothing was saved.", "errors": errors})
    store.forget_network(CUSTOM_TIMETABLE)
    audit(db, "NETWORK_IMPORTED" if how == "import" else "NETWORK_EDITED", user=admin,
          detail={"table": kind, "rows": rows}, request=request)
    return _corridor(name, db)


@router.get("/network/{name}")
def get_corridor(name: Corridor, db: Session = Depends(get_db), admin=Depends(require(*ADMIN_ONLY))):
    return _corridor(name, db)


@router.put("/network/custom/{kind}")
def edit_table(kind: Kind, req: TableRows, request: Request, db: Session = Depends(get_db),
               store: ScenarioStore = Depends(get_store), admin=Depends(require(*ADMIN_ONLY))):
    _not_in_use(store)
    ok, errors, _ = netadmin.replace_table(db, kind, [{k: "" if v is None else str(v) for k, v in r.items()}
                                                      for r in req.rows])
    return _saved("custom", kind, ok, errors, db, store, admin, request, "edit", len(req.rows))


@router.post("/network/custom/{kind}/import")
def import_csv(kind: Kind, req: CsvImport, request: Request, db: Session = Depends(get_db),
               store: ScenarioStore = Depends(get_store), admin=Depends(require(*ADMIN_ONLY))):
    _not_in_use(store)
    rows, errors = netadmin.parse_csv(kind, req.csv)
    if not errors:
        ok, errors, _ = netadmin.replace_table(db, kind, rows)
    else:
        ok = False
    return _saved("custom", kind, ok, errors, db, store, admin, request, "import", len(rows))


@router.post("/network/custom/reset")
def reset_custom(request: Request, db: Session = Depends(get_db), store: ScenarioStore = Depends(get_store),
                 admin=Depends(require(*ADMIN_ONLY))):
    _not_in_use(store)
    netadmin.reset_custom(db)
    store.forget_network(CUSTOM_TIMETABLE)
    audit(db, "NETWORK_RESET", user=admin, detail={"seed": netadmin.SEED}, request=request)
    return _corridor("custom", db)
