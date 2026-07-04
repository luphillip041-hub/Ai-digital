#!/usr/bin/env python3
"""Backtest the desk's deterministic entry strategy over historical bars.

What this backtests — honestly:
- ENTRY: the exact live scanner scoring (shared desk_agents/scoring.py),
  a signal fires when a symbol first becomes eligible (score >= min).
- EXIT: the same bracket the paper executor places — stop at the
  entry-day 20dma (or 1.5 ATR), target +2R, time-stop after 20 sessions.
- SIZING: one R of risk per trade; results are reported in R multiples
  and as portfolio return risking 0.5% of equity per trade.

What it does NOT backtest: the LLM debate. Historical LLM decisions
can't be simulated without lookahead bias (the model already knows how
2025 ended), so the desk's judgment layer is forward-tested on the paper
account instead. This script measures the funnel that feeds it.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from desk_agents.marketdata import fetch_ohlcv  # noqa: E402
from desk_agents.scoring import score_window  # noqa: E402

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    load_dotenv(ROOT / ".env.local")
except Exception:
    pass

WARMUP = 55
TIME_STOP_BARS = 20
RISK_PCT_PER_TRADE = 0.5  # % of equity risked per trade in the portfolio sim


@dataclass(frozen=True)
class Trade:
    symbol: str
    entry_bar: int
    exit_bar: int
    entry: float
    stop: float
    target: float
    exit_price: float
    exit_reason: str
    r_multiple: float
    bars_held: int


def backtest_symbol(symbol: str, lookback: str, min_score: float, source: str | None) -> dict:
    data = fetch_ohlcv(symbol, lookback=lookback, source=source)
    if not data.ok:
        return {"symbol": symbol.upper(), "error": data.error or "insufficient history", "trades": []}

    closes, highs, lows, volumes = data.closes, data.highs, data.lows, data.volumes
    trades: list[Trade] = []
    i = WARMUP
    while i < len(closes) - 1:
        card = score_window(closes[: i + 1], highs[: i + 1], lows[: i + 1], volumes[: i + 1],
                            min_score=min_score)
        if not card.eligible:
            i += 1
            continue

        # Signal on bar i → enter on bar i+1 (no same-bar hindsight).
        entry_bar = i + 1
        entry = closes[entry_bar]
        atr_stop = entry * (1 - 1.5 * (card.atr_pct or 3.0) / 100)
        stop = card.ma20 if (card.ma20 and card.ma20 < entry * 0.995) else atr_stop
        stop = max(stop, entry * 0.85)
        risk = entry - stop
        if risk <= 0:
            i += 1
            continue
        target = entry + 2 * risk

        exit_bar, exit_price, reason = None, None, None
        for j in range(entry_bar + 1, min(entry_bar + 1 + TIME_STOP_BARS, len(closes))):
            if lows[j] <= stop:
                exit_bar, exit_price, reason = j, stop, "stop"
                break
            if highs[j] >= target:
                exit_bar, exit_price, reason = j, target, "target"
                break
        if exit_bar is None:
            exit_bar = min(entry_bar + TIME_STOP_BARS, len(closes) - 1)
            exit_price, reason = closes[exit_bar], "time"

        trades.append(Trade(
            symbol=symbol.upper(), entry_bar=entry_bar, exit_bar=exit_bar,
            entry=round(entry, 4), stop=round(stop, 4), target=round(target, 4),
            exit_price=round(exit_price, 4), exit_reason=reason,
            r_multiple=round((exit_price - entry) / risk, 3),
            bars_held=exit_bar - entry_bar,
        ))
        i = exit_bar + 1  # one position per symbol at a time

    return {"symbol": symbol.upper(), "source": data.source, "bars": len(closes),
            "trades": [asdict(t) for t in trades]}


def summarize(all_results: list) -> dict:
    trades = [t for r in all_results for t in r.get("trades", [])]
    if not trades:
        return {"trades": 0, "note": "no signals fired in this window"}
    rs = [t["r_multiple"] for t in trades]
    wins = [r for r in rs if r > 0]
    equity = 100.0
    peak, max_dd = equity, 0.0
    for r in rs:  # sequential 0.5%-risk portfolio sim
        equity *= 1 + (RISK_PCT_PER_TRADE / 100) * r
        peak = max(peak, equity)
        max_dd = max(max_dd, (peak - equity) / peak * 100)
    return {
        "trades": len(trades),
        "win_rate_pct": round(100 * len(wins) / len(trades), 1),
        "avg_r": round(sum(rs) / len(rs), 3),
        "best_r": max(rs),
        "worst_r": min(rs),
        "expectancy_note": "avg_r > 0 means the entry funnel has positive edge before the LLM layer",
        "portfolio_sim": {
            "risk_per_trade_pct": RISK_PCT_PER_TRADE,
            "final_equity_pct": round(equity, 2),
            "return_pct": round(equity - 100, 2),
            "max_drawdown_pct": round(max_dd, 2),
        },
        "exits": {
            "target": sum(1 for t in trades if t["exit_reason"] == "target"),
            "stop": sum(1 for t in trades if t["exit_reason"] == "stop"),
            "time": sum(1 for t in trades if t["exit_reason"] == "time"),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest the scanner entry + bracket exit strategy")
    parser.add_argument("--symbols", default="SPY,QQQ,NVDA,TSLA,SMH,AAPL,MSFT,AMZN,GOOGL,META")
    parser.add_argument("--lookback", default="2y", help="1y or 2y recommended")
    parser.add_argument("--min-score", type=float, default=60)
    parser.add_argument("--data-source", choices=("auto", "alpaca", "yahoo"), default=None)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    results = [backtest_symbol(s, args.lookback, args.min_score, args.data_source) for s in symbols]
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "lookback": args.lookback,
        "min_score": args.min_score,
        "strategy": "scanner eligibility entry → bracket exit (stop=20dma/1.5ATR, target=2R, time=20 bars)",
        "summary": summarize(results),
        "per_symbol": [
            {"symbol": r["symbol"],
             "trades": len(r.get("trades", [])),
             "avg_r": round(sum(t["r_multiple"] for t in r["trades"]) / len(r["trades"]), 3) if r.get("trades") else None,
             "error": r.get("error")}
            for r in results
        ],
        "detail": results,
        "llm_calls_spent": 0,
    }
    out = Path(args.out) if args.out else ROOT / "runs" / f"backtest_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2))
    print(json.dumps({k: payload[k] for k in ("lookback", "strategy", "summary", "per_symbol")}, indent=2))
    print(f"\nsaved={out}")


if __name__ == "__main__":
    main()
