"""Position tracking, trade logging (trades.csv), daily P&L logging
(daily_pnl.csv), and crash-safe state persistence (bot_state.json)."""

import csv
import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from typing import Dict, Optional

import config

logger = logging.getLogger(__name__)

TRADES_HEADER = [
    "timestamp", "instrument", "direction",
    "entry_price", "exit_price", "pnl", "position_size", "reason",
]
DAILY_PNL_HEADER = ["date", "realized_pnl", "account_equity"]


@dataclass
class Position:
    symbol: str
    direction: str  # "long" or "short"
    qty: float
    entry_price: float
    entry_time: str  # ISO timestamp
    atr_at_entry: float
    hard_stop: float
    trail_atr_mult: Optional[float] = None
    trail_stop: Optional[float] = None
    best_price: float = 0.0  # high-water (long) / low-water (short) mark
    strategy: str = ""


class Portfolio:
    def __init__(self):
        self.positions: Dict[str, Position] = {}
        # realized P&L per ISO date string, survives restarts via state file
        self.realized_by_day: Dict[str, float] = {}
        self._init_csv(config.TRADES_CSV, TRADES_HEADER)
        self._init_csv(config.DAILY_PNL_CSV, DAILY_PNL_HEADER)
        self.load_state()

    # ------------------------------------------------------------------
    # Position lifecycle
    # ------------------------------------------------------------------
    def open_position(self, symbol: str, direction: str, qty: float,
                      entry_price: float, atr: float, hard_stop: float,
                      trail_atr_mult: Optional[float], strategy: str) -> Position:
        pos = Position(
            symbol=symbol,
            direction=direction,
            qty=qty,
            entry_price=entry_price,
            entry_time=datetime.now(timezone.utc).isoformat(),
            atr_at_entry=atr,
            hard_stop=hard_stop,
            trail_atr_mult=trail_atr_mult,
            best_price=entry_price,
            strategy=strategy,
        )
        self.positions[symbol] = pos
        self.save_state()
        logger.info(
            "OPEN %s %s qty=%s @ %.4f (ATR %.4f, hard stop %.4f)",
            direction.upper(), symbol, qty, entry_price, atr, hard_stop,
        )
        return pos

    def close_position(self, symbol: str, exit_price: float, reason: str) -> float:
        """Close the tracked position, log the round-trip trade, return P&L."""
        pos = self.positions.pop(symbol, None)
        if pos is None:
            logger.warning("close_position: no tracked position for %s", symbol)
            return 0.0

        if pos.direction == "long":
            pnl = (exit_price - pos.entry_price) * pos.qty
        else:
            pnl = (pos.entry_price - exit_price) * pos.qty

        today = datetime.now(timezone.utc).date().isoformat()
        self.realized_by_day[today] = self.realized_by_day.get(today, 0.0) + pnl

        self._append_csv(config.TRADES_CSV, [
            datetime.now(timezone.utc).isoformat(),
            symbol,
            pos.direction,
            f"{pos.entry_price:.6f}",
            f"{exit_price:.6f}",
            f"{pnl:.2f}",
            pos.qty,
            reason,
        ])
        self.save_state()
        logger.info(
            "CLOSE %s %s qty=%s @ %.4f | P&L $%.2f | %s",
            pos.direction.upper(), symbol, pos.qty, exit_price, pnl, reason,
        )
        return pnl

    def get(self, symbol: str) -> Optional[Position]:
        return self.positions.get(symbol)

    def is_long(self, symbol: str) -> bool:
        pos = self.positions.get(symbol)
        return pos is not None and pos.direction == "long"

    # ------------------------------------------------------------------
    # Daily P&L
    # ------------------------------------------------------------------
    def log_daily_pnl(self, day: date, account_equity: Optional[float]) -> None:
        realized = self.realized_by_day.get(day.isoformat(), 0.0)
        self._append_csv(config.DAILY_PNL_CSV, [
            day.isoformat(),
            f"{realized:.2f}",
            f"{account_equity:.2f}" if account_equity is not None else "",
        ])
        logger.info("Daily P&L %s: realized $%.2f, equity %s",
                    day.isoformat(), realized, account_equity)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def save_state(self) -> None:
        state = {
            "positions": {s: asdict(p) for s, p in self.positions.items()},
            "realized_by_day": self.realized_by_day,
        }
        tmp = config.STATE_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(state, f, indent=2)
        os.replace(tmp, config.STATE_FILE)

    def load_state(self) -> None:
        if not os.path.exists(config.STATE_FILE):
            return
        try:
            with open(config.STATE_FILE) as f:
                state = json.load(f)
            self.positions = {
                s: Position(**p) for s, p in state.get("positions", {}).items()
            }
            self.realized_by_day = state.get("realized_by_day", {})
            if self.positions:
                logger.info("Restored %d open position(s) from state: %s",
                            len(self.positions), list(self.positions))
        except (json.JSONDecodeError, TypeError, KeyError) as exc:
            logger.error("Could not load state file %s: %s — starting fresh",
                         config.STATE_FILE, exc)

    # ------------------------------------------------------------------
    # CSV helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _init_csv(path: str, header: list) -> None:
        if not os.path.exists(path):
            with open(path, "w", newline="") as f:
                csv.writer(f).writerow(header)

    @staticmethod
    def _append_csv(path: str, row: list) -> None:
        with open(path, "a", newline="") as f:
            csv.writer(f).writerow(row)
