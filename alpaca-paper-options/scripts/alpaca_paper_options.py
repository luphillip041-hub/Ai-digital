#!/usr/bin/env python3
"""Isolated Alpaca PAPER options adapter for Flip's standalone paper-options service.

Paper-only by default. This module never reads credentials from other projects;
it loads only alpaca-paper-options/.env and .env.local.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    load_dotenv = None

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs"
PAPER_API = "https://paper-api.alpaca.markets"
DATA_API = "https://data.alpaca.markets"


class AlpacaError(RuntimeError):
    pass


@dataclass(frozen=True)
class AlpacaConfig:
    key_id: str
    secret_key: str
    paper_base_url: str = PAPER_API
    data_base_url: str = DATA_API

    @property
    def present(self) -> bool:
        return bool(self.key_id and self.secret_key)


def load_env() -> None:
    if load_dotenv:
        load_dotenv(ROOT / ".env")
        load_dotenv(ROOT / ".env.local")


def config_from_env() -> AlpacaConfig:
    load_env()
    key = os.getenv("APCA_API_KEY_ID") or os.getenv("ALPACA_API_KEY_ID") or os.getenv("ALPACA_API_KEY") or ""
    secret = os.getenv("APCA_API_SECRET_KEY") or os.getenv("ALPACA_API_SECRET_KEY") or os.getenv("ALPACA_API_SECRET") or ""
    paper = os.getenv("ALPACA_PAPER_BASE_URL", PAPER_API).rstrip("/")
    data = os.getenv("ALPACA_DATA_BASE_URL", DATA_API).rstrip("/")
    return AlpacaConfig(key.strip(), secret.strip(), paper, data)


def now_utc() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def headers(cfg: AlpacaConfig) -> dict[str, str]:
    return {
        "APCA-API-KEY-ID": cfg.key_id,
        "APCA-API-SECRET-KEY": cfg.secret_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def request_json(
    cfg: AlpacaConfig,
    method: str,
    url: str,
    *,
    payload: dict[str, Any] | None = None,
    timeout: int = 20,
) -> Any:
    if not cfg.present:
        raise AlpacaError("missing Alpaca paper API keys in alpaca-paper-options/.env")
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=body, headers=headers(cfg), method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise AlpacaError(f"{method} {url} failed {exc.code}: {raw[:1200]}") from exc
    except urllib.error.URLError as exc:
        raise AlpacaError(f"{method} {url} failed: {exc}") from exc


def get_account(cfg: AlpacaConfig) -> dict[str, Any]:
    return request_json(cfg, "GET", f"{cfg.paper_base_url}/v2/account")


def get_clock(cfg: AlpacaConfig) -> dict[str, Any]:
    return request_json(cfg, "GET", f"{cfg.paper_base_url}/v2/clock")


def get_positions(cfg: AlpacaConfig) -> list[dict[str, Any]]:
    data = request_json(cfg, "GET", f"{cfg.paper_base_url}/v2/positions")
    return data if isinstance(data, list) else []


def get_orders(cfg: AlpacaConfig, status: str = "open", limit: int = 50) -> list[dict[str, Any]]:
    qs = urllib.parse.urlencode({"status": status, "limit": limit, "direction": "desc"})
    data = request_json(cfg, "GET", f"{cfg.paper_base_url}/v2/orders?{qs}")
    return data if isinstance(data, list) else []


def get_fills(cfg: AlpacaConfig, page_size: int = 100) -> list[dict[str, Any]]:
    qs = urllib.parse.urlencode({"direction": "desc", "page_size": page_size})
    data = request_json(cfg, "GET", f"{cfg.paper_base_url}/v2/account/activities/FILL?{qs}")
    return data if isinstance(data, list) else []


def occ_symbol(underlying: str, expiration: str, option_type: str, strike: float) -> str:
    exp = date.fromisoformat(expiration).strftime("%y%m%d")
    cp = "C" if option_type.upper().startswith("C") else "P"
    strike_int = int(round(float(strike) * 1000))
    return f"{underlying.upper()}{exp}{cp}{strike_int:08d}"


def option_snapshot(cfg: AlpacaConfig, occ: str) -> dict[str, Any]:
    qs = urllib.parse.urlencode({"symbols": occ})
    data = request_json(cfg, "GET", f"{cfg.data_base_url}/v1beta1/options/snapshots?{qs}")
    if isinstance(data, dict):
        snaps = data.get("snapshots") or data.get("snapshot") or {}
        if isinstance(snaps, dict) and occ in snaps:
            return snaps[occ]
    return data if isinstance(data, dict) else {}


def stock_latest_quote(cfg: AlpacaConfig, symbol: str) -> dict[str, Any]:
    qs = urllib.parse.urlencode({"feed": os.getenv("ALPACA_STOCK_FEED", "iex")})
    return request_json(cfg, "GET", f"{cfg.data_base_url}/v2/stocks/{symbol}/quotes/latest?{qs}")


def _money(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def _option_quote_fields(snapshot: dict[str, Any]) -> dict[str, Any]:
    q = snapshot.get("latestQuote") or snapshot.get("latest_quote") or snapshot.get("quote") or {}
    trade = snapshot.get("latestTrade") or snapshot.get("latest_trade") or {}
    greeks = snapshot.get("greeks") or {}
    iv = snapshot.get("impliedVolatility") or snapshot.get("implied_volatility")
    bid = _money(q.get("bp") or q.get("bidPrice") or q.get("bid_price") or q.get("bid"))
    ask = _money(q.get("ap") or q.get("askPrice") or q.get("ask_price") or q.get("ask"))
    last = _money(trade.get("p") or trade.get("price") or trade.get("last"))
    mid = round((bid + ask) / 2, 4) if bid and ask else last
    return {
        "bid": bid,
        "ask": ask,
        "mid": mid,
        "last": last,
        "iv": iv,
        "delta": greeks.get("delta"),
        "theta": greeks.get("theta"),
        "raw_quote": q,
        "raw_trade": trade,
    }


def account_summary(account: dict[str, Any]) -> dict[str, Any]:
    return {
        "id_tail": str(account.get("id", ""))[-6:] if account else "",
        "status": account.get("status"),
        "currency": account.get("currency"),
        "buying_power": account.get("buying_power"),
        "options_buying_power": account.get("options_buying_power"),
        "options_trading_level": account.get("options_trading_level"),
        "account_blocked": account.get("account_blocked"),
        "trading_blocked": account.get("trading_blocked"),
        "pattern_day_trader": account.get("pattern_day_trader"),
        "paper_endpoint": True,
    }


def verify_account(account: dict[str, Any], clock: dict[str, Any], required_debit: float) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if account.get("status") != "ACTIVE":
        reasons.append(f"account status {account.get('status')}")
    if account.get("account_blocked") is True or account.get("trading_blocked") is True:
        reasons.append("account/trading blocked")
    try:
        if int(account.get("options_trading_level") or 0) < int(os.getenv("ALPACA_MIN_OPTIONS_LEVEL", "2")):
            reasons.append("options trading level too low")
    except Exception:
        reasons.append("options trading level unavailable")
    if required_debit > 0:
        obp = _money(account.get("options_buying_power") or account.get("buying_power"))
        if obp < required_debit:
            reasons.append(f"insufficient options buying power {obp:.2f} < {required_debit:.2f}")
    if os.getenv("ALPACA_ALLOW_AFTER_HOURS_OPTIONS", "false").lower() != "true" and clock.get("is_open") is not True:
        reasons.append("market closed")
    return not reasons, reasons


def build_order_from_signal(signal: dict[str, Any], qty: int, limit_multiplier: float = 1.02) -> dict[str, Any]:
    setup = signal.get("setup") or {}
    contract = signal.get("contract") or {}
    if not contract:
        raise AlpacaError("signal has no contract")
    symbol = str(signal.get("symbol") or setup.get("symbol") or "").upper()
    if not symbol:
        raise AlpacaError("signal missing underlying symbol")
    occ = contract.get("symbol") or occ_symbol(symbol, contract["expiration"], contract["type"], float(contract["strike"]))
    ask = _money(contract.get("ask") or contract.get("mid"))
    mid = _money(contract.get("mid") or ask)
    # Conservative paper entry: use ask-side cap, never market orders.
    limit_price = round(max(mid, ask) * limit_multiplier, 2)
    return {
        "symbol": occ,
        "qty": str(int(qty)),
        "side": "buy",
        "type": "limit",
        "time_in_force": "day",
        "limit_price": f"{limit_price:.2f}",
        "position_intent": "buy_to_open",
    }


def stage_signal_order(
    cfg: AlpacaConfig,
    signal: dict[str, Any],
    *,
    qty: int,
    submit: bool,
    max_debit: float,
    allow_wide_spread: bool = False,
) -> dict[str, Any]:
    contract = signal.get("contract") or {}
    symbol = signal.get("symbol") or (signal.get("setup") or {}).get("symbol")
    order = build_order_from_signal(signal, qty)
    planned_debit = _money(order["limit_price"]) * int(qty) * 100
    occ = order["symbol"]
    result: dict[str, Any] = {
        "generated_at": now_utc(),
        "mode": "submit" if submit else "dry_run",
        "symbol": symbol,
        "occ_symbol": occ,
        "qty": int(qty),
        "paper_endpoint": cfg.paper_base_url == PAPER_API,
        "order": order,
        "planned_max_debit": round(planned_debit, 2),
        "max_debit_allowed": max_debit,
        "checks": [],
        "submitted_order": None,
    }
    if not cfg.present:
        result.update({"status": "blocked", "reasons": ["missing Alpaca paper API keys in alpaca-paper-options/.env"]})
        return result
    account = get_account(cfg)
    clock = get_clock(cfg)
    snapshot = option_snapshot(cfg, occ)
    live_q = _option_quote_fields(snapshot)
    result["account"] = account_summary(account)
    result["clock"] = {k: clock.get(k) for k in ("is_open", "timestamp", "next_open", "next_close")}
    result["live_option_quote"] = live_q

    reasons: list[str] = []
    if cfg.paper_base_url != PAPER_API:
        reasons.append("not using paper-api.alpaca.markets")
    ok, acct_reasons = verify_account(account, clock, planned_debit)
    reasons.extend(acct_reasons)
    if max_debit and planned_debit > max_debit:
        reasons.append(f"planned debit {planned_debit:.2f} exceeds max {max_debit:.2f}")
    spread_pct = contract.get("spread_pct")
    if spread_pct is not None and float(spread_pct) > float(os.getenv("ALPACA_MAX_OPTION_SPREAD_PCT", "25")) and not allow_wide_spread:
        reasons.append(f"wide spread {spread_pct}%")
    if live_q.get("ask") and live_q.get("bid"):
        live_mid = (float(live_q["ask"]) + float(live_q["bid"])) / 2
        if live_mid <= 0:
            reasons.append("invalid live option mid")
    else:
        reasons.append("missing live option bid/ask")

    if reasons:
        result.update({"status": "blocked", "reasons": reasons})
        return result
    result["status"] = "ready"
    if submit:
        submitted = request_json(cfg, "POST", f"{cfg.paper_base_url}/v2/orders", payload=order)
        result.update({"status": "submitted", "submitted_order": submitted})
    return result


def load_signal(path: Path, rank: int = 1, symbol: str | None = None) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    signals = payload.get("signals") or []
    if symbol:
        for sig in signals:
            if str(sig.get("symbol", "")).upper() == symbol.upper():
                return sig
        raise AlpacaError(f"no signal for {symbol} in {path}")
    idx = max(0, rank - 1)
    if idx >= len(signals):
        raise AlpacaError(f"rank {rank} not available in {path}")
    return signals[idx]


def safe_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Alpaca PAPER options guardrail adapter")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("account")
    sub.add_parser("clock")
    sub.add_parser("positions")
    sub.add_parser("orders")
    sub.add_parser("fills")
    stage = sub.add_parser("stage-signal")
    stage.add_argument("--signal-json", type=Path, default=RUNS / "options_signals_latest.json")
    stage.add_argument("--rank", type=int, default=1)
    stage.add_argument("--symbol")
    stage.add_argument("--qty", type=int, default=int(os.getenv("ALPACA_PAPER_OPTION_QTY", "1")))
    stage.add_argument("--max-debit", type=float, default=float(os.getenv("ALPACA_PAPER_MAX_ORDER_DEBIT", "250")))
    stage.add_argument("--submit", action="store_true")
    stage.add_argument("--allow-wide-spread", action="store_true")
    stage.add_argument("--out", type=Path)
    args = parser.parse_args()

    cfg = config_from_env()
    try:
        if args.cmd == "account":
            payload = {"generated_at": now_utc(), "account": account_summary(get_account(cfg)) if cfg.present else None, "credentials_present": cfg.present}
        elif args.cmd == "clock":
            payload = {"generated_at": now_utc(), "clock": get_clock(cfg) if cfg.present else None, "credentials_present": cfg.present}
        elif args.cmd == "positions":
            payload = {"generated_at": now_utc(), "positions": get_positions(cfg) if cfg.present else [], "credentials_present": cfg.present}
        elif args.cmd == "orders":
            payload = {"generated_at": now_utc(), "orders": get_orders(cfg) if cfg.present else [], "credentials_present": cfg.present}
        elif args.cmd == "fills":
            payload = {"generated_at": now_utc(), "fills": get_fills(cfg) if cfg.present else [], "credentials_present": cfg.present}
        elif args.cmd == "stage-signal":
            sig = load_signal(args.signal_json, rank=args.rank, symbol=args.symbol)
            payload = stage_signal_order(cfg, sig, qty=args.qty, submit=args.submit, max_debit=args.max_debit, allow_wide_spread=args.allow_wide_spread)
        else:  # pragma: no cover
            raise AlpacaError("unknown command")
        if getattr(args, "out", None):
            safe_write(args.out, payload)
        print(json.dumps(payload, indent=2, default=str))
    except AlpacaError as exc:
        payload = {"generated_at": now_utc(), "status": "error", "error": str(exc)}
        if getattr(args, "out", None):
            safe_write(args.out, payload)
        print(json.dumps(payload, indent=2), file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
