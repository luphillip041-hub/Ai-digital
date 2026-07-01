"""Market data: historical daily bars from Alpaca, plus a synthetic generator
so the pipeline can be developed and tested without API keys."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from .config import Settings

BAR_COLUMNS = ["open", "high", "low", "close", "volume"]


def fetch_daily_bars(settings: Settings, symbol: str, years: float = 5.0) -> pd.DataFrame:
    """Fetch daily OHLCV bars for one symbol from Alpaca.

    Returns a DataFrame indexed by date with columns open/high/low/close/volume.
    """
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    settings.require_keys()
    client = StockHistoricalDataClient(settings.api_key, settings.secret_key)
    end = datetime.now(timezone.utc) - timedelta(minutes=16)  # free plan excludes last 15 min
    start = end - timedelta(days=int(years * 365.25))
    request = StockBarsRequest(
        symbol_or_symbols=symbol,
        timeframe=TimeFrame.Day,
        start=start,
        end=end,
    )
    bars = client.get_stock_bars(request).df
    if bars.empty:
        raise ValueError(f"No bars returned for {symbol}")
    df = bars.xs(symbol, level="symbol")[BAR_COLUMNS].copy()
    df.index = pd.to_datetime(df.index).tz_convert("UTC").normalize().tz_localize(None)
    df.index.name = "date"
    return df


def synthetic_daily_bars(
    n_days: int = 1500,
    seed: int = 7,
    drift: float = 0.0003,
    vol: float = 0.012,
    start_price: float = 100.0,
) -> pd.DataFrame:
    """Geometric-Brownian-ish daily bars with mild autocorrelation, for tests
    and offline backtests."""
    rng = np.random.default_rng(seed)
    shocks = rng.normal(drift, vol, n_days)
    # Add slight momentum so a model has something learnable.
    for i in range(1, n_days):
        shocks[i] += 0.10 * shocks[i - 1]
    close = start_price * np.exp(np.cumsum(shocks))
    open_ = np.empty(n_days)
    open_[0] = start_price
    open_[1:] = close[:-1] * np.exp(rng.normal(0, vol / 4, n_days - 1))
    spread = np.abs(rng.normal(0, vol, n_days)) * close
    high = np.maximum(open_, close) + spread
    low = np.minimum(open_, close) - spread
    volume = rng.integers(1_000_000, 5_000_000, n_days).astype(float)
    index = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n_days, name="date")
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=index,
    )
