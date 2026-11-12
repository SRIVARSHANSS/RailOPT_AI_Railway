import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.services.network import load_network  # noqa: E402


@pytest.fixture
def net():
    return load_network(BACKEND / "data")
