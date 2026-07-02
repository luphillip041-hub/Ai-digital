"""Shared technical indicators, computed on pandas OHLCV DataFrames.

All functions expect a DataFrame with columns: open, high, low, close, volume,
indexed by bar timestamp, oldest row first.
"""

import pandas as pd


def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(period).mean()


def rolling_std(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(period).std(ddof=0)


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def true_range(bars: pd.DataFrame) -> pd.Series:
    prev_close = bars["close"].shift(1)
    tr = pd.concat(
        [
            bars["high"] - bars["low"],
            (bars["high"] - prev_close).abs(),
            (bars["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr


def atr(bars: pd.DataFrame, period: int = 14) -> pd.Series:
    """Wilder's Average True Range."""
    return true_range(bars).ewm(alpha=1.0 / period, adjust=False).mean()


def rolling_high(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(period).max()


def rolling_low(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(period).min()
