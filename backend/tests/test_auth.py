"""Phase 8 auth: bcrypt, JWT cookies, expiry + refresh, logout, roles, rate limiting, audit log,
and the role-by-endpoint permission matrix (every API route is classified and checked)."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from app.core import auth
from app.core.config import get_settings
from app.core.security import (MAX_PASSWORD_BYTES, decode_token, hash_password, make_token, password_problem,
                               verify_password, TokenError)
from app.core.store import ScenarioStore, get_store
from app.db import models as m
from app.db.session import session_factory
from app.main import app
from tests._authkit import PASSWORD, audit_rows, login, make_user

pytestmark = pytest.mark.real_auth

PUBLIC = "PUBLIC"
ANY = "ANY_SIGNED_IN"
READ, CONTROL, WHATIF, ADMIN = set(auth.READ), set(auth.CONTROL), set(auth.WHATIF), set(auth.ADMIN_ONLY)
ALERTS, REPORTS = set(auth.ALERTS), set(auth.REPORTS)
# every API route and who may call it (docs/ASSUMPTIONS.md 80)
MATRIX = {
    ("GET", "/api/health"): PUBLIC,
    ("POST", "/api/auth/login"): PUBLIC,
    ("POST", "/api/auth/refresh"): PUBLIC,
    ("POST", "/api/auth/logout"): PUBLIC,
    ("GET", "/api/auth/me"): ANY,
    ("GET", "/api/replay/days"): READ,
    ("GET", "/api/network"): READ,
    ("GET", "/api/scenario"): READ,
    ("GET", "/api/state"): READ,
    ("GET", "/api/conflicts"): READ,
    ("GET", "/api/timeline"): READ,
    ("GET", "/api/evaluation"): READ,
    ("GET", "/api/model"): READ,
    ("POST", "/api/scenario/reset"): CONTROL,
    ("POST", "/api/events"): CONTROL,
    ("POST", "/api/optimize"): CONTROL,
    ("POST", "/api/recommendation/{rec_id}/decision"): CONTROL,
    ("POST", "/api/whatif"): WHATIF,
    ("GET", "/api/admin/users"): ADMIN,
    ("POST", "/api/admin/users"): ADMIN,
    ("PATCH", "/api/admin/users/{user_id}"): ADMIN,
    ("POST", "/api/admin/users/{user_id}/password"): ADMIN,
    ("GET", "/api/admin/audit"): ADMIN,
    ("GET", "/api/admin/network/{name}"): ADMIN,
    ("PUT", "/api/admin/network/custom/{kind}"): ADMIN,
    ("POST", "/api/admin/network/custom/{kind}/import"): ADMIN,
    ("POST", "/api/admin/network/custom/reset"): ADMIN,
    ("GET", "/api/admin/audit.csv"): ADMIN,
    ("GET", "/api/alerts"): ALERTS,
    ("POST", "/api/alerts/ack"): CONTROL,
    ("GET", "/api/reports"): READ,
    ("GET", "/api/reports/scenario.pdf"): READ,
    ("GET", "/api/reports/scenario.csv"): READ,
    ("GET", "/api/reports/evaluation.pdf"): REPORTS,
    ("GET", "/api/reports/model.pdf"): REPORTS,
}
PATH_VALUES = {"{rec_id}": "R99", "{user_id}": "999999", "{name}": "reference", "{kind}": "stations"}
ROLES = ("ADMIN", "CONTROLLER", "ANALYST")


def api_routes():
    """Every API operation, from the OpenAPI schema (works with lazily included routers)."""
    return [(meth.upper(), path) for path, ops in app.openapi()["paths"].items() for meth in ops]


@pytest.fixture()
def client(monkeypatch):
    store = ScenarioStore()
    app.dependency_overrides[get_store] = lambda: store
    from app.services.realdata import replay
    monkeypatch.setattr(replay, "day_checks", lambda: [])      # keep the matrix fast
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(get_store, None)


@pytest.fixture(scope="module")
def users():
    return {role: make_user(role) for role in ROLES}


# ---- passwords ------------------------------------------------------------------------------------
def test_password_hashing():
    h = hash_password(PASSWORD)
    assert h.startswith("$2") and PASSWORD not in h
    assert verify_password(PASSWORD, h) and not verify_password(PASSWORD + "x", h)
    assert hash_password(PASSWORD) != h                         # a new salt every time
    assert password_problem("short") and password_problem("x" * (MAX_PASSWORD_BYTES + 1))
    with pytest.raises(ValueError):
        hash_password("short")


# ---- tokens ---------------------------------------------------------------------------------------
def test_token_expiry_and_type():
    s = get_settings()
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    old = make_token(user_id=1, role="ADMIN", token_version=0, kind="access", lifetime=timedelta(minutes=15),
                     secret=s.jwt_secret, now=past)
    with pytest.raises(TokenError) as e:
        decode_token(old, secret=s.jwt_secret, kind="access")
    assert e.value.expired
    fresh = make_token(user_id=1, role="ADMIN", token_version=0, kind="refresh", lifetime=timedelta(hours=8),
                       secret=s.jwt_secret)
    with pytest.raises(TokenError):
        decode_token(fresh, secret=s.jwt_secret, kind="access")       # a refresh token is not an access token
    with pytest.raises(TokenError):
        decode_token(fresh, secret="another-secret", kind="refresh")


def test_expired_access_token_then_refresh(client, users):
    u = users["ANALYST"]
    assert login(client, u.email).status_code == 200
    s = get_settings()
    expired = make_token(user_id=u.id, role=u.role, token_version=u.token_version, kind="access",
                         lifetime=timedelta(minutes=15), secret=s.jwt_secret,
                         now=datetime.now(timezone.utc) - timedelta(minutes=16))
    jar = next(c for c in client.cookies.jar if c.name == auth.ACCESS_COOKIE)
    client.cookies.set(auth.ACCESS_COOKIE, expired, domain=jar.domain, path=jar.path)
    r = client.get("/api/auth/me")
    assert r.status_code == 401 and r.headers.get("X-Session-Expired") == "1" and "expired" in r.json()["detail"]
    assert client.post("/api/auth/refresh").status_code == 200       # refresh cookie -> new access cookie
    assert client.get("/api/auth/me").json()["role"] == "ANALYST"


def test_cookies_are_httponly_and_lax(client, users):
    r = login(client, users["CONTROLLER"].email)
    cookies = r.headers.get_list("set-cookie")
    assert any(c.startswith(auth.ACCESS_COOKIE) for c in cookies)
    for c in cookies:
        low = c.lower()
        assert "httponly" in low and "samesite=lax" in low
    assert any("path=/api/auth" in c.lower() for c in cookies if c.startswith(auth.REFRESH_COOKIE))


# ---- login, logout, roles ---------------------------------------------------------------------------
def test_login_logout_and_audit(client):
    u = make_user("CONTROLLER")
    bad = login(client, u.email, "wrong password!!")
    assert bad.status_code == 401 and bad.json()["detail"] == "Wrong email or password."
    assert login(client, "nobody@test.local").json()["detail"] == "Wrong email or password."
    ok = login(client, u.email.upper())                              # emails are case-insensitive
    assert ok.status_code == 200 and ok.json()["role"] == "CONTROLLER"
    old = client.cookies.get(auth.ACCESS_COOKIE)
    assert client.get("/api/auth/me").status_code == 200
    assert client.post("/api/auth/logout").json() == {"signed_out": True}
    client.cookies.set(auth.ACCESS_COOKIE, old, domain="testserver.local", path="/")   # an old token after logout
    r = client.get("/api/auth/me")
    assert r.status_code == 401 and "Session ended" in r.json()["detail"]
    actions = [a.action for a in audit_rows(email=u.email)]
    assert actions == ["LOGIN_FAILED", "LOGIN", "LOGOUT"]


def test_unauthenticated_and_forbidden_messages(client, users):
    r = client.get("/api/scenario")
    assert r.status_code == 401 and r.json()["detail"] == "Not signed in. Sign in to use RailOpt AI."
    login(client, users["ANALYST"].email)
    r = client.post("/api/events", json={})
    assert r.status_code == 403
    assert r.json()["detail"] == "This action needs the CONTROLLER role; you are signed in as ANALYST."


def test_deactivated_user_cannot_sign_in_and_loses_session(client, users):
    admin = users["ADMIN"]
    u = make_user("ANALYST")
    other = TestClient(app)
    assert login(other, u.email).status_code == 200
    login(client, admin.email)
    assert client.patch(f"/api/admin/users/{u.id}", json={"is_active": False}).status_code == 200
    assert other.get("/api/auth/me").status_code == 401             # its session ended at once
    r = login(other, u.email)
    assert r.status_code == 401 and "deactivated" in r.json()["detail"]
    row = audit_rows(email=admin.email, action="USER_DEACTIVATED")[-1]   # logged as the admin's action
    assert row.detail["email"] == u.email and row.detail["changes"]["is_active"] == [True, False]


def test_admin_user_management(client, users):
    login(client, users["ADMIN"].email)
    r = client.post("/api/admin/users", json={"email": "New.Person@Test.local", "display_name": "New Person",
                                              "role": "ANALYST", "password": "a long enough pw"})
    assert r.status_code == 201 and r.json()["email"] == "new.person@test.local"
    uid = r.json()["id"]
    assert client.post("/api/admin/users", json={"email": "new.person@test.local", "display_name": "x",
                                                 "role": "ANALYST", "password": "a long enough pw"}).status_code == 409
    assert client.post("/api/admin/users", json={"email": "p2@test.local", "display_name": "x", "role": "ANALYST",
                                                 "password": "short"}).status_code == 422
    assert client.patch(f"/api/admin/users/{uid}", json={"role": "CONTROLLER"}).json()["role"] == "CONTROLLER"
    assert client.post(f"/api/admin/users/{uid}/password", json={"password": "another long pw"}).status_code == 200
    other = TestClient(app)
    assert login(other, "new.person@test.local", "another long pw").json()["role"] == "CONTROLLER"
    users_list = client.get("/api/admin/users").json()
    assert all("password" not in k for u in users_list for k in u)
    mine = client.get("/api/admin/audit", params={"email": users["ADMIN"].email, "limit": 500}).json()
    about = {r["action"] for r in mine["rows"] if r["detail"].get("email") == "new.person@test.local"}
    assert {"USER_CREATED", "USER_ROLE_CHANGED", "PASSWORD_RESET"} <= about
    theirs = client.get("/api/admin/audit", params={"email": "new.person"}).json()
    assert {r["action"] for r in theirs["rows"]} == {"LOGIN"}


def test_last_admin_cannot_be_removed(client):
    with session_factory()() as db:                                  # only one active admin in this test
        db.execute(update(m.User).where(m.User.role == "ADMIN").values(is_active=False))
        db.commit()
    admin = make_user("ADMIN")
    login(client, admin.email)
    r = client.patch(f"/api/admin/users/{admin.id}", json={"role": "ANALYST"})
    assert r.status_code == 409 and "last active admin" in r.json()["detail"]
    with session_factory()() as db:
        db.execute(update(m.User).where(m.User.role == "ADMIN").values(is_active=True))
        db.commit()


# ---- rate limiting ----------------------------------------------------------------------------------
def test_login_rate_limit(client):
    u = make_user("ANALYST")
    for _ in range(5):
        assert login(client, u.email, "wrong password!!").status_code == 401
    r = login(client, u.email)                                       # even the right password is refused
    assert r.status_code == 429
    assert r.json()["detail"].startswith("Too many failed sign-in attempts for this account. Try again in")
    assert int(r.headers["Retry-After"]) > 0
    assert audit_rows(email=u.email, action="LOGIN_RATE_LIMITED")
    # 16 minutes later the lockout is over
    with session_factory()() as db:
        db.execute(update(m.AuditLog).where(m.AuditLog.email == u.email)
                   .values(at=datetime.now(timezone.utc) - timedelta(minutes=16)))
        db.commit()
    assert login(client, u.email).status_code == 200
    # failures spread over more than 15 minutes do not lock
    v = make_user("ANALYST")
    for k in range(5):
        login(client, v.email, "wrong password!!")
        with session_factory()() as db:
            for row in db.scalars(select(m.AuditLog).where(m.AuditLog.email == v.email,
                                                          m.AuditLog.action == "LOGIN_FAILED")):
                row.at = row.at - timedelta(minutes=4)
            db.commit()
    assert login(client, v.email).status_code == 200


# ---- decisions are logged with the user ------------------------------------------------------------
def test_decision_logged_with_user(client, users):
    u = users["CONTROLLER"]
    login(client, u.email)
    client.post("/api/scenario/reset", json={"timetable": "reference"})
    client.post("/api/events", json={"event_type": "STOPPAGE", "train_id": "T101", "location": "S_BC",
                                     "start_time": "10:03", "duration_min": 15})
    rec = client.post("/api/optimize", json={"at": "10:03"}).json()["recommendation"]
    d = client.post(f"/api/recommendation/{rec['recommendation_id']}/decision", json={"decision": "accept"}).json()
    assert d["decision_log"][-1]["decided_by"] == u.email
    row = audit_rows(email=u.email, action="DECISION")[-1]
    assert row.detail["recommendation_id"] == rec["recommendation_id"] and row.detail["decision"] == "accept"
    assert audit_rows(email=u.email, action="EVENT_ADDED") and audit_rows(email=u.email, action="SCENARIO_RESET")


# ---- permission matrix --------------------------------------------------------------------------------
def test_every_route_is_classified():
    assert set(api_routes()) == set(MATRIX), set(api_routes()) ^ set(MATRIX)


def _call(client, method, path):
    url = path
    for k, v in PATH_VALUES.items():
        url = url.replace(k, v)
    if method == "GET":
        return client.get(url)
    return client.request(method, url, json={})


@pytest.mark.parametrize("method,path", sorted(MATRIX))
def test_permission_matrix(client, users, method, path):
    rule = MATRIX[(method, path)]
    anon = _call(client, method, path)
    if rule == PUBLIC:
        assert anon.status_code not in (403,), (method, path, anon.status_code)
        return
    assert anon.status_code == 401, (method, path, anon.status_code)
    for role in ROLES:
        c = TestClient(app)
        assert login(c, users[role].email).status_code == 200
        r = _call(c, method, path)
        allowed = rule == ANY or role in rule
        if allowed:
            assert r.status_code not in (401, 403), (method, path, role, r.status_code, r.text[:200])
        else:
            assert r.status_code == 403, (method, path, role, r.status_code)
            assert f"you are signed in as {role}" in r.json()["detail"]
