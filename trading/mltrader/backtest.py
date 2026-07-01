"""Walk-forward backtest.

The model is retrained on a rolling window and then used to trade the
following out-of-sample block, repeatedly, so every traded day is genuinely
out of sample. Strategy is long/flat: hold the asset the day after the model
says P(up) >= threshold, otherwise stay in cash.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .features import FEATURE_COLUMNS, FWD_RETURN_COLUMN, build_dataset
from .model import predict_proba_up, train

TRADING_DAYS = 252


@dataclass
class BacktestResult:
    equity: pd.Series          # strategy equity curve (starts at 1.0)
    benchmark: pd.Series       # buy & hold equity curve
    daily_returns: pd.Series   # strategy daily returns (after costs)
    positions: pd.Series       # 0/1 exposure actually held each day
    proba: pd.Series           # model P(up) each day

    @property
    def total_return(self) -> float:
        return float(self.equity.iloc[-1] - 1)

    @property
    def cagr(self) -> float:
        years = len(self.equity) / TRADING_DAYS
        return float(self.equity.iloc[-1] ** (1 / years) - 1) if years > 0 else 0.0

    @property
    def sharpe(self) -> float:
        r = self.daily_returns
        if r.std() == 0:
            return 0.0
        return float(r.mean() / r.std() * np.sqrt(TRADING_DAYS))

    @property
    def max_drawdown(self) -> float:
        peak = self.equity.cummax()
        return float((self.equity / peak - 1).min())

    @property
    def hit_rate(self) -> float:
        """Fraction of invested days with a positive return."""
        invested = self.daily_returns[self.positions == 1]
        if len(invested) == 0:
            return 0.0
        return float((invested > 0).mean())

    @property
    def exposure(self) -> float:
        return float(self.positions.mean())

    def summary(self) -> str:
        bench_total = float(self.benchmark.iloc[-1] - 1)
        lines = [
            f"days traded        {len(self.equity)}",
            f"total return       {self.total_return:+.1%}   (buy & hold {bench_total:+.1%})",
            f"CAGR               {self.cagr:+.1%}",
            f"Sharpe             {self.sharpe:.2f}",
            f"max drawdown       {self.max_drawdown:.1%}",
            f"hit rate           {self.hit_rate:.1%}",
            f"time in market     {self.exposure:.1%}",
        ]
        return "\n".join(lines)


def walk_forward_backtest(
    bars: pd.DataFrame,
    train_window: int = 504,       # ~2 years
    test_window: int = 63,         # ~1 quarter per refit
    entry_threshold: float = 0.55,
    cost_bps: float = 5.0,         # round-trip cost per position change, in bps
    random_state: int = 0,
) -> BacktestResult:
    ds = build_dataset(bars)
    if len(ds) <= train_window + test_window:
        raise ValueError(
            f"Not enough data: {len(ds)} usable rows, need > {train_window + test_window}"
        )

    proba_chunks: list[pd.Series] = []
    start = train_window
    while start < len(ds):
        train_ds = ds.iloc[start - train_window : start]
        test_ds = ds.iloc[start : start + test_window]
        model = train(train_ds, random_state=random_state)
        p = predict_proba_up(model, test_ds[FEATURE_COLUMNS])
        proba_chunks.append(pd.Series(p, index=test_ds.index))
        start += test_window

    proba = pd.concat(proba_chunks)
    oos = ds.loc[proba.index]
    positions = (proba >= entry_threshold).astype(int)

    fwd_ret = oos[FWD_RETURN_COLUMN]
    turnover = positions.diff().abs().fillna(positions.iloc[0])
    costs = turnover * (cost_bps / 10_000)
    daily_returns = positions * fwd_ret - costs

    equity = (1 + daily_returns).cumprod()
    benchmark = (1 + fwd_ret).cumprod()

    return BacktestResult(
        equity=equity,
        benchmark=benchmark,
        daily_returns=daily_returns,
        positions=positions,
        proba=proba,
    )
