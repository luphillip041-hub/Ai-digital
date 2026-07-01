import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mltrader.data import synthetic_daily_bars  # noqa: E402


@pytest.fixture(scope="session")
def bars():
    return synthetic_daily_bars(n_days=1500, seed=7)
