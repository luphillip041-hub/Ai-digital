"""Thin wrapper around Alpaca's TradingClient (paper by default)."""

from __future__ import annotations

from .config import Settings


class AlpacaBroker:
    def __init__(self, settings: Settings):
        from alpaca.trading.client import TradingClient

        settings.require_keys()
        self.settings = settings
        self.client = TradingClient(
            settings.api_key, settings.secret_key, paper=settings.paper
        )

    def equity(self) -> float:
        return float(self.client.get_account().equity)

    def positions_notional(self) -> dict[str, float]:
        """Current market value held per symbol."""
        return {
            p.symbol: float(p.market_value)
            for p in self.client.get_all_positions()
        }

    def latest_prices(self, symbols: list[str]) -> dict[str, float]:
        from alpaca.data.historical import StockHistoricalDataClient
        from alpaca.data.requests import StockLatestTradeRequest

        data = StockHistoricalDataClient(
            self.settings.api_key, self.settings.secret_key
        )
        trades = data.get_stock_latest_trade(
            StockLatestTradeRequest(symbol_or_symbols=symbols)
        )
        return {s: float(t.price) for s, t in trades.items()}

    def submit_notional_order(self, symbol: str, side: str, notional: float):
        from alpaca.trading.enums import OrderSide, TimeInForce
        from alpaca.trading.requests import MarketOrderRequest

        order = MarketOrderRequest(
            symbol=symbol,
            notional=round(notional, 2),
            side=OrderSide.BUY if side == "buy" else OrderSide.SELL,
            time_in_force=TimeInForce.DAY,
        )
        return self.client.submit_order(order)

    def market_is_open(self) -> bool:
        return bool(self.client.get_clock().is_open)
