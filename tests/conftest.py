import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MPLBACKEND", "Agg")

import pytest

from astrotools_adv.core import tasks
from astrotools_adv.core.workspace import Workspace


@pytest.fixture(autouse=True)
def _sync_tasks():
    """Run background tasks inline so tests are deterministic."""
    tasks.set_synchronous(True)
    yield
    tasks.set_synchronous(False)


@pytest.fixture
def ws(qapp):
    return Workspace()
