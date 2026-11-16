import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.services.network import load_network  # noqa: E402


@pytest.fixture
def net():
    return load_network(BACKEND / "data")


# ---- Phase 8: database and auth for tests ------------------------------------------------------
# Every test runs against a throwaway in-memory SQLite database (never the real one). Tests that
# do not exercise auth are signed in as a CONTROLLER stand-in; mark a test `real_auth` to use the
# real cookie/JWT dependency instead.
import os  # noqa: E402

os.environ.setdefault("JWT_SECRET", "pytest-only-secret-not-for-production-use-0123456789")

from app.core import auth as _auth  # noqa: E402
from app.db import models as _models  # noqa: E402
from app.db.session import make_engine, set_engine  # noqa: E402


def pytest_configure(config):
    config.addinivalue_line("markers", "real_auth: use the real auth dependency (no stand-in user)")
    config.addinivalue_line("markers", "postgres: needs TEST_DATABASE_URL (a throwaway PostgreSQL database)")


@pytest.fixture(scope="session", autouse=True)
def _test_database():
    engine = make_engine("sqlite://")
    _models.Base.metadata.create_all(engine)
    set_engine(engine)
    yield engine
    set_engine(None)


@pytest.fixture(autouse=True)
def _signed_in(request):
    from app.main import app
    if request.node.get_closest_marker("real_auth"):
        app.dependency_overrides.pop(_auth.current_user, None)
        yield
        return
    app.dependency_overrides[_auth.current_user] = lambda: _auth.stand_in_user("CONTROLLER")
    yield
    app.dependency_overrides.pop(_auth.current_user, None)
