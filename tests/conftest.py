import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import output_handler as oh  # noqa: E402


@pytest.fixture(autouse=True)
def empty_store():
    """The listing store is in memory: every test starts with it empty."""
    oh.clear_all()
    yield
    oh.clear_all()
