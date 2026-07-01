"""Main event loop for the multi-strategy Alpaca trading bot.

Run from the repository root:  python -m bot.main

Every POLL_INTERVAL_SECONDS the bot:
  1. checks stops (hard 1%-equity stop + ATR trailing stops) for open
     positions against the latest trade price,
  2. for each instrument whose candle just closed, fetches bars and asks its
     strategy for a signal, then routes the signal through risk management
     (ATR sizing, correlation filter) before touching the broker,
  3. rolls the daily P&L file over at UTC midnight.

Equities are only processed while the market is open; crypto runs 24/7.
Any per-instrument error is logged and skipped so one bad symbol/API hiccup
never kills the loop.
"""

import logging
import time
from datetime import datetime, timezone
from typing import Optional

import config
from bot.broker import Broker
from bot.notifier import Notifier
from bot.portfolio import Portfolio
from bot.risk_manager import RiskManager
from bot.strategies import STRATEGY_REGISTRY
from bot.strategies.base import EXIT, LONG, SHORT, Signal

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(config.LOG_FILE),
    ],
)
logger = logging.getLogger("bot")


class TradingBot:
    def __init__(self):
        self.broker = Broker()
        self.portfolio = Portfolio()
        self.risk = RiskManager()
        self.notifier = Notifier()
        self.strategies = {
            key: STRATEGY_REGISTRY[cfg["strategy"]](key, cfg["params"])
            for key, cfg in config.INSTRUMENTS.items()
        }
        # Per-instrument id of the last candle period we evaluated, so each
        # strategy runs exactly once per completed bar of its timeframe.
        self.last_bar_bucket = {}
        self.current_day = datetime.now(timezone.utc).date()

    # ------------------------------------------------------------------
    # Startup
    # ------------------------------------------------------------------
    def reconcile_positions(self) -> None:
        """Cross-check persisted positions against what Alpaca actually holds;
        drop tracked positions that no longer exist at the broker."""
        try:
            live = self.broker.list_position_symbols()
        except Exception as exc:
            logger.error("Could not list broker positions on startup: %s", exc)
            return
        for key in list(self.portfolio.positions):
            broker_symbol = config.INSTRUMENTS[key]["trade_symbol"].replace("/", "")
            if broker_symbol not in live:
                logger.warning(
                    "Tracked position %s not found at broker — dropping it "
                    "from local state", key,
                )
                self.portfolio.positions.pop(key)
        self.portfolio.save_state()

        tracked = {
            config.INSTRUMENTS[k]["trade_symbol"].replace("/", "")
            for k in self.portfolio.positions
        }
        for sym in live - tracked:
            logger.warning(
                "Broker holds %s which this bot is not tracking — it will "
                "NOT be managed by the bot", sym,
            )

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------
    def run(self) -> None:
        logger.info(
            "Starting bot: %d instruments, poll every %ss, risk %.1f%%/trade",
            len(config.INSTRUMENTS), config.POLL_INTERVAL_SECONDS,
            config.RISK_PER_TRADE * 100,
        )
        self.reconcile_positions()
        self.notifier.send(
            "Bot started",
            f"{len(config.INSTRUMENTS)} instruments, "
            f"{len(self.portfolio.positions)} open position(s) restored",
        )
        while True:
            try:
                self.tick()
            except KeyboardInterrupt:
                logger.info("Shutting down (state saved to %s)", config.STATE_FILE)
                self.portfolio.save_state()
                return
            except Exception:
                # Catch-all so transient API/parse failures never end the loop.
                logger.exception("Unhandled error in tick — continuing")
            time.sleep(config.POLL_INTERVAL_SECONDS)

    def tick(self) -> None:
        try:
            market_open = self.broker.market_is_open()
        except Exception as exc:
            logger.error("Clock unavailable (%s) — treating equity market "
                         "as closed this tick", exc)
            market_open = False

        for key, cfg in config.INSTRUMENTS.items():
            try:
                self.process_instrument(key, cfg, market_open)
            except Exception:
                logger.exception("Error processing %s — skipping this tick", key)

        self.rollover_daily_pnl()

    def process_instrument(self, key: str, cfg: dict, market_open: bool) -> None:
        # Equities can only be traded (and stopped out) during market hours.
        if cfg["asset_class"] == "equity" and not market_open:
            return

        # --- 1. Stop management on every poll, using the latest trade price.
        position = self.portfolio.get(key)
        if position is not None:
            price = self.broker.get_latest_price(cfg)
            if price is not None:
                exit_reason = self.risk.check_stops(position, price)
                if exit_reason:
                    self.close_trade(key, cfg, exit_reason)
                    position = None

        # --- 2. Strategy evaluation once per completed candle.
        minutes = cfg["timeframe_minutes"]
        bucket = int(datetime.now(timezone.utc).timestamp() // (minutes * 60))
        if self.last_bar_bucket.get(key) == bucket:
            return
        self.last_bar_bucket[key] = bucket

        strategy = self.strategies[key]
        bars = self.broker.get_bars(cfg, limit=strategy.required_bars + 20)
        if not strategy.has_enough_bars(bars):
            logger.info("%s: only %d bars available (need %d) — waiting",
                        key, len(bars), strategy.required_bars)
            return

        from bot import indicators
        latest_atr = float(indicators.atr(bars, config.ATR_PERIOD).iloc[-1])
        last_close = float(bars["close"].iloc[-1])

        # Ratchet trailing stops on each completed bar with fresh ATR.
        position = self.portfolio.get(key)
        if position is not None:
            self.risk.update_trailing_stop(position, latest_atr)
            self.portfolio.save_state()

        direction = position.direction if position else None
        signal = strategy.evaluate(bars, direction)
        if signal.action != "none":
            logger.info("%s signal: %s (%s)", key, signal.action.upper(),
                        signal.reason)
            self.handle_signal(key, cfg, signal, latest_atr, last_close)

    # ------------------------------------------------------------------
    # Signal routing
    # ------------------------------------------------------------------
    def handle_signal(self, key: str, cfg: dict, signal: Signal,
                      atr: float, last_close: float) -> None:
        position = self.portfolio.get(key)

        if signal.action == EXIT:
            if position is not None:
                self.close_trade(key, cfg, f"strategy exit: {signal.reason}")
            return

        if signal.action == LONG:
            if position is not None and position.direction == "long":
                return
            if position is not None:  # flip short -> long
                self.close_trade(key, cfg, f"reversing to long: {signal.reason}")
            if self.risk.correlation_blocks_long(key, self.portfolio):
                return
            self.open_trade(key, cfg, "long", atr, last_close, signal.reason)
            return

        if signal.action == SHORT:
            if position is not None and position.direction == "short":
                return
            if position is not None:  # long position: exit first
                self.close_trade(key, cfg, f"short signal: {signal.reason}")
            if not cfg["shortable"]:
                logger.info("%s not shortable — short signal handled as "
                            "exit-only", key)
                return
            self.open_trade(key, cfg, "short", atr, last_close, signal.reason)

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------
    def open_trade(self, key: str, cfg: dict, direction: str, atr: float,
                   price_hint: float, reason: str) -> None:
        try:
            equity = self.broker.get_equity()
        except Exception as exc:
            logger.error("Cannot fetch equity, skipping %s entry: %s", key, exc)
            return

        qty = self.risk.position_size(equity, atr, price_hint,
                                      cfg["asset_class"])
        if qty <= 0:
            return

        side = "buy" if direction == "long" else "sell"
        fill = self.broker.submit_market_order(cfg, side, qty)
        if fill is None:
            logger.error("Entry order for %s did not fill — no position "
                         "tracked", key)
            return

        hard_stop = self.risk.hard_stop_price(fill, atr, direction)
        self.portfolio.open_position(
            symbol=key, direction=direction, qty=qty, entry_price=fill,
            atr=atr, hard_stop=hard_stop,
            trail_atr_mult=cfg["trail_atr_mult"], strategy=cfg["strategy"],
        )
        self.notifier.trade_opened(key, direction, qty, fill, hard_stop, reason)

    def close_trade(self, key: str, cfg: dict, reason: str) -> None:
        position = self.portfolio.get(key)
        if position is None:
            return
        side = "sell" if position.direction == "long" else "buy"
        fill = self.broker.submit_market_order(cfg, side, position.qty)
        if fill is None:
            # Order didn't confirm — log with the best price we have rather
            # than leave the book in limbo; reconcile on next startup.
            fill = self.broker.get_latest_price(cfg) or position.entry_price
            logger.error("Exit fill for %s unconfirmed — logging close at "
                         "%.4f; verify at the broker", key, fill)
        pnl = self.portfolio.close_position(key, fill, reason)
        self.notifier.trade_closed(key, position.direction, position.qty,
                                   fill, pnl, reason)

    # ------------------------------------------------------------------
    # Daily P&L
    # ------------------------------------------------------------------
    def rollover_daily_pnl(self) -> None:
        today = datetime.now(timezone.utc).date()
        if today == self.current_day:
            return
        equity: Optional[float]
        try:
            equity = self.broker.get_equity()
        except Exception as exc:
            logger.error("Equity unavailable for daily P&L: %s", exc)
            equity = None
        self.portfolio.log_daily_pnl(self.current_day, equity)
        day = self.current_day.isoformat()
        self.notifier.daily_summary(
            day,
            self.portfolio.realized_by_day.get(day, 0.0),
            equity,
            self._trades_closed_on(day),
            self.portfolio.positions,
        )
        self.current_day = today

    @staticmethod
    def _trades_closed_on(day: str) -> int:
        try:
            with open(config.TRADES_CSV) as f:
                return sum(1 for line in f if line.startswith(day))
        except OSError:
            return 0


def main() -> None:
    TradingBot().run()


if __name__ == "__main__":
    main()
