"""Paper-trading execution for desk decisions — Alpaca paper API only.

Design rules:
- PAPER ONLY. The client refuses any trading endpoint that is not
  paper-api.alpaca.markets. There is no override flag on purpose.
- Deterministic risk engine: entry/stop/target/size are computed from
  market data, never parsed out of LLM prose. The LLM decides WHETHER
  (BUY/SELL/HOLD); math decides HOW MUCH and WHERE.
- Every order is a bracket (entry + stop-loss + take-profit) so no
  position rides unmanaged.
"""

from __future__ import annotations

import json
import math
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from typing import Any

from desk_agents.marketdata import MarketBrief

PAPER_HOST = "paper-api.alpaca.markets"

MAX_POSITION_PCT = 5.0     # hard ceiling on position notional, % of equity
MAX_RISK_PCT = 0.5         # max loss at stop, % of equity
DEFAULT_POSITION_PCT = 3.0


class LiveTradingBlocked(RuntimeError):
    pass


@dataclass(frozen=True)
class OrderPlan:
    symbol: str
    action: str                # buy | close | none
    reason: str
    qty: int = 0
    entry_ref: float | None = None   # reference price (last close)
    stop_price: float | None = None
    target_price: float | None = None
    notional: float | None = None
    risk_dollars: float | None = None
    equity: float | None = None


class PaperBroker:
    """Minimal Alpaca trading client, stdlib urllib, paper endpoint only."""

    def __init__(self) -> None:
        base = os.getenv("ALPACA_BASE_URL", f"https://{PAPER_HOST}").rstrip("/")
        if PAPER_HOST not in base:
            raise LiveTradingBlocked(
                f"Refusing trading endpoint {base!r}: this desk only trades on the "
                f"Alpaca PAPER account ({PAPER_HOST}). There is no live-trading override."
            )
        self.base = base
        self.key = os.getenv("ALPACA_API_KEY", "")
        self.secret = os.getenv("ALPACA_SECRET_KEY", "")
        if not self.key or not self.secret:
            raise RuntimeError("ALPACA_API_KEY / ALPACA_SECRET_KEY not set")

    def _request(self, method: str, path: str, body: dict | None = None) -> Any:
        request = urllib.request.Request(
            f"{self.base}{path}",
            data=json.dumps(body).encode() if body is not None else None,
            headers={
                "APCA-API-KEY-ID": self.key,
                "APCA-API-SECRET-KEY": self.secret,
                "Content-Type": "application/json",
            },
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:400]
            raise RuntimeError(f"alpaca {method} {path} failed ({exc.code}): {detail}") from exc

    def account(self) -> dict:
        return self._request("GET", "/v2/account")

    def positions(self) -> list[dict]:
        return self._request("GET", "/v2/positions")

    def position(self, symbol: str) -> dict | None:
        try:
            return self._request("GET", f"/v2/positions/{symbol.upper()}")
        except RuntimeError as exc:
            if "(404)" in str(exc):
                return None
            raise

    def open_orders(self) -> list[dict]:
        return self._request("GET", "/v2/orders?status=open&limit=100")

    def recent_closed_orders(self, limit: int = 50) -> list[dict]:
        return self._request("GET", f"/v2/orders?status=closed&limit={min(limit, 100)}")

    def submit_bracket_buy(self, plan: OrderPlan) -> dict:
        return self._request("POST", "/v2/orders", {
            "symbol": plan.symbol,
            "qty": str(plan.qty),
            "side": "buy",
            "type": "market",
            "time_in_force": "day",
            "order_class": "bracket",
            "take_profit": {"limit_price": f"{plan.target_price:.2f}"},
            "stop_loss": {"stop_price": f"{plan.stop_price:.2f}"},
        })

    def close_position(self, symbol: str) -> dict:
        return self._request("DELETE", f"/v2/positions/{symbol.upper()}")


def plan_order(
    brief: MarketBrief,
    decision: dict,
    equity: float,
    *,
    already_held: bool = False,
) -> OrderPlan:
    """Deterministic order plan from live data + the desk's verdict."""
    symbol = brief.symbol
    action = (decision.get("action") or "HOLD").upper()

    if action == "SELL":
        if already_held:
            return OrderPlan(symbol=symbol, action="close", reason="desk decision SELL; closing paper position")
        return OrderPlan(symbol=symbol, action="none", reason="desk decision SELL but no position held")
    if action != "BUY":
        return OrderPlan(symbol=symbol, action="none", reason=f"desk decision {action}; nothing to execute")
    if already_held:
        return OrderPlan(symbol=symbol, action="none", reason="already holding this symbol; desk never pyramids")
    if not brief.ok or not brief.close or not brief.atr_pct:
        return OrderPlan(symbol=symbol, action="none", reason="market brief incomplete; refusing to size blind")

    entry = brief.close
    # Stop: the 20-day average when it is meaningfully below price, else 1.5 ATR.
    atr_stop = entry * (1 - 1.5 * brief.atr_pct / 100)
    stop = brief.ma20 if (brief.ma20 and brief.ma20 < entry * 0.995) else atr_stop
    stop = max(stop, entry * 0.85)  # never risk more than 15% per share
    risk_per_share = entry - stop
    if risk_per_share <= 0:
        return OrderPlan(symbol=symbol, action="none", reason="no valid stop below entry")
    target = entry + 2 * risk_per_share

    pct = decision.get("position_size_pct")
    try:
        pct = float(pct)
    except (TypeError, ValueError):
        pct = DEFAULT_POSITION_PCT
    pct = min(max(pct, 0.0), MAX_POSITION_PCT)
    if pct == 0:
        return OrderPlan(symbol=symbol, action="none", reason="decision sized the position at 0%")

    qty_by_notional = (equity * pct / 100) / entry
    qty_by_risk = (equity * MAX_RISK_PCT / 100) / risk_per_share
    qty = int(math.floor(min(qty_by_notional, qty_by_risk)))
    if qty < 1:
        return OrderPlan(symbol=symbol, action="none",
                         reason=f"position rounds to 0 shares at {pct}% of ${equity:,.0f} equity")

    return OrderPlan(
        symbol=symbol,
        action="buy",
        reason=f"BUY sized at min({pct}% notional, {MAX_RISK_PCT}% risk) of equity",
        qty=qty,
        entry_ref=round(entry, 2),
        stop_price=round(stop, 2),
        target_price=round(target, 2),
        notional=round(qty * entry, 2),
        risk_dollars=round(qty * risk_per_share, 2),
        equity=round(equity, 2),
    )


def execute_decision(
    brief: MarketBrief,
    decision: dict,
    *,
    execute: bool = False,
) -> dict:
    """Plan (and optionally place) the paper trade for one desk decision."""
    broker = PaperBroker()
    account = broker.account()
    equity = float(account.get("equity") or 0)
    held = broker.position(brief.symbol) is not None
    plan = plan_order(brief, decision, equity, already_held=held)

    result: dict[str, Any] = {"plan": asdict(plan), "executed": False, "order": None, "mode": "paper"}
    if not execute or plan.action == "none":
        return result
    if plan.action == "close":
        result["order"] = broker.close_position(plan.symbol)
    else:
        result["order"] = broker.submit_bracket_buy(plan)
    result["executed"] = True
    return result
