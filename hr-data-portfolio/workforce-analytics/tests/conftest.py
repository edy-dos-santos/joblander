import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from workforce import analysis  # noqa: E402


@pytest.fixture(scope="session")
def results():
    """Analysis results for the committed clean dataset."""
    return analysis.run()
