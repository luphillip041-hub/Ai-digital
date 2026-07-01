"""FastAPI dashboard server.

Runs in two modes:
- demo (no API keys): synthetic data end-to-end, no orders can be sent
- paper/live (keys set): real Alpaca account, signals from real bars

    python -m mltrader.cli serve --port 8000
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import engine
from .backtest import walk_forward_backtest
from .config import Settings
from .data import fetch_daily_bars

WEB_DIR = Path(__file__).parent / "web"
CACHE_TTL_SECONDS = 15 * 60


class RebalanceRequest(BaseModel):
    dry_run: bool = True


class TradingService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.demo = not (settings.api_key and settings.secret_key)
        self._broker = None
        self._cache: dict[str, tuple[float, object]] = {}
        self._lock = threading.Lock()

    @property
    def broker(self):
        if self._broker is None:
            from .broker import AlpacaBroker

            self._broker = AlpacaBroker(self.settings)
        return self._broker

    def _cached(self, key: str, compute):
        with self._lock:
            hit = self._cache.get(key)
            if hit and time.monotonic() - hit[0] < CACHE_TTL_SECONDS:
                return hit[1]
            value = compute()
            self._cache[key] = (time.monotonic(), value)
            return value

    def _bars(self, symbol: str, years: float):
        if self.demo:
            return engine.demo_bars(self.settings, symbol, years)
        return fetch_daily_bars(self.settings, symbol, years)

    # ---- endpoint payloads ----

    def summary(self) -> dict:
        if self.demo:
            return {
                "mode": "demo",
                "equity": 100_000.0,
                "market_open": False,
                "positions": [],
                "symbols": self.settings.symbols,
                "entry_threshold": self.settings.entry_threshold,
            }
        positions = self.broker.positions_notional()
        return {
            "mode": "paper" if self.settings.paper else "live",
            "equity": self.broker.equity(),
            "market_open": self.broker.market_is_open(),
            "positions": [
                {"symbol": s, "notional": round(n, 2)} for s, n in sorted(positions.items())
            ],
            "symbols": self.settings.symbols,
            "entry_threshold": self.settings.entry_threshold,
        }

    def signals(self, years: float = 6.0) -> dict:
        def compute():
            proba = {
                symbol: engine.compute_signal(self._bars(symbol, years))
                for symbol in self.settings.symbols
            }
            threshold = self.settings.entry_threshold
            return {
                "threshold": threshold,
                "signals": [
                    {"symbol": s, "proba": round(p, 4), "long": p >= threshold}
                    for s, p in proba.items()
                ],
            }

        return self._cached(f"signals:{years}", compute)

    def backtest(self, symbol: str, years: float = 6.0) -> dict:
        if symbol not in self.settings.symbols:
            raise HTTPException(404, f"unknown symbol {symbol!r}")

        def compute():
            bars = self._bars(symbol, years)
            result = walk_forward_backtest(
                bars, entry_threshold=self.settings.entry_threshold
            )
            bench_total = float(result.benchmark.iloc[-1] - 1)
            return {
                "symbol": symbol,
                "metrics": {
                    "total_return": result.total_return,
                    "benchmark_return": bench_total,
                    "cagr": result.cagr,
                    "sharpe": result.sharpe,
                    "max_drawdown": result.max_drawdown,
                    "hit_rate": result.hit_rate,
                    "exposure": result.exposure,
                    "days": len(result.equity),
                },
                "dates": [d.strftime("%Y-%m-%d") for d in result.equity.index],
                "strategy": [round(float(v), 5) for v in result.equity],
                "benchmark": [round(float(v), 5) for v in result.benchmark],
            }

        return self._cached(f"backtest:{symbol}:{years}", compute)

    def rebalance(self, dry_run: bool) -> dict:
        if self.demo:
            proba = {s["symbol"]: s["proba"] for s in self.signals()["signals"]}
            prices = {
                symbol: float(self._bars(symbol, 1.0)["close"].iloc[-1])
                for symbol in self.settings.symbols
            }
            orders = engine.plan_orders(
                self.settings, proba, equity=100_000.0, prices=prices, current_notional={}
            )
            return {"signals": proba, "orders": orders, "sent": False, "dry_run": True,
                    "note": "demo mode — orders are never sent"}
        report = engine.rebalance(self.broker, self.settings, dry_run=dry_run)
        self._cache.pop("signals:6.0", None)
        return report


def create_app(settings: Settings | None = None) -> FastAPI:
    service = TradingService(settings or Settings())
    app = FastAPI(title="mltrader dashboard")
    app.state.service = service

    @app.get("/")
    def index():
        return FileResponse(WEB_DIR / "index.html")

    @app.get("/api/summary")
    def summary():
        return service.summary()

    @app.get("/api/signals")
    def signals(years: float = 6.0):
        return service.signals(years)

    @app.get("/api/backtest")
    def backtest(symbol: str, years: float = 6.0):
        return service.backtest(symbol, years)

    @app.post("/api/rebalance")
    def rebalance(req: RebalanceRequest):
        return service.rebalance(dry_run=req.dry_run)

    return app
