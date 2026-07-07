#!/usr/bin/env python3
"""Build a consolidated zero-LLM desk run card.

The run card turns scattered desk artifacts into one operator view:
- latest stock scanner context
- latest options signals
- Vibe/research packets
- signal outcomes
- standalone Alpaca paper-options service status
- concrete next actions / guardrail notes

It intentionally does not call broker submit paths. Optional --refresh only runs
scanner/outcome refreshers and reads the standalone paper service artifacts.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parent
RUNS = ROOT / "runs"
SCRIPTS = ROOT / "scripts"
PAPER_ROOT = Path(os.getenv("FLIP_DESK_PAPER_OPTIONS_ROOT", str(PROJECT_ROOT / "alpaca-paper-options"))).resolve()
PAPER_RUNS = PAPER_ROOT / "runs"
DEFAULT_SYMBOLS = os.getenv("FLIP_DESK_DEFAULT_SYMBOLS", "SPY,QQQ,NVDA,TSLA,SMH,AAPL,MSFT,AMZN,GOOGL,META")
DEFAULT_OUT = RUNS / "daily_run_card_latest.json"
DEFAULT_MD = RUNS / "daily_run_card_latest.md"
PYTHON = os.getenv("FLIP_DESK_PYTHON", sys.executable)


@dataclass
class ActionItem:
    priority: str
    title: str
    detail: str
    source: str


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"error": str(exc), "path": str(path)}


def latest(pattern: str, base: Path = RUNS) -> Path | None:
    if not base.exists():
        return None
    files = sorted(base.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def run_refresh(args: list[str], cwd: Path = ROOT, timeout: int = 300) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            [PYTHON, *args],
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
        return {"cmd": args, "exit_code": proc.returncode, "stderr_tail": (proc.stderr or "")[-1000:]}
    except Exception as exc:
        return {"cmd": args, "exit_code": -1, "error": repr(exc)}


def refresh_artifacts(symbols: str, include_paper: bool) -> list[dict[str, Any]]:
    RUNS.mkdir(parents=True, exist_ok=True)
    results = [
        run_refresh(["scripts/scan_watchlist.py", "--symbols", symbols, "--max-finalists", "5", "--out", str(RUNS / "run_card_watchlist.json")], timeout=240),
        run_refresh(["scripts/signal_outcome_tracker.py", "--limit", os.getenv("FLIP_DESK_OUTCOME_LIMIT", "50"), "--out", str(RUNS / "signal_outcomes_latest.json"), "--markdown-out", str(RUNS / "signal_outcomes_latest.md")], timeout=360),
    ]
    # Paper refresh is intentionally read-only-ish unless the user calls paperopts separately.
    # This only asks the paper service for account metadata; no analysis/order path.
    if include_paper and PAPER_ROOT.exists():
        results.append(run_refresh(["scripts/alpaca_paper_options.py", "account"], cwd=PAPER_ROOT, timeout=90))
    return results


def compact_scan(payload: dict[str, Any]) -> dict[str, Any]:
    rows = payload.get("finalists") or payload.get("ranked") or []
    return {
        "generated_at": payload.get("generated_at"),
        "top": [
            {
                "symbol": r.get("symbol"),
                "score": r.get("score"),
                "bias": r.get("bias"),
                "eligible": r.get("eligible"),
                "close": r.get("close"),
                "why": (r.get("why") or [])[:4],
                "risk_flags": (r.get("risk_flags") or [])[:4],
            }
            for r in rows[:6]
        ],
    }


def compact_options(payload: dict[str, Any]) -> dict[str, Any]:
    signals = payload.get("signals") or []
    out = []
    for s in signals[:5]:
        setup = s.get("setup") or {}
        contract = s.get("contract") or {}
        mgmt = s.get("management") or {}
        out.append(
            {
                "symbol": s.get("symbol"),
                "score": s.get("total_score"),
                "setup": setup.get("setup"),
                "direction": setup.get("direction"),
                "entry": setup.get("entry"),
                "target": setup.get("target"),
                "stop": setup.get("stop"),
                "contract": f"{contract.get('type', '—')} {contract.get('strike', '—')} exp {contract.get('expiration', '—')}",
                "bid_ask": f"{contract.get('bid', '—')}/{contract.get('ask', '—')}",
                "est_cost": mgmt.get("estimated_contract_cost"),
                "risk_flags": (setup.get("risk_flags") or []) + (contract.get("risk_flags") or []),
            }
        )
    return {"generated_at": payload.get("generated_at"), "signals": out}


def latest_vibe_packets() -> list[dict[str, Any]]:
    packets: list[dict[str, Any]] = []
    files = sorted(RUNS.glob("*vibe*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:5]
    seen: set[str] = set()
    for path in files:
        payload = read_json(path)
        symbol = str(payload.get("symbol") or path.stem).upper()
        if symbol in seen:
            continue
        seen.add(symbol)
        verdict = payload.get("verdict") or {}
        if not verdict:
            continue
        packets.append(
            {
                "symbol": symbol,
                "stance": verdict.get("stance"),
                "bias": verdict.get("bias"),
                "confidence": verdict.get("confidence"),
                "summary": verdict.get("summary"),
                "source_file": str(path.relative_to(ROOT)),
            }
        )
    return packets


def compact_outcomes(payload: dict[str, Any]) -> dict[str, Any]:
    rows = payload.get("outcomes") or []
    return {
        "generated_at": payload.get("generated_at"),
        "summary": payload.get("summary") or {},
        "watch": [
            {
                "symbol": r.get("symbol"),
                "grade": r.get("risk_grade"),
                "status": r.get("status"),
                "move_pct": r.get("move_pct"),
                "progress_to_target_pct": r.get("progress_to_target_pct"),
                "distance_to_stop_pct": r.get("distance_to_stop_pct"),
                "notes": r.get("notes") or [],
            }
            for r in rows[:6]
        ],
    }


def compact_paper() -> dict[str, Any]:
    latest_run = read_json(PAPER_RUNS / "paper_options_latest.json")
    eod = read_json(PAPER_RUNS / "paper_options_eod_latest.json")
    selected = latest_run.get("selected_signal") or {}
    setup = selected.get("setup") or {}
    contract = selected.get("contract") or {}
    order = latest_run.get("paper_order") or {}
    acct = ((eod.get("alpaca") or {}).get("account") or {}).get("account") or {}
    positions = ((eod.get("alpaca") or {}).get("positions") or {}).get("positions") or []
    orders = ((eod.get("alpaca") or {}).get("orders") or {}).get("orders") or []
    return {
        "service_found": PAPER_ROOT.exists(),
        "root": str(PAPER_ROOT),
        "latest_run_at": latest_run.get("generated_at"),
        "mode": latest_run.get("mode"),
        "selected": {
            "symbol": selected.get("symbol"),
            "setup": setup.get("setup"),
            "direction": setup.get("direction"),
            "score": selected.get("total_score"),
            "contract": f"{contract.get('type', '—')} {contract.get('strike', '—')} exp {contract.get('expiration', '—')}",
            "bid_ask": f"{contract.get('bid', '—')}/{contract.get('ask', '—')}",
        },
        "order_status": order.get("status"),
        "blocked_reasons": order.get("reasons") or [],
        "account_status": acct.get("status"),
        "options_level": acct.get("options_trading_level"),
        "open_positions": len(positions),
        "open_orders": len(orders),
    }


def build_actions(scan: dict[str, Any], options: dict[str, Any], outcomes: dict[str, Any], paper: dict[str, Any]) -> list[ActionItem]:
    actions: list[ActionItem] = []
    for row in outcomes.get("watch", []):
        notes = row.get("notes") or []
        if row.get("status") == "stop_hit" or "near stop" in notes:
            actions.append(ActionItem("HIGH", f"Review {row.get('symbol')} outcome risk", f"{row.get('grade')} move {row.get('move_pct')}%, notes: {', '.join(notes) or 'n/a'}", "outcomes"))
        elif row.get("status") == "target_hit" or "near target" in notes:
            actions.append(ActionItem("MED", f"Harvest/trim review for {row.get('symbol')}", f"{row.get('grade')} progress {row.get('progress_to_target_pct')}%", "outcomes"))
    top_opt = (options.get("signals") or [])[:1]
    if top_opt:
        s = top_opt[0]
        cost = s.get("est_cost")
        flags = s.get("risk_flags") or []
        detail = f"{s.get('setup')} {s.get('direction')} score {s.get('score')} | {s.get('contract')} | est cost {cost}"
        if flags:
            detail += f" | flags: {', '.join(flags[:3])}"
        actions.append(ActionItem("MED", f"Preflight top option signal: {s.get('symbol')}", detail, "options"))
    top_scan = (scan.get("top") or [])[:1]
    if top_scan:
        r = top_scan[0]
        actions.append(ActionItem("LOW", f"Refresh research packet for {r.get('symbol')}", f"Scanner score {r.get('score')} bias {r.get('bias')} close {r.get('close')}", "scanner"))
    if paper.get("order_status") == "blocked":
        actions.append(ActionItem("MED", "Paper service blocked latest order", "; ".join(paper.get("blocked_reasons") or ["review guardrails"]), "paper"))
    elif paper.get("order_status") in {"submitted", "filled", "accepted"}:
        actions.append(ActionItem("HIGH", "Review paper order/fill", f"Latest paper order status {paper.get('order_status')}", "paper"))
    if not actions:
        actions.append(ActionItem("LOW", "Run scanner/options refresh", "No urgent action from current artifacts.", "desk"))
    return actions[:8]


def format_markdown(payload: dict[str, Any]) -> str:
    lines = [
        f"# Daily Desk Run Card — {payload.get('generated_at')}",
        "",
        "Research/paper-only operator card. No broker submit path is called by this report.",
        "",
        "## Action Queue",
    ]
    for item in payload.get("action_queue", []):
        lines.append(f"- **{item['priority']}** — {item['title']}: {item['detail']} _({item['source']})_")
    lines += ["", "## Scanner"]
    for row in (payload.get("scanner") or {}).get("top", [])[:6]:
        flags = ", ".join(row.get("risk_flags") or []) or "none"
        why = ", ".join(row.get("why") or []) or "n/a"
        lines.append(f"- **{row.get('symbol')}** score {row.get('score')} bias {row.get('bias')} close {row.get('close')} | {why} | flags: {flags}")
    lines += ["", "## Options Signals"]
    for s in (payload.get("options") or {}).get("signals", [])[:5]:
        lines.append(f"- **{s.get('symbol')}** {s.get('setup')} {s.get('direction')} score {s.get('score')} | {s.get('contract')} bid/ask {s.get('bid_ask')} | entry {s.get('entry')} target {s.get('target')} stop {s.get('stop')}")
    lines += ["", "## Outcomes"]
    outcome_summary = (payload.get("outcomes") or {}).get("summary") or {}
    lines.append(f"Tracked {outcome_summary.get('tracked', 0)} | target {outcome_summary.get('target_hit', 0)} | stop {outcome_summary.get('stop_hit', 0)} | working {outcome_summary.get('working', 0)} | against {outcome_summary.get('against', 0)} | avg {outcome_summary.get('avg_move_pct')}%")
    for row in (payload.get("outcomes") or {}).get("watch", [])[:6]:
        notes = ", ".join(row.get("notes") or [])
        lines.append(f"- **{row.get('symbol')}** {row.get('grade')} move {row.get('move_pct')}% progress {row.get('progress_to_target_pct')}% stop distance {row.get('distance_to_stop_pct')}% {notes}")
    paper = payload.get("paper") or {}
    lines += [
        "",
        "## Paper Options Service",
        f"- Service: {'found' if paper.get('service_found') else 'missing'} | mode {paper.get('mode')} | account {paper.get('account_status')} | options level {paper.get('options_level')}",
        f"- Latest: {paper.get('selected', {}).get('symbol')} {paper.get('selected', {}).get('setup')} | {paper.get('selected', {}).get('contract')} | order {paper.get('order_status')}",
    ]
    if paper.get("blocked_reasons"):
        lines.append(f"- Blocked: {'; '.join(paper.get('blocked_reasons') or [])}")
    lines += ["", "## Vibe / Research Packets"]
    for v in payload.get("vibe_packets", [])[:5]:
        lines.append(f"- **{v.get('symbol')}** {v.get('stance')} | bias {v.get('bias')} | conf {v.get('confidence')}/10 — {v.get('summary')}")
    return "\n".join(lines) + "\n"


def build_payload(symbols: str, refreshed: list[dict[str, Any]]) -> dict[str, Any]:
    scan_path = RUNS / "run_card_watchlist.json"
    scan_payload = read_json(scan_path) or read_json(RUNS / "ui_watchlist_scan.json") or read_json(RUNS / "latest_watchlist_scan.json")
    options_payload = read_json(RUNS / "ui_options_signals.json") or read_json(RUNS / "options_signals_latest.json") or read_json(latest("*options*signals*.json") or Path("/nonexistent"))
    outcomes_payload = read_json(RUNS / "signal_outcomes_latest.json")
    scanner = compact_scan(scan_payload)
    options = compact_options(options_payload)
    outcomes = compact_outcomes(outcomes_payload)
    paper = compact_paper()
    actions = build_actions(scanner, options, outcomes, paper)
    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "mode": "zero_llm_run_card",
        "symbols": [s.strip().upper() for s in symbols.split(",") if s.strip()],
        "refresh_results": refreshed,
        "scanner": scanner,
        "options": options,
        "outcomes": outcomes,
        "paper": paper,
        "vibe_packets": latest_vibe_packets(),
        "action_queue": [asdict(a) for a in actions],
        "safety": [
            "No live broker submit path called by run card.",
            "Paper options submit remains controlled by standalone service guardrails.",
            "Scanner/outcomes use delayed/proxy data unless upgraded data source is configured.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbols", default=DEFAULT_SYMBOLS)
    parser.add_argument("--refresh", action="store_true", help="Refresh scanner and outcome artifacts before building the card.")
    parser.add_argument("--include-paper-account-refresh", action="store_true", help="Also ask standalone paper service for account metadata; never submits orders.")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--markdown-out", type=Path, default=DEFAULT_MD)
    args = parser.parse_args()

    refreshed = refresh_artifacts(args.symbols, args.include_paper_account_refresh) if args.refresh else []
    payload = build_payload(args.symbols, refreshed)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    args.markdown_out.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_out.write_text(format_markdown(payload), encoding="utf-8")
    print(json.dumps(payload, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
