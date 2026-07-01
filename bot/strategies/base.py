"""Strategy interface.

A strategy is a pure function of (historical completed bars, current position)
returning a Signal. It never talks to the broker and never sizes positions —
execution and risk live in main.py / risk_manager.py so every strategy gets
identical risk treatment.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

import pandas as pd

# Signal actions
LONG = "long"
SHORT = "short"
EXIT = "exit"
NONE = "none"


@dataclass
class Signal:
    action: str  # one of LONG / SHORT / EXIT / NONE
    reason: str = ""


class Strategy(ABC):
    #: minimum number of completed bars required before signals are valid
    required_bars: int = 50

    def __init__(self, symbol: str, params: dict):
        self.symbol = symbol
        self.params = params

    @abstractmethod
    def evaluate(self, bars: pd.DataFrame, position_direction: Optional[str]) -> Signal:
        """Return a Signal given completed bars (oldest first) and the current
        position direction ("long", "short", or None if flat)."""
        raise NotImplementedError

    def has_enough_bars(self, bars: pd.DataFrame) -> bool:
        return len(bars) >= self.required_bars
