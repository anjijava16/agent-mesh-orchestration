import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from refundry import store  # noqa: E402


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "live: runs against the already-running network and shares its database")


@pytest.fixture(autouse=True)
def clean_db(request):
    """Give every unit test an empty database.

    Tests marked `live` are exempt: they talk to the running network over HTTP
    and share its database, so resetting here would delete the very rows they
    are about to assert on.
    """
    if request.node.get_closest_marker("live"):
        yield
        return
    store.reset()
    yield
    store.reset()
