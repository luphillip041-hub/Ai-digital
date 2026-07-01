"""Position sizing and portfolio risk limits."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RiskLimits:
    max_position_pct: float = 0.20     # max fraction of equity per symbol
    max_gross_exposure: float = 1.0    # max sum of position fractions (long-only)
    min_order_notional: float = 1.0    # skip dust orders below this many dollars


def target_weights(
    proba_by_symbol: dict[str, float],
    entry_threshold: float,
    limits: RiskLimits,
) -> dict[str, float]:
    """Convert per-symbol P(up) into target portfolio weights.

    Symbols above the entry threshold split the gross exposure budget equally,
    capped per-symbol at max_position_pct. Everything else targets zero.
    """
    selected = [s for s, p in proba_by_symbol.items() if p >= entry_threshold]
    weights = {s: 0.0 for s in proba_by_symbol}
    if not selected:
        return weights
    per_symbol = min(limits.max_gross_exposure / len(selected), limits.max_position_pct)
    for s in selected:
        weights[s] = per_symbol
    return weights


def orders_from_weights(
    weights: dict[str, float],
    prices: dict[str, float],
    current_notional: dict[str, float],
    equity: float,
    limits: RiskLimits,
) -> list[dict]:
    """Diff target weights against current holdings into market-order intents.

    Returns dicts: {symbol, side ('buy'|'sell'), notional (positive dollars)}.
    Sells are listed first so freed cash can fund the buys.
    """
    orders: list[dict] = []
    for symbol, weight in weights.items():
        if symbol not in prices or prices[symbol] <= 0:
            continue
        target = max(0.0, min(weight, limits.max_position_pct)) * equity
        delta = target - current_notional.get(symbol, 0.0)
        if abs(delta) < limits.min_order_notional:
            continue
        side = "buy" if delta > 0 else "sell"
        orders.append({"symbol": symbol, "side": side, "notional": round(abs(delta), 2)})
    orders.sort(key=lambda o: o["side"] != "sell")  # sells first
    return orders
