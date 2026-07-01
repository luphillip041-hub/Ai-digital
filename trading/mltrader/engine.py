"""Shared signal/rebalance engine used by the CLI, the bot loop, and the
dashboard server."""

from __future__ import annotations

import zlib
from typing import Callable

import pandas as pd

from .config import Settings
from .data import fetch_daily_bars, synthetic_daily_bars
from .features import build_dataset, build_features
from .model import predict_proba_up, train
from .risk import RiskLimits, orders_from_weights, target_weights

BarsFn = Callable[[Settings, str, float], pd.DataFrame]


def demo_bars(settings: Settings, symbol: str, years: float = 6.0) -> pd.DataFrame:
    """Deterministic synthetic bars per symbol, for keyless demo mode."""
    seed = zlib.crc32(symbol.encode())
    rng_pick = seed % 1000 / 1000
    return synthetic_daily_bars(
        n_days=int(years * 252),
        seed=seed % 2**16,
        drift=0.0001 + 0.0004 * rng_pick,
        vol=0.010 + 0.008 * (1 - rng_pick),
        start_price=50 + 400 * rng_pick,
    )


def compute_signal(bars: pd.DataFrame) -> float:
    """Train on all available history and return P(up) for the latest bar."""
    dataset = build_dataset(bars)
    model = train(dataset)
    latest = build_features(bars).dropna().iloc[[-1]]
    return float(predict_proba_up(model, latest)[0])


def compute_signals(
    settings: Settings, years: float = 6.0, bars_fn: BarsFn = fetch_daily_bars
) -> dict[str, float]:
    return {
        symbol: compute_signal(bars_fn(settings, symbol, years))
        for symbol in settings.symbols
    }


def risk_limits(settings: Settings) -> RiskLimits:
    return RiskLimits(
        max_position_pct=settings.max_position_pct,
        max_gross_exposure=settings.max_gross_exposure,
    )


def plan_orders(
    settings: Settings,
    proba_by_symbol: dict[str, float],
    equity: float,
    prices: dict[str, float],
    current_notional: dict[str, float],
) -> list[dict]:
    limits = risk_limits(settings)
    weights = target_weights(proba_by_symbol, settings.entry_threshold, limits)
    return orders_from_weights(weights, prices, current_notional, equity, limits)


def rebalance(broker, settings: Settings, years: float = 6.0, dry_run: bool = True) -> dict:
    """One full cycle against a live/paper Alpaca account. Returns a report dict."""
    proba = compute_signals(settings, years=years)
    orders = plan_orders(
        settings,
        proba,
        equity=broker.equity(),
        prices=broker.latest_prices(settings.symbols),
        current_notional=broker.positions_notional(),
    )
    sent = False
    if not dry_run:
        for o in orders:
            broker.submit_notional_order(o["symbol"], o["side"], o["notional"])
        sent = True
    return {"signals": proba, "orders": orders, "sent": sent, "dry_run": dry_run}
