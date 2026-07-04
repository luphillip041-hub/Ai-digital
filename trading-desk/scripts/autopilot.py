#!/usr/bin/env python3
"""Autopilot: scan the market, research finalists, paper-trade the BUYs.

One pass = one decision cycle, built for cron/launchd or the dashboard:

    1. zero-LLM scan of the watchlist        → finalists
    2. desk analysis on the top N finalists  → BUY/SELL/HOLD each
    3. execute BUYs as bracket orders        → Alpaca PAPER account only

Dry-run is the default: it prints/saves exactly what it WOULD do.
Arm real paper execution with --execute. Budget guard still applies to
the research step; if the monthly cap blocks a run, that ticker is
skipped, never forced.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from desk_agents.execution import PaperBroker, execute_decision  # noqa: E402
from desk_agents.marketdata import MarketBrief  # noqa: E402

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    load_dotenv(ROOT / ".env.local")
except Exception:
    pass

PYTHON = sys.executable


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scan → research → paper-trade, one pass")
    parser.add_argument("--symbols", default=os.getenv(
        "FLIP_DESK_DEFAULT_SYMBOLS", "SPY,QQQ,NVDA,TSLA,SMH,AAPL,MSFT,AMZN,GOOGL,META"))
    parser.add_argument("--max-research", type=int, default=int(os.getenv("FLIP_DESK_AUTOPILOT_MAX_RESEARCH", "2")),
                        help="How many top finalists get a desk run (8 LLM calls each)")
    parser.add_argument("--model-profile", default="cheap")
    parser.add_argument("--execute", action="store_true",
                        help="Actually place paper bracket orders. Default is dry-run.")
    parser.add_argument("--out", default=None)
    return parser.parse_args()


def run_script(cmd: list, timeout: int) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=ROOT, text=True, timeout=timeout,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)


def main() -> None:
    args = parse_args()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    report: dict = {
        "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mode": "execute" if args.execute else "dry_run",
        "symbols": args.symbols,
        "steps": [],
        "trades": [],
    }

    print(f"=== Autopilot pass ({report['mode']}) ===")

    # 1. scan (zero LLM)
    scan_out = ROOT / "runs" / f"autopilot_scan_{stamp}.json"
    proc = run_script([PYTHON, "scripts/scan_watchlist.py", "--symbols", args.symbols,
                       "--out", str(scan_out)], timeout=300)
    if proc.returncode != 0 or not scan_out.exists():
        raise SystemExit(f"scan failed:\n{proc.stdout[-1500:]}")
    scan = json.loads(scan_out.read_text())
    finalists = [r["symbol"] for r in scan.get("finalists", [])]
    report["steps"].append({"step": "scan", "finalists": finalists})
    print(f"scan finalists: {finalists or 'none'}")

    # 2 + 3. research the top finalists, execute BUYs
    for symbol in finalists[: max(args.max_research, 0)]:
        run_out = ROOT / "runs" / f"autopilot_{symbol}_{stamp}.json"
        print(f"\n--- desk research: {symbol} ---")
        proc = run_script([PYTHON, "scripts/run_desk_analysis.py", symbol,
                           "--model-profile", args.model_profile, "--json-out", str(run_out)],
                          timeout=1800)
        if not run_out.exists():
            report["steps"].append({"step": "research", "symbol": symbol, "status": "failed",
                                    "detail": proc.stdout[-800:]})
            print(f"research failed for {symbol}; skipping")
            continue
        payload = json.loads(run_out.read_text())
        decision = payload.get("decision") or {}
        status = payload.get("status")
        report["steps"].append({"step": "research", "symbol": symbol, "status": status,
                                "action": decision.get("action"), "file": run_out.name})
        print(f"decision: {decision.get('action')} ({decision.get('conviction')})")
        if status != "completed":
            continue

        scan_row = next((r for r in scan.get("ranked", []) if r["symbol"] == symbol), {})
        brief = MarketBrief(
            symbol=symbol, ok=True, source=scan_row.get("source", "scan"),
            close=scan_row.get("close"), ma20=scan_row.get("ma20"), ma50=scan_row.get("ma50"),
            rsi14=scan_row.get("rsi14"), atr_pct=scan_row.get("atr_pct"),
            volume_ratio=scan_row.get("volume_ratio"),
            ret5_pct=scan_row.get("five_day_return_pct"), ret20_pct=scan_row.get("twenty_day_return_pct"),
        )
        trade = execute_decision(brief, decision, execute=args.execute)
        trade["symbol"] = symbol
        report["trades"].append(trade)
        plan = trade["plan"]
        if plan["action"] == "buy":
            verb = "PLACED" if trade["executed"] else "WOULD PLACE (dry-run)"
            print(f"{verb}: buy {plan['qty']} {symbol} ~${plan['entry_ref']} "
                  f"stop {plan['stop_price']} target {plan['target_price']} "
                  f"(risk ${plan['risk_dollars']} on ${plan['equity']:,.0f} equity)")
        else:
            print(f"no trade: {plan['reason']}")

    # snapshot the paper account after the pass
    try:
        broker = PaperBroker()
        account = broker.account()
        report["account"] = {
            "equity": account.get("equity"),
            "cash": account.get("cash"),
            "buying_power": account.get("buying_power"),
        }
        report["positions"] = [
            {"symbol": p["symbol"], "qty": p["qty"], "avg_entry": p["avg_entry_price"],
             "market_value": p["market_value"], "unrealized_pl": p["unrealized_pl"],
             "unrealized_plpc": p["unrealized_plpc"]}
            for p in broker.positions()
        ]
    except Exception as exc:
        report["account_error"] = repr(exc)

    out = Path(args.out) if args.out else ROOT / "runs" / f"autopilot_{stamp}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, default=str))
    print(f"\nautopilot report saved: {out}")
    if not args.execute and report["trades"]:
        print("dry-run only — re-run with --execute to place these paper orders")


if __name__ == "__main__":
    main()
