"""Risk management: ATR-based position sizing, hard stops, trailing stops,
and the SPY/QQQ/BTC correlation filter.

Sizing rule: a 1-ATR adverse move must cost exactly RISK_PER_TRADE (1%) of
account equity, so qty = (equity * 1%) / ATR. Quiet instruments get bigger
positions, volatile ones smaller — dollar risk stays constant.

Hard stop rule: every trade is cut at a loss of 1% of entry-time equity.
Given the sizing rule, that is exactly a 1-ATR move from entry. No exceptions.
"""

import logging
import math
from typing import Optional

import config
from bot.portfolio import Position

logger = logging.getLogger(__name__)


class RiskManager:
    # ------------------------------------------------------------------
    # Position sizing
    # ------------------------------------------------------------------
    def position_size(self, equity: float, atr: float, price: float,
                      asset_class: str) -> float:
        """Quantity such that a 1-ATR move against us = RISK_PER_TRADE of equity.

        Returns 0 if the trade can't be sized safely (bad ATR, sub-share
        equity size, dust crypto order, or notional exceeding equity).
        """
        if atr is None or atr <= 0 or price <= 0 or equity <= 0:
            return 0.0

        risk_dollars = equity * config.RISK_PER_TRADE
        qty = risk_dollars / atr

        if asset_class == "equity":
            qty = float(math.floor(qty))  # whole shares (required for shorts)
            if qty < 1:
                logger.warning(
                    "Sized position < 1 share (risk $%.2f / ATR %.4f) — skipping",
                    risk_dollars, atr,
                )
                return 0.0
        else:
            qty = round(qty, 6)
            if qty * price < config.CRYPTO_MIN_NOTIONAL:
                logger.warning(
                    "Crypto order notional $%.2f below minimum $%.2f — skipping",
                    qty * price, config.CRYPTO_MIN_NOTIONAL,
                )
                return 0.0

        # Sanity cap: never exceed account equity in notional (a very quiet
        # instrument could otherwise size beyond buying power).
        if qty * price > equity:
            qty = equity / price
            qty = float(math.floor(qty)) if asset_class == "equity" else round(qty, 6)
            logger.info("Position capped at 1x equity notional: qty=%s", qty)

        return max(qty, 0.0)

    # ------------------------------------------------------------------
    # Stops
    # ------------------------------------------------------------------
    def hard_stop_distance(self, equity: float, qty: float, atr: float) -> float:
        """Price distance at which the loss equals HARD_STOP_EQUITY_FRACTION
        (1%) of equity for this position size.

        Equals exactly 1 ATR when sizing was unconstrained (qty = 1% equity
        / ATR). When the notional cap or whole-share rounding shrank the
        position, the distance widens so the dollar risk stays 1% of equity
        — the stop is defined in equity terms, not ATR terms.
        """
        if qty <= 0:
            return atr
        return max(atr, equity * config.HARD_STOP_EQUITY_FRACTION / qty)

    def hard_stop_price(self, entry_price: float, stop_distance: float,
                        direction: str) -> float:
        if direction == "long":
            return entry_price - stop_distance
        return entry_price + stop_distance

    def update_trailing_stop(self, position: Position, latest_atr: float) -> None:
        """Ratchet the trailing stop after each completed bar.

        The trail follows the best price seen since entry at
        trail_atr_mult * current ATR. It only ever tightens.
        """
        if position.trail_atr_mult is None or latest_atr is None or latest_atr <= 0:
            return

        distance = position.trail_atr_mult * latest_atr
        if position.direction == "long":
            candidate = position.best_price - distance
            if position.trail_stop is None or candidate > position.trail_stop:
                position.trail_stop = candidate
        else:
            candidate = position.best_price + distance
            if position.trail_stop is None or candidate < position.trail_stop:
                position.trail_stop = candidate

    def check_stops(self, position: Position, price: float) -> Optional[str]:
        """Return an exit reason if the price violates any stop, else None.

        Also updates the position's best_price high-water mark.
        """
        if position.direction == "long":
            position.best_price = max(position.best_price, price)
            if price <= position.hard_stop:
                return (f"hard stop hit: price {price:.2f} <= "
                        f"stop {position.hard_stop:.2f} (1% equity loss)")
            if position.trail_stop is not None and price <= position.trail_stop:
                return (f"trailing stop hit: price {price:.2f} <= "
                        f"trail {position.trail_stop:.2f}")
        else:
            position.best_price = min(position.best_price, price)
            if price >= position.hard_stop:
                return (f"hard stop hit: price {price:.2f} >= "
                        f"stop {position.hard_stop:.2f} (1% equity loss)")
            if position.trail_stop is not None and price >= position.trail_stop:
                return (f"trailing stop hit: price {price:.2f} >= "
                        f"trail {position.trail_stop:.2f}")
        return None

    # ------------------------------------------------------------------
    # Correlation filter
    # ------------------------------------------------------------------
    def correlation_blocks_long(self, symbol: str, portfolio) -> bool:
        """True if a new long on `symbol` would stack correlated risk-on
        exposure (SPY and QQQ already long -> no new BTC/USD longs)."""
        cfg = config.CORRELATION_FILTER
        if symbol != cfg["blocked_symbol"]:
            return False
        if all(portfolio.is_long(s) for s in cfg["requires_long"]):
            logger.info(
                "Correlation filter: %s long blocked — %s already long",
                symbol, " and ".join(cfg["requires_long"]),
            )
            return True
        return False
