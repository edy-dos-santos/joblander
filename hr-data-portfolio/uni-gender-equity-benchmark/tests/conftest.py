import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from benchmark import analysis  # noqa: E402


@pytest.fixture(scope="session")
def results():
    return analysis.run()
