#!/usr/bin/env python3
"""Vibe-Trading inspired research bridge for Flip's trade desk.

This does not vendor HKUDS/Vibe-Trading code. It creates a normalized research
packet that the desk/UI/Discord can consume, and optionally launches an external
Vibe-Trading CLI sidecar when installed.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs"
PYTHON = os.getenv("FLIP_DESK_PYTHON", sys.executable)

DEFAULT_PROMPT_TEMPLATE = """Research {symbol} for the Y4Y trade desk.
Return a concise, evidence-backed trading brief with:
- bias: bullish / bearish / neutral
- setup quality
- data freshness caveats
- key levels: entry zone, invalidation, target zone
- options suitability if relevant
- risk factors
- what would change the thesis
No broker execution. Research/paper only."""


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def run_script(args: list[str], timeout: int = 240) -> tuple[int, str, str]:
    proc = subprocess.run(
        [PYTHON, *args],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )
    return proc.returncode, proc.stdout, proc.stderr


def latest_signal_for(symbol: str) -> dict[str, Any] | None:
    payloads = [read_json(RUNS / "ui_options_signals.json"), read_json(RUNS / "options_signals_latest.json")]
    for payload in payloads:
        for sig in payload.get("signals") or []:
            if str(sig.get("symbol", "")).upper() == symbol:
                return sig
    return None


def ensure_scanner_context(symbol: str, refresh: bool) -> dict[str, Any]:
    out = RUNS / f"vibe_context_{symbol}.json"
    if refresh or not out.exists():
        rc, stdout, stderr = run_script(
            [
                str(ROOT / "scripts" / "scan_watchlist.py"),
                "--symbols",
                symbol,
                "--min-score",
                "0",
                "--max-finalists",
                "1",
                "--out",
                str(out),
            ],
            timeout=180,
        )
        if rc != 0:
            return {"status": "scanner_error", "error": (stderr or stdout)[-1200:]}
    return read_json(out)


def concise_scanner_summary(scan: dict[str, Any], symbol: str) -> dict[str, Any]:
    rows = scan.get("ranked") or scan.get("finalists") or []
    item = rows[0] if rows else {}
    return {
        "symbol": symbol,
        "score": item.get("score"),
        "bias": item.get("bias"),
        "eligible": item.get("eligible"),
        "close": item.get("close"),
        "rsi14": item.get("rsi14"),
        "atr_pct": item.get("atr_pct"),
        "volume_ratio": item.get("volume_ratio"),
        "five_day_return_pct": item.get("five_day_return_pct"),
        "twenty_day_return_pct": item.get("twenty_day_return_pct"),
        "why": item.get("why") or [],
        "risk_flags": item.get("risk_flags") or [],
    }


def extract_signal_summary(signal: dict[str, Any] | None) -> dict[str, Any] | None:
    if not signal:
        return None
    setup = signal.get("setup") or {}
    contract = signal.get("contract") or {}
    mgmt = signal.get("management") or {}
    return {
        "rank": signal.get("rank"),
        "total_score": signal.get("total_score"),
        "setup": setup.get("setup"),
        "direction": setup.get("direction"),
        "entry": setup.get("entry"),
        "target": setup.get("target"),
        "stop": setup.get("stop"),
        "reward_risk": setup.get("reward_risk"),
        "why": setup.get("why") or [],
        "contract": {
            "type": contract.get("type"),
            "expiration": contract.get("expiration"),
            "dte": contract.get("dte"),
            "strike": contract.get("strike"),
            "bid": contract.get("bid"),
            "ask": contract.get("ask"),
            "mid": contract.get("mid"),
            "volume": contract.get("volume"),
            "open_interest": contract.get("open_interest"),
            "implied_volatility": contract.get("implied_volatility"),
            "spread_pct": contract.get("spread_pct"),
            "approx_delta": contract.get("approx_delta"),
            "breakeven": contract.get("breakeven"),
        },
        "management": {
            "take_profit": mgmt.get("take_profit"),
            "stop_loss": mgmt.get("stop_loss"),
            "time_stop": mgmt.get("time_stop"),
            "estimated_contract_cost": mgmt.get("estimated_contract_cost"),
        },
    }


def deterministic_verdict(scan_summary: dict[str, Any], signal_summary: dict[str, Any] | None) -> dict[str, Any]:
    score = scan_summary.get("score") or 0
    bias = scan_summary.get("bias") or "neutral"
    flags = list(scan_summary.get("risk_flags") or [])
    if signal_summary:
        total = signal_summary.get("total_score") or 0
        direction = signal_summary.get("direction") or bias
        rr = signal_summary.get("reward_risk") or "n/a"
        if total >= 75 and not flags:
            stance = "research-approved candidate"
        elif total >= 60:
            stance = "watchlist candidate"
        else:
            stance = "weak candidate"
        return {
            "stance": stance,
            "bias": direction,
            "confidence": min(9, round(float(total) / 12, 1)),
            "summary": f"{direction} {signal_summary.get('setup')} with options score {total}; R/R {rr}.",
        }
    if score >= 70:
        stance = "strong stock setup"
    elif score >= 55:
        stance = "watchlist setup"
    else:
        stance = "no clean edge"
    return {
        "stance": stance,
        "bias": bias,
        "confidence": min(8, round(float(score) / 12, 1)) if score else 2,
        "summary": f"{bias} scanner bias with score {score}; needs options/agent confirmation before action.",
    }


def call_vibe_cli(symbol: str, prompt: str, timeout: int) -> dict[str, Any]:
    cmd = shutil.which(os.getenv("VIBE_TRADING_BIN", "vibe-trading"))
    if not cmd:
        return {"enabled": False, "status": "not_installed", "message": "vibe-trading CLI not found"}
    try:
        proc = subprocess.run(
            [cmd, "run", "-p", prompt],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
        return {
            "enabled": True,
            "status": "ok" if proc.returncode == 0 else "error",
            "exit_code": proc.returncode,
            "stdout_tail": proc.stdout[-6000:],
            "stderr_tail": proc.stderr[-2000:],
        }
    except Exception as exc:
        return {"enabled": True, "status": "exception", "error": repr(exc)}


def build_report(symbol: str, refresh: bool, run_vibe: bool, timeout: int) -> dict[str, Any]:
    symbol = symbol.upper().strip()
    scan = ensure_scanner_context(symbol, refresh)
    scan_summary = concise_scanner_summary(scan, symbol)
    signal_summary = extract_signal_summary(latest_signal_for(symbol))
    verdict = deterministic_verdict(scan_summary, signal_summary)
    prompt = DEFAULT_PROMPT_TEMPLATE.format(symbol=symbol)
    vibe = call_vibe_cli(symbol, prompt, timeout) if run_vibe else {"enabled": False, "status": "skipped"}
    report = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "symbol": symbol,
        "source": "desk_scanner + optional external Vibe-Trading sidecar",
        "safety": {
            "execution": "disabled",
            "live_orders": False,
            "notes": "Research/paper only. Vibe output is advisory and must flow through desk risk rules.",
        },
        "verdict": verdict,
        "desk_context": scan_summary,
        "option_signal": signal_summary,
        "vibe_sidecar": vibe,
        "recommended_next_steps": [
            "Use this as analyst context, not an order signal.",
            "If useful, run !preflight then !desk for full low-burn analysis.",
            "Track outcome in run cards before considering execution integrations.",
        ],
    }
    return report


def format_markdown(report: dict[str, Any]) -> str:
    v = report.get("verdict") or {}
    d = report.get("desk_context") or {}
    opt = report.get("option_signal") or {}
    lines = [
        f"# Vibe Research Bridge — {report.get('symbol')}",
        "",
        f"Generated: {report.get('generated_at')} UTC",
        "",
        f"**Stance:** {v.get('stance')}  ",
        f"**Bias:** {v.get('bias')}  ",
        f"**Confidence:** {v.get('confidence')}/10  ",
        f"**Summary:** {v.get('summary')}",
        "",
        "## Desk scanner context",
        f"- Score: {d.get('score')}",
        f"- Close: {d.get('close')}",
        f"- RSI14: {d.get('rsi14')}",
        f"- ATR%: {d.get('atr_pct')}",
        f"- Why: {', '.join(d.get('why') or []) or 'n/a'}",
        f"- Flags: {', '.join(d.get('risk_flags') or []) or 'none'}",
        "",
    ]
    if opt:
        c = opt.get("contract") or {}
        lines += [
            "## Option candidate",
            f"- Setup: {opt.get('setup')} {opt.get('direction')}",
            f"- Entry / Target / Stop: {opt.get('entry')} / {opt.get('target')} / {opt.get('stop')}",
            f"- Contract: {c.get('type')} {c.get('strike')} exp {c.get('expiration')} ({c.get('dte')} DTE)",
            f"- Bid/Ask: {c.get('bid')} / {c.get('ask')} | Vol/OI: {c.get('volume')} / {c.get('open_interest')}",
            "",
        ]
    sidecar = report.get("vibe_sidecar") or {}
    lines += [
        "## Vibe sidecar",
        f"- Status: {sidecar.get('status')}",
        f"- Enabled: {sidecar.get('enabled')}",
        "",
        "Research/paper only — no broker execution.",
    ]
    if sidecar.get("stdout_tail"):
        lines += ["", "### Vibe output tail", "```text", sidecar["stdout_tail"][-3500:], "```"]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a Vibe-Trading style research packet for the desk")
    parser.add_argument("symbol")
    parser.add_argument("--run-vibe", action="store_true", help="Call external vibe-trading CLI if installed")
    parser.add_argument("--refresh", action="store_true", help="Refresh deterministic scanner context")
    parser.add_argument("--timeout", type=int, default=int(os.getenv("FLIP_DESK_VIBE_TIMEOUT_SECONDS", "900")))
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--markdown-out", type=Path)
    args = parser.parse_args()

    RUNS.mkdir(exist_ok=True)
    report = build_report(args.symbol, args.refresh, args.run_vibe, args.timeout)
    json_out = args.json_out or RUNS / f"vibe_research_{report['symbol']}_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.json"
    md_out = args.markdown_out or json_out.with_suffix(".md")
    json_out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    md_out.write_text(format_markdown(report), encoding="utf-8")
    report["json_path"] = str(json_out)
    report["markdown_path"] = str(md_out)
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
