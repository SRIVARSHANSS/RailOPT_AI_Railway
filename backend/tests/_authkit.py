"""Helpers for the Phase 8 auth tests: real users in the test database, real cookie sessions."""
from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.security import hash_password
from app.db import models as m
from app.db.session import session_factory

PASSWORD = "correct horse battery staple"


def make_user(role: str, *, email: str | None = None, password: str = PASSWORD, active: bool = True) -> m.User:
    email = email or f"{role.lower()}-{uuid.uuid4().hex[:8]}@test.local"
    with session_factory()() as db:
        u = m.User(email=email, display_name=f"Test {role.title()}", role=role, password_hash=hash_password(password),
                   is_active=active, token_version=0)
        db.add(u)
        db.commit()
        return u


def login(client: TestClient, email: str, password: str = PASSWORD):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def audit_rows(email: str | None = None, action: str | None = None) -> list[m.AuditLog]:
    with session_factory()() as db:
        q = select(m.AuditLog).order_by(m.AuditLog.id)
        if email:
            q = q.where(m.AuditLog.email == email)
        if action:
            q = q.where(m.AuditLog.action == action)
        return list(db.scalars(q))
