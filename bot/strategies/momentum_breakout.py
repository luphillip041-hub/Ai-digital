"""Strategy 2 — Momentum Breakout (BTC/USD) on 1-hour candles.

Entry:  close breaks above the prior 20-period high AND the bar's volume is
        at least 1.5x the prior 20-period average volume -> LONG.
        Close breaks below the prior 20-period low with the same volume
        confirmation -> SHORT (Alpaca can't short crypto, so execution turns
        this into "exit long" — see main.py / config "shortable").
Exit:   opposite breakout, or the 2x-ATR trailing stop managed by the
        risk manager.

The prior high/low and average volume exclude the breakout bar itself
(rolling window shifted by one) so the bar can't confirm its own breakout.
"""

from typing import Optional

import pandas as pd

from bot import indicators
from bot.strategies.base import LONG, NONE, SHORT, Signal, Strategy


class MomentumBreakoutStrategy(Strategy):
    required_bars = 60  # 20-bar channel (+1 shift) + ATR warm-up

    def evaluate(self, bars: pd.DataFrame, position_direction: Optional[str]) -> Signal:
        if not self.has_enough_bars(bars):
            return Signal(NONE, "insufficient bars")

        lookback = self.params["lookback"]
        volume_mult = self.params["volume_mult"]

        # Channel and volume baseline from bars *before* the current one.
        prior_high = indicators.rolling_high(bars["high"], lookback).shift(1).iloc[-1]
        prior_low = indicators.rolling_low(bars["low"], lookback).shift(1).iloc[-1]
        avg_volume = indicators.sma(bars["volume"], lookback).shift(1).iloc[-1]

        price = bars["close"].iloc[-1]
        volume = bars["volume"].iloc[-1]

        if pd.isna(prior_high) or pd.isna(prior_low) or pd.isna(avg_volume):
            return Signal(NONE, "indicators not ready")

        volume_confirmed = avg_volume > 0 and volume >= volume_mult * avg_volume

        if price > prior_high and volume_confirmed and position_direction != "long":
            return Signal(
                LONG,
                f"close {price:.2f} broke above {lookback}-bar high {prior_high:.2f}, "
                f"volume {volume:.0f} >= {volume_mult}x avg {avg_volume:.0f}",
            )

        if price < prior_low and volume_confirmed and position_direction != "short":
            # SHORT doubles as the long exit; execution downgrades it to EXIT
            # on non-shortable assets (crypto).
            return Signal(
                SHORT,
                f"close {price:.2f} broke below {lookback}-bar low {prior_low:.2f}, "
                f"volume {volume:.0f} >= {volume_mult}x avg {avg_volume:.0f}",
            )

        return Signal(NONE)
