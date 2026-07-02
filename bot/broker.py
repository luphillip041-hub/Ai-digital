"""Thin wrapper around alpaca-trade-api.

Centralizes: retry-with-backoff on transient failures (disconnects, timeouts,
rate limits, 5xx), equities-vs-crypto endpoint differences, bar normalization
(and dropping the still-forming bar), and market-order execution with fill
polling.
"""

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import pandas as pd
import requests
from alpaca_trade_api.rest import APIError, REST, TimeFrame, TimeFrameUnit

import config

logger = logging.getLogger(__name__)

BAR_COLUMNS = ["open", "high", "low", "close", "volume"]


class Broker:
    def __init__(self):
        if not config.ALPACA_API_KEY or not config.ALPACA_SECRET_KEY:
            raise RuntimeError(
                "Missing Alpaca credentials. Copy .env.example to .env and "
                "set ALPACA_API_KEY / ALPACA_SECRET_KEY."
            )
        self.api = REST(
            key_id=config.ALPACA_API_KEY,
            secret_key=config.ALPACA_SECRET_KEY,
            base_url=config.ALPACA_BASE_URL,
        )

    # ------------------------------------------------------------------
    # Retry plumbing
    # ------------------------------------------------------------------
    def _call(self, fn, *args, **kwargs):
        """Call an API function, retrying transient failures with backoff."""
        delay = config.API_RETRY_BASE_DELAY
        last_exc = None
        for attempt in range(config.API_MAX_RETRIES + 1):
            try:
                return fn(*args, **kwargs)
            except APIError as exc:
                status = getattr(exc, "status_code", None) or 0
                # Retry rate limits and server-side errors; client errors
                # (bad request, rejected order) are not transient.
                if status in (429,) or status >= 500:
                    last_exc = exc
                else:
                    raise
            except (requests.exceptions.RequestException,
                    ConnectionError, TimeoutError) as exc:
                last_exc = exc
            if attempt < config.API_MAX_RETRIES:
                logger.warning("API call %s failed (%s), retrying in %ss",
                               getattr(fn, "__name__", fn), last_exc, delay)
                time.sleep(delay)
                delay *= 2
        raise last_exc

    # ------------------------------------------------------------------
    # Account / clock
    # ------------------------------------------------------------------
    def get_equity(self) -> float:
        return float(self._call(self.api.get_account).equity)

    def market_is_open(self) -> bool:
        return bool(self._call(self.api.get_clock).is_open)

    def list_position_symbols(self) -> set:
        """Symbols with live positions at the broker (crypto sans slash)."""
        return {p.symbol for p in self._call(self.api.list_positions)}

    # ------------------------------------------------------------------
    # Market data
    # ------------------------------------------------------------------
    @staticmethod
    def _timeframe(minutes: int) -> TimeFrame:
        if minutes >= 1440:
            return TimeFrame(minutes // 1440, TimeFrameUnit.Day)
        if minutes % 60 == 0:
            return TimeFrame(minutes // 60, TimeFrameUnit.Hour)
        return TimeFrame(minutes, TimeFrameUnit.Minute)

    def get_bars(self, instrument_cfg: dict, limit: int) -> pd.DataFrame:
        """Completed OHLCV bars, oldest first. The still-forming bar for the
        current period is dropped so strategies only ever see closed candles."""
        minutes = instrument_cfg["timeframe_minutes"]
        tf = self._timeframe(minutes)
        symbol = instrument_cfg["data_symbol"]
        now = datetime.now(timezone.utc)
        # Generous lookback: x6 covers nights/weekends when equities don't trade.
        start = (now - timedelta(minutes=minutes * limit * 6)).isoformat()

        if instrument_cfg["asset_class"] == "crypto":
            df = self._call(
                self.api.get_crypto_bars, symbol, tf, start=start, limit=limit
            ).df
        else:
            df = self._call(
                self.api.get_bars, symbol, tf, start=start, limit=limit,
                adjustment="raw", feed=config.ALPACA_DATA_FEED,
            ).df

        df = self._normalize_bars(df, symbol)

        # Drop the in-progress bar: anything at/after the current period start.
        epoch_min = int(now.timestamp() // 60)
        period_start = datetime.fromtimestamp(
            (epoch_min - epoch_min % minutes) * 60, tz=timezone.utc
        )
        df = df[df.index < period_start]
        return df

    @staticmethod
    def _normalize_bars(df, symbol: str) -> pd.DataFrame:
        if df is None or df.empty:
            return pd.DataFrame(columns=BAR_COLUMNS)
        # Multi-symbol responses carry a 'symbol' column — filter just in case.
        if "symbol" in df.columns:
            df = df[df["symbol"] == symbol]
        return df[BAR_COLUMNS].sort_index()

    def get_bars_range(self, instrument_cfg: dict, start_iso: str,
                       end_iso: str, limit: int = 50000) -> pd.DataFrame:
        """Historical OHLCV bars between two timestamps (for backtesting)."""
        tf = self._timeframe(instrument_cfg["timeframe_minutes"])
        symbol = instrument_cfg["data_symbol"]
        if instrument_cfg["asset_class"] == "crypto":
            df = self._call(self.api.get_crypto_bars, symbol, tf,
                            start=start_iso, end=end_iso, limit=limit).df
        else:
            df = self._call(self.api.get_bars, symbol, tf,
                            start=start_iso, end=end_iso, limit=limit,
                            adjustment="raw", feed=config.ALPACA_DATA_FEED).df
        return self._normalize_bars(df, symbol)

    def get_latest_price(self, instrument_cfg: dict) -> Optional[float]:
        symbol = instrument_cfg["data_symbol"]
        try:
            if instrument_cfg["asset_class"] == "crypto":
                try:
                    trade = self._call(self.api.get_latest_crypto_trade, symbol)
                    return float(trade.price)
                except (APIError, AttributeError, TypeError):
                    # Endpoint signature varies across library versions —
                    # fall back to the latest 1-minute bar close.
                    df = self._call(
                        self.api.get_crypto_bars, symbol, TimeFrame.Minute, limit=2
                    ).df
                    return float(df["close"].iloc[-1]) if not df.empty else None
            trade = self._call(self.api.get_latest_trade, symbol,
                               feed=config.ALPACA_DATA_FEED)
            return float(trade.price)
        except Exception as exc:  # price checks must never kill the loop
            logger.error("Failed to fetch latest price for %s: %s", symbol, exc)
            return None

    # ------------------------------------------------------------------
    # Orders
    # ------------------------------------------------------------------
    def submit_market_order(self, instrument_cfg: dict, side: str,
                            qty: float) -> Optional[float]:
        """Submit a market order and return the average fill price
        (None if the order could not be confirmed filled)."""
        symbol = instrument_cfg["trade_symbol"]
        tif = "gtc" if instrument_cfg["asset_class"] == "crypto" else "day"
        try:
            order = self._call(
                self.api.submit_order,
                symbol=symbol, qty=qty, side=side, type="market",
                time_in_force=tif,
            )
        except APIError as exc:
            logger.error("Order rejected: %s %s x%s — %s", side, symbol, qty, exc)
            return None

        # Poll briefly for the fill so we can log a real execution price.
        for _ in range(15):
            try:
                order = self._call(self.api.get_order, order.id)
            except APIError:
                break
            if order.status == "filled" and order.filled_avg_price:
                return float(order.filled_avg_price)
            if order.status in ("canceled", "expired", "rejected"):
                logger.error("Order %s ended %s", order.id, order.status)
                return None
            time.sleep(1)

        logger.warning("Order %s not confirmed filled after polling; "
                       "status=%s", order.id, order.status)
        if getattr(order, "filled_avg_price", None):
            return float(order.filled_avg_price)
        return None
