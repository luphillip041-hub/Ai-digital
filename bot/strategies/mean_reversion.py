"""Strategy 1 — Mean Reversion (SPY, QQQ) on 15-minute candles.

Entry:  price stretched more than `band_mult` standard deviations away from
        the 20-period SMA (1.5σ for SPY, 1.8σ for QQQ):
          below the lower band -> LONG (expect revert up)
          above the upper band -> SHORT (expect revert down)
Exit:   price returns to the moving average.
"""

from typing import Optional

import pandas as pd

from bot import indicators
from bot.strategies.base import EXIT, LONG, NONE, SHORT, Signal, Strategy


class MeanReversionStrategy(Strategy):
    required_bars = 60  # 20-period SMA/σ + 14-period ATR, with headroom

    def evaluate(self, bars: pd.DataFrame, position_direction: Optional[str]) -> Signal:
        if not self.has_enough_bars(bars):
            return Signal(NONE, "insufficient bars")

        period = self.params["sma_period"]
        band_mult = self.params["band_mult"]

        close = bars["close"]
        mean = indicators.sma(close, period).iloc[-1]
        std = indicators.rolling_std(close, period).iloc[-1]
        price = close.iloc[-1]

        if pd.isna(mean) or pd.isna(std) or std == 0:
            return Signal(NONE, "indicators not ready")

        upper = mean + band_mult * std
        lower = mean - band_mult * std

        # Exits first: revert-to-mean is the profit target.
        if position_direction == "long" and price >= mean:
            return Signal(EXIT, f"price {price:.2f} reverted to SMA {mean:.2f}")
        if position_direction == "short" and price <= mean:
            return Signal(EXIT, f"price {price:.2f} reverted to SMA {mean:.2f}")

        if position_direction is None:
            if price < lower:
                return Signal(
                    LONG,
                    f"price {price:.2f} < lower band {lower:.2f} "
                    f"({band_mult}σ below SMA {mean:.2f})",
                )
            if price > upper:
                return Signal(
                    SHORT,
                    f"price {price:.2f} > upper band {upper:.2f} "
                    f"({band_mult}σ above SMA {mean:.2f})",
                )

        return Signal(NONE)
