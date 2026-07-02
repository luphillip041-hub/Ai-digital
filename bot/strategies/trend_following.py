"""Strategy 3 — Trend Following (GLD, USO) on 4-hour candles.

Entry:  50-period EMA crosses above the 200-period EMA (golden cross) -> LONG.
Exit:   50 EMA crosses below the 200 EMA (death cross) -> exit long and go
        SHORT. A 3x-ATR trailing stop (risk manager) protects open trends.

Signals fire only on the bar where the cross occurs; positions closed by a
trailing stop mid-trend are not re-entered until the next cross.
"""

from typing import Optional

import pandas as pd

from bot import indicators
from bot.strategies.base import LONG, NONE, SHORT, Signal, Strategy


class TrendFollowingStrategy(Strategy):
    # EMAs converge geometrically; ~3x the slow period gives a stable 200 EMA.
    required_bars = 600

    def evaluate(self, bars: pd.DataFrame, position_direction: Optional[str]) -> Signal:
        if not self.has_enough_bars(bars):
            return Signal(NONE, "insufficient bars")

        fast = indicators.ema(bars["close"], self.params["fast_ema"])
        slow = indicators.ema(bars["close"], self.params["slow_ema"])

        fast_now, fast_prev = fast.iloc[-1], fast.iloc[-2]
        slow_now, slow_prev = slow.iloc[-1], slow.iloc[-2]

        if pd.isna(fast_prev) or pd.isna(slow_prev):
            return Signal(NONE, "indicators not ready")

        golden_cross = fast_prev <= slow_prev and fast_now > slow_now
        death_cross = fast_prev >= slow_prev and fast_now < slow_now

        if golden_cross and position_direction != "long":
            return Signal(
                LONG,
                f"golden cross: 50 EMA {fast_now:.2f} crossed above "
                f"200 EMA {slow_now:.2f}",
            )

        if death_cross and position_direction != "short":
            return Signal(
                SHORT,
                f"death cross: 50 EMA {fast_now:.2f} crossed below "
                f"200 EMA {slow_now:.2f}",
            )

        return Signal(NONE)
