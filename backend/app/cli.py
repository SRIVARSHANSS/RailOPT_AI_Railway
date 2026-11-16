"""User administration from the command line (Phase 8). Run from backend/ after migrating.

    python -m app.cli create-admin --email admin@example.org --name "Admin"
    python -m app.cli create-user  --email ctl@example.org --name "Controller" --role CONTROLLER
    python -m app.cli list-users

Passwords are typed at a hidden prompt (twice), never passed on the command line or stored in
the repository. The first admin can also come from RAILOPT_ADMIN_EMAIL / RAILOPT_ADMIN_PASSWORD
in backend/.env: it is created when the API starts and no admin exists yet."""
from __future__ import annotations

import argparse
import getpass
import logging
import os
import sys

from sqlalchemy import func, select

from app.core.security import hash_password, password_problem
from app.db import models as m
from app.db.session import session_factory

log = logging.getLogger("railopt.cli")


def create_user(email: str, name: str, role: str, password: str, *, via: str) -> m.User:
    email = email.strip().lower()
    if role not in m.ROLES:
        raise ValueError(f"role must be one of {', '.join(m.ROLES)}")
    problem = password_problem(password)
    if problem:
        raise ValueError(problem)
    with session_factory()() as db:
        if db.scalars(select(m.User).where(func.lower(m.User.email) == email)).first():
            raise ValueError(f"a user with email {email} already exists")
        user = m.User(email=email, display_name=name, role=role, password_hash=hash_password(password),
                      is_active=True, token_version=0)
        db.add(user)
        db.flush()
        db.add(m.AuditLog(user_id=user.id, email=email, action="USER_CREATED",
                          detail={"user_id": user.id, "email": email, "role": role, "via": via}))
        db.commit()
        return user


def admin_from_env() -> None:
    """Create the first admin from the environment, only when both variables are set and no
    admin exists yet. Never logs the password."""
    from app.core.config import get_settings
    get_settings()                                   # loads backend/.env
    email, password = os.environ.get("RAILOPT_ADMIN_EMAIL"), os.environ.get("RAILOPT_ADMIN_PASSWORD")
    if not email or not password:
        return
    try:
        with session_factory()() as db:
            if db.scalar(select(func.count()).select_from(m.User).where(m.User.role == "ADMIN")):
                return
        create_user(email, "Administrator", "ADMIN", password, via="environment")
        log.warning("first admin %s created from RAILOPT_ADMIN_EMAIL; remove RAILOPT_ADMIN_PASSWORD from .env", email)
    except Exception as exc:                         # e.g. not migrated yet: the API still starts
        log.error("could not create the first admin from the environment: %s", exc)


def _ask_password() -> str:
    while True:
        a = getpass.getpass("Password (hidden): ")
        problem = password_problem(a)
        if problem:
            print(problem)
            continue
        if getpass.getpass("Repeat password: ") != a:
            print("The two passwords differ; try again.")
            continue
        return a


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m app.cli", description="RailOpt AI user administration")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("create-admin", help="create an ADMIN user (prompts for the password)")
    a.add_argument("--email", required=True)
    a.add_argument("--name", default="Administrator")
    u = sub.add_parser("create-user", help="create a user with a role (prompts for the password)")
    u.add_argument("--email", required=True)
    u.add_argument("--name", required=True)
    u.add_argument("--role", required=True, choices=m.ROLES)
    sub.add_parser("list-users", help="list users (no passwords)")
    args = p.parse_args(argv)
    try:
        if args.cmd == "list-users":
            with session_factory()() as db:
                for x in db.scalars(select(m.User).order_by(m.User.id)):
                    print(f"{x.id:>3}  {x.role:<10}  {'active' if x.is_active else 'inactive':<8}  {x.email}  ({x.display_name})")
            return 0
        role = "ADMIN" if args.cmd == "create-admin" else args.role
        user = create_user(args.email, args.name, role, _ask_password(), via="cli")
        print(f"Created {user.role} {user.email} (id {user.id}).")
        return 0
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
