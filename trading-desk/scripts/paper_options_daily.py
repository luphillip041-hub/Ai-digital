#!/usr/bin/env python3
"""Daily paper-options trader for Flip's trade desk.

Runs a full low-burn market pass, stages/optionally submits the top PAPER option
signal through Alpaca guardrails, and writes an EOD report artifact.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    load_dotenv = None

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs"
SCRIPTS = ROOT / "scripts"
PYTHON = os.getenv("FLIP_DESK_PYTHON", sys.executable)
ET = ZoneInfo("America/New_York")
DEFAULT_SYMBOLS = os.getenv("FLIP_DESK_DEFAULT_SYMBOLS", "SPY,QQQ,NVDA,TSLA,SMH,AAPL,MSFT,AMZN,GOOGL,META")


def load_env() -> None:
    if load_dotenv:
        load_dotenv(ROOT / ".env")
        load_dotenv(ROOT / ".env.local")


def now_utc() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%d_%H%M%S")


def today_et() -> str:
    return datetime.now(ET).date().isoformat()


def run(args: list[str], timeout: int = 300) -> dict[str, Any]:
    proc = subprocess.run(
        [PYTHON, *args],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )
    return {"args": args, "exit_code": proc.returncode, "stdout": proc.stdout[-6000:], "stderr": proc.stderr[-3000:]}


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"error": str(exc), "path": str(path)}


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def write_markdown(path: Path, text: str) -> None:
    path.parent.mkdir(exist_ok=True)
    path.write_text(text, encoding="utf-8")


def safe_rel(path: Path | str | None) -> str:
    if not path:
        return ""
    try:
        return str(Path(path).relative_to(ROOT))
    except Exception:
        return str(path)


def pick_signal(options_payload: dict[str, Any]) -> dict[str, Any] | None:
    signals = options_payload.get("signals") or []
    if not signals:
        return None
    # Favor top-ranked but require contract and no severe liquidity flags.
    for sig in signals:
        contract = sig.get("contract") or {}
        flags = set((contract.get("risk_flags") or []) + ((sig.get("setup") or {}).get("risk_flags") or []))
        if contract and "very_wide_spread" not in flags and "low_open_interest" not in flags:
            return sig
    return signals[0]


def format_signal_line(sig: dict[str, Any] | None) -> str:
    if not sig:
        return "No options signal selected."
    setup = sig.get("setup") or {}
    c = sig.get("contract") or {}
    return (
        f"{sig.get('symbol')} {setup.get('setup')} {setup.get('direction')} | "
        f"score {sig.get('total_score')} | entry {setup.get('entry')} target {setup.get('target')} stop {setup.get('stop')} | "
        f"{c.get('type')} {c.get('strike')} exp {c.get('expiration')} bid/ask {c.get('bid')}/{c.get('ask')}"
    )


def build_iteration(symbols: str, *, submit: bool, max_debit: float, max_signals: int) -> dict[str, Any]:
    load_env()
    RUNS.mkdir(exist_ok=True)
    run_id = f"paper_options_{stamp()}"
    scan_json = RUNS / f"{run_id}_watchlist.json"
    options_json = RUNS / f"{run_id}_options.json"
    options_md = RUNS / f"{run_id}_options.md"
    order_json = RUNS / f"{run_id}_order.json"
    report_md = RUNS / f"{run_id}_report.md"
    report_json = RUNS / f"{run_id}_report.json"

    stock_run = run(
        [str(SCRIPTS / "scan_watchlist.py"), "--symbols", symbols, "--max-finalists", "5", "--out", str(scan_json)],
        timeout=240,
    )
    options_run = run(
        [
            str(SCRIPTS / "options_signal_scanner.py"),
            "--symbols",
            symbols,
            "--max-signals",
            str(max_signals),
            "--out",
            str(options_json),
            "--markdown-out",
            str(options_md),
        ],
        timeout=480,
    )
    stock_payload = read_json(scan_json)
    options_payload = read_json(options_json)
    selected = pick_signal(options_payload)

    order_payload: dict[str, Any] = {"status": "skipped", "reason": "no selected signal"}
    order_run: dict[str, Any] | None = None
    if selected:
        args = [
            str(SCRIPTS / "alpaca_paper_options.py"),
            "stage-signal",
            "--signal-json",
            str(options_json),
            "--symbol",
            str(selected.get("symbol")),
            "--max-debit",
            str(max_debit),
            "--out",
            str(order_json),
        ]
        if submit:
            args.append("--submit")
        order_run = run(args, timeout=90)
        order_payload = read_json(order_json) if order_json.exists() else {"status": "error", "stderr": order_run.get("stderr")}

    report = {
        "generated_at": now_utc(),
        "run_id": run_id,
        "trade_date_et": today_et(),
        "mode": "submit" if submit else "dry_run",
        "universe": symbols,
        "paths": {
            "scan_json": safe_rel(scan_json),
            "options_json": safe_rel(options_json),
            "options_md": safe_rel(options_md),
            "order_json": safe_rel(order_json) if order_json.exists() else None,
            "report_md": safe_rel(report_md),
        },
        "stock_scan": {
            "exit_code": stock_run["exit_code"],
            "finalists": stock_payload.get("finalists") or [],
            "ranked_top": (stock_payload.get("ranked") or [])[:5],
        },
        "options_scan": {
            "exit_code": options_run["exit_code"],
            "signals": options_payload.get("signals") or [],
        },
        "selected_signal": selected,
        "paper_order": order_payload,
        "subprocess": {"stock": stock_run, "options": options_run, "order": order_run},
        "safety": {
            "paper_only": True,
            "live_execution": False,
            "submit_requires_flag": True,
            "max_debit": max_debit,
            "note": "Default dry-run. To submit paper orders, set explicit --submit or FLIP_DESK_PAPER_OPTIONS_AUTO_SUBMIT=true.",
        },
    }
    write_json(report_json, report)
    write_markdown(report_md, format_report(report))
    # Also write stable latest pointers for dashboard/Discord.
    write_json(RUNS / "paper_options_latest.json", report)
    write_markdown(RUNS / "paper_options_latest.md", format_report(report))
    return report


def account_block() -> dict[str, Any]:
    account = run([str(SCRIPTS / "alpaca_paper_options.py"), "account"], timeout=40)
    positions = run([str(SCRIPTS / "alpaca_paper_options.py"), "positions"], timeout=40)
    orders = run([str(SCRIPTS / "alpaca_paper_options.py"), "orders"], timeout=40)
    fills = run([str(SCRIPTS / "alpaca_paper_options.py"), "fills"], timeout=40)
    def parse(res: dict[str, Any]) -> dict[str, Any]:
        try:
            return json.loads(res.get("stdout") or "{}")
        except Exception:
            return {"exit_code": res.get("exit_code"), "stderr": res.get("stderr")}
    return {"account": parse(account), "positions": parse(positions), "orders": parse(orders), "fills": parse(fills)}


def build_eod_report() -> dict[str, Any]:
    latest = read_json(RUNS / "paper_options_latest.json")
    acct = account_block()
    payload = {
        "generated_at": now_utc(),
        "trade_date_et": today_et(),
        "latest_iteration": latest,
        "alpaca": acct,
        "report_md": str(RUNS / f"paper_options_eod_{today_et()}.md"),
    }
    md = format_eod(payload)
    out = RUNS / f"paper_options_eod_{today_et()}.json"
    md_out = RUNS / f"paper_options_eod_{today_et()}.md"
    write_json(out, payload)
    write_markdown(md_out, md)
    write_json(RUNS / "paper_options_eod_latest.json", payload)
    write_markdown(RUNS / "paper_options_eod_latest.md", md)
    return payload


def format_report(report: dict[str, Any]) -> str:
    finalists = report.get("stock_scan", {}).get("finalists") or []
    signals = report.get("options_scan", {}).get("signals") or []
    selected = report.get("selected_signal")
    order = report.get("paper_order") or {}
    lines = [
        f"# Paper Options Desk Report — {report.get('trade_date_et')}",
        "",
        f"Generated: {report.get('generated_at')} UTC",
        f"Mode: **{report.get('mode')}** — paper only",
        "",
        "## Market analysis",
    ]
    if finalists:
        for row in finalists[:5]:
            lines.append(f"- {row.get('symbol')}: score {row.get('score')} bias {row.get('bias')} close {row.get('close')} — {', '.join((row.get('why') or [])[:3])}")
    else:
        lines.append("- No stock finalists from scanner.")
    lines += ["", "## Options analysis"]
    if signals:
        for sig in signals[:5]:
            lines.append(f"- {format_signal_line(sig)}")
    else:
        lines.append("- No qualifying options signals.")
    lines += ["", "## Selected paper action", format_signal_line(selected), ""]
    lines.append(f"Order status: **{order.get('status', 'n/a')}**")
    if order.get("reasons"):
        lines.append("Blocked reasons: " + "; ".join(order.get("reasons") or []))
    if order.get("order"):
        lines.append("```json")
        lines.append(json.dumps(order.get("order"), indent=2))
        lines.append("```")
    lines += ["", "_Research/paper only. No real-money execution._"]
    return "\n".join(lines) + "\n"


def format_eod(payload: dict[str, Any]) -> str:
    latest = payload.get("latest_iteration") or {}
    alpaca = payload.get("alpaca") or {}
    positions = (alpaca.get("positions") or {}).get("positions") or []
    orders = (alpaca.get("orders") or {}).get("orders") or []
    fills = (alpaca.get("fills") or {}).get("fills") or []
    acct = (alpaca.get("account") or {}).get("account") or {}
    lines = [
        f"# End-of-Day Paper Options Report — {payload.get('trade_date_et')}",
        "",
        f"Generated: {payload.get('generated_at')} UTC",
        "",
        "## Account",
        f"- Status: {acct.get('status', 'n/a')}",
        f"- Buying power: {acct.get('buying_power', 'n/a')}",
        f"- Options buying power: {acct.get('options_buying_power', 'n/a')}",
        f"- Options level: {acct.get('options_trading_level', 'n/a')}",
        "",
        "## Latest desk action",
        f"- Run: {latest.get('run_id', 'n/a')}",
        f"- Mode: {latest.get('mode', 'n/a')}",
        f"- Selected: {format_signal_line(latest.get('selected_signal'))}",
        f"- Order status: {(latest.get('paper_order') or {}).get('status', 'n/a')}",
        "",
        "## Open positions",
    ]
    if positions:
        for p in positions:
            lines.append(f"- {p.get('symbol')} qty {p.get('qty')} avg {p.get('avg_entry_price')} current {p.get('current_price')} uPL {p.get('unrealized_pl')} ({p.get('unrealized_plpc')})")
    else:
        lines.append("- None")
    lines += ["", "## Open orders"]
    if orders:
        for o in orders[:10]:
            lines.append(f"- {o.get('symbol')} {o.get('side')} {o.get('qty')} {o.get('type')} {o.get('limit_price')} status {o.get('status')}")
    else:
        lines.append("- None")
    lines += ["", "## Fills today/recent"]
    if fills:
        for f in fills[:20]:
            lines.append(f"- {f.get('transaction_time')} {f.get('symbol')} {f.get('side')} qty {f.get('qty')} price {f.get('price')}")
    else:
        lines.append("- None")
    lines += ["", "_Paper account only. Review fills and scanner quality before enabling submit mode._"]
    return "\n".join(lines) + "\n"


def main() -> None:
    load_env()
    parser = argparse.ArgumentParser(description="Run daily paper options analysis/trading/report cycle")
    sub = parser.add_subparsers(dest="cmd", required=True)
    runp = sub.add_parser("run-iteration")
    runp.add_argument("--symbols", default=DEFAULT_SYMBOLS)
    runp.add_argument("--max-signals", type=int, default=int(os.getenv("FLIP_DESK_MAX_OPTION_SIGNALS", "3")))
    runp.add_argument("--max-debit", type=float, default=float(os.getenv("ALPACA_PAPER_MAX_ORDER_DEBIT", "250")))
    runp.add_argument("--submit", action="store_true")
    sub.add_parser("eod-report")
    args = parser.parse_args()
    if args.cmd == "run-iteration":
        submit = args.submit or os.getenv("FLIP_DESK_PAPER_OPTIONS_AUTO_SUBMIT", "false").lower() == "true"
        payload = build_iteration(args.symbols, submit=submit, max_debit=args.max_debit, max_signals=args.max_signals)
    else:
        payload = build_eod_report()
    print(json.dumps(payload, indent=2, default=str))


if __name__ == "__main__":
    main()
