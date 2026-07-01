"""Feature engineering: turn OHLCV bars into a supervised learning dataset.

All features are computed strictly from information available at the close of
day t; the label is the direction of the close-to-close return of day t+1, so
there is no look-ahead leakage.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

FEATURE_COLUMNS = [
    "ret_1d",
    "ret_5d",
    "ret_10d",
    "ret_21d",
    "sma10_ratio",
    "sma50_ratio",
    "ema12_26_diff",
    "rsi_14",
    "boll_z",
    "vol_21d",
    "volume_z",
    "hl_range",
]
LABEL_COLUMN = "target_up"
FWD_RETURN_COLUMN = "fwd_ret_1d"


def rsi(close: pd.Series, window: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(window).mean()
    loss = (-delta.clip(upper=0)).rolling(window).mean()
    rs = gain / loss.replace(0, np.nan)
    out = 100 - 100 / (1 + rs)
    return out.fillna(50.0)


def build_features(bars: pd.DataFrame) -> pd.DataFrame:
    """Return a DataFrame of FEATURE_COLUMNS (no label), aligned to bars.index."""
    close = bars["close"]
    volume = bars["volume"]
    feats = pd.DataFrame(index=bars.index)

    feats["ret_1d"] = close.pct_change(1)
    feats["ret_5d"] = close.pct_change(5)
    feats["ret_10d"] = close.pct_change(10)
    feats["ret_21d"] = close.pct_change(21)

    feats["sma10_ratio"] = close / close.rolling(10).mean() - 1
    feats["sma50_ratio"] = close / close.rolling(50).mean() - 1

    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    feats["ema12_26_diff"] = (ema12 - ema26) / close

    feats["rsi_14"] = rsi(close) / 100.0

    sma20 = close.rolling(20).mean()
    std20 = close.rolling(20).std()
    feats["boll_z"] = (close - sma20) / std20.replace(0, np.nan)

    feats["vol_21d"] = close.pct_change().rolling(21).std()
    vol_mean = volume.rolling(21).mean()
    vol_std = volume.rolling(21).std()
    feats["volume_z"] = (volume - vol_mean) / vol_std.replace(0, np.nan)

    feats["hl_range"] = (bars["high"] - bars["low"]) / close

    return feats[FEATURE_COLUMNS]


def build_dataset(bars: pd.DataFrame) -> pd.DataFrame:
    """Features + next-day forward return and binary up/down label.

    The last row (which has no known future return) is dropped, as are the
    warm-up rows with incomplete rolling windows.
    """
    feats = build_features(bars)
    fwd = bars["close"].pct_change().shift(-1)
    ds = feats.copy()
    ds[FWD_RETURN_COLUMN] = fwd
    ds[LABEL_COLUMN] = (fwd > 0).astype(int)
    ds = ds.dropna()
    return ds
