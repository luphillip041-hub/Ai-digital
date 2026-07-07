#!/usr/bin/env python3
"""Track forward outcomes for desk option-signal artifacts.

This is a zero-LLM accountability layer: it scans saved option-signal JSON files,
fetches current underlying prices, compares actual move vs the original entry /
target / stop, and writes stable JSON + Markdown artifacts for the UI/Discord bot.

It intentionally tracks the *underlying setup* first because free/delayed data often
lacks reliable historical OPRA bars. Option contract quote tracking can be added
later when Tradier/Alpaca OPRA snapshots are wired as the canonical source.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs"
DEFAULT_OUT = RUNS / "signal_outcomes_latest.json"
DEFAULT_MD = RUNS / "signal_outcomes_latest.md"


@dataclass
class OutcomeRow:
    key: str
    symbol: str
    generated_at: str | None
    age_days: float | None
    setup: str
    direction: str
    entry: float | None
    target: float | None
    stop: float | None
    current: float | None
    move_pct: float | None
    progress_to_target_pct: float | None
    distance_to_stop_pct: float | None
    status: str
    risk_grade: str
    score: float | None
    contract: str
    source_file: str
    notes: list[str]


def read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def as_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        out = float(value)
        if math.isnan(out) or math.isinf(out):
            return None
        return out
    except Exception:
        return None


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except Exception:
        return None


def signal_identity(sig: dict[str, Any], generated_at: str | None, source: Path) -> str:
    setup = sig.get("setup") or {}
    contract = sig.get("contract") or {}
    parts = [
        str(sig.get("symbol") or ""),
        str(setup.get("direction") or ""),
        str(contract.get("type") or ""),
        str(contract.get("expiration") or ""),
        str(contract.get("strike") or ""),
        str(round(as_float(setup.get("entry")) or 0, 2)),
        str(generated_at or source.name),
    ]
    return "|".join(parts)


def extract_signals(payload: dict[str, Any], source: Path) -> list[tuple[dict[str, Any], str | None]]:
    generated_at = payload.get("generated_at")
    out: list[tuple[dict[str, Any], str | None]] = []
    if isinstance(payload.get("signals"), list):
        out.extend((s, generated_at) for s in payload["signals"] if isinstance(s, dict))
    selected = payload.get("selected_signal")
    if isinstance(selected, dict) and selected:
        out.append((selected, generated_at))
    opt = payload.get("option_signal")
    if isinstance(opt, dict) and opt:
        # Vibe bridge stores a reduced option shape; keep only if entry context exists.
        out.append((opt, generated_at))
    return out


def discover_signals(limit: int) -> list[tuple[dict[str, Any], str | None, Path]]:
    patterns = [
        "*options*signals*.json",
        "*options_scan*.json",
        "paper_options_*_report.json",
        "paper_options_latest.json",
        "ui_options_signals.json",
        "discord_options_scan_*.json",
        "ui_vibe_*.json",
    ]
    files: list[Path] = []
    for pattern in patterns:
        files.extend(RUNS.glob(pattern))
    files = sorted(set(files), key=lambda p: p.stat().st_mtime, reverse=True)
    seen: set[str] = set()
    rows: list[tuple[dict[str, Any], str | None, Path]] = []
    for path in files:
        payload = read_json(path)
        for sig, generated_at in extract_signals(payload, path):
            key = signal_identity(sig, generated_at, path)
            if key in seen:
                continue
            seen.add(key)
            rows.append((sig, generated_at, path))
            if len(rows) >= limit:
                return rows
    return rows


def fetch_prices(symbols: list[str]) -> dict[str, float]:
    if not symbols:
        return {}
    try:
        import yfinance as yf  # type: ignore
    except Exception as exc:
        raise RuntimeError(f"yfinance unavailable: {exc}") from exc

    prices: dict[str, float] = {}
    for symbol in sorted(set(symbols)):
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="5d", interval="1d", auto_adjust=True)
            if hist is not None and not hist.empty:
                prices[symbol] = round(float(hist["Close"].dropna().iloc[-1]), 4)
        except Exception:
            continue
    return prices


def classify(direction: str, entry: float | None, target: float | None, stop: float | None, current: float | None) -> tuple[str, str, list[str], float | None, float | None, float | None]:
    notes: list[str] = []
    if entry is None or current is None:
        return "untracked", "⚪ DATA", notes + ["missing entry/current price"], None, None, None

    longish = direction.lower() not in {"short", "bearish", "put"}
    move_pct = ((current - entry) / entry * 100.0) if longish else ((entry - current) / entry * 100.0)

    progress = None
    if target is not None and target != entry:
        denom = abs(target - entry)
        if denom > 0:
            progress = ((current - entry) / (target - entry) * 100.0) if longish else ((entry - current) / (entry - target) * 100.0)

    dist_stop = None
    if stop is not None and current:
        if longish:
            dist_stop = (current - stop) / current * 100.0
        else:
            dist_stop = (stop - current) / current * 100.0

    hit_target = target is not None and ((current >= target) if longish else (current <= target))
    hit_stop = stop is not None and ((current <= stop) if longish else (current >= stop))

    if hit_target:
        status = "target_hit"
        grade = "🟢 WIN"
    elif hit_stop:
        status = "stop_hit"
        grade = "🔴 STOP"
    elif move_pct >= 2:
        status = "working"
        grade = "🟢 WORKING"
    elif move_pct <= -2:
        status = "against"
        grade = "🟠 AGAINST"
    else:
        status = "flat"
        grade = "🟡 FLAT"

    if progress is not None and progress >= 70 and not hit_target:
        notes.append("near target")
    if dist_stop is not None and dist_stop < 1.5 and not hit_stop:
        notes.append("near stop")
    return status, grade, notes, round(move_pct, 2), round(progress, 1) if progress is not None else None, round(dist_stop, 2) if dist_stop is not None else None


def contract_label(sig: dict[str, Any]) -> str:
    c = sig.get("contract") or {}
    parts = [str(c.get("symbol") or "").strip()]
    desc = " ".join(str(x) for x in [c.get("type"), c.get("strike"), c.get("expiration")] if x is not None)
    if desc:
        parts.append(desc)
    return " · ".join(x for x in parts if x) or "n/a"


def build_rows(limit: int) -> list[OutcomeRow]:
    discovered = discover_signals(limit)
    symbols = [str((sig.get("symbol") or "")).upper() for sig, _, _ in discovered if sig.get("symbol")]
    prices = fetch_prices(symbols)
    now = datetime.now(UTC)
    rows: list[OutcomeRow] = []
    for sig, generated_at, source in discovered:
        setup = sig.get("setup") or {}
        symbol = str(sig.get("symbol") or "").upper()
        gen_dt = parse_dt(generated_at)
        age_days = round((now - gen_dt).total_seconds() / 86400, 2) if gen_dt else None
        direction = str(setup.get("direction") or sig.get("direction") or "long")
        entry = as_float(setup.get("entry") or setup.get("close"))
        target = as_float(setup.get("target"))
        stop = as_float(setup.get("stop"))
        current = prices.get(symbol)
        status, grade, notes, move_pct, progress, dist_stop = classify(direction, entry, target, stop, current)
        rows.append(
            OutcomeRow(
                key=signal_identity(sig, generated_at, source),
                symbol=symbol,
                generated_at=generated_at,
                age_days=age_days,
                setup=str(setup.get("setup") or sig.get("setup") or "signal"),
                direction=direction,
                entry=entry,
                target=target,
                stop=stop,
                current=current,
                move_pct=move_pct,
                progress_to_target_pct=progress,
                distance_to_stop_pct=dist_stop,
                status=status,
                risk_grade=grade,
                score=as_float(sig.get("total_score")),
                contract=contract_label(sig),
                source_file=str(source.relative_to(ROOT)),
                notes=notes,
            )
        )
    return rows


def format_markdown(payload: dict[str, Any]) -> str:
    rows = payload.get("outcomes") or []
    lines = [
        f"# Signal Outcome Tracker — {payload.get('generated_at')}",
        "",
        "Tracks saved desk option signals against current underlying prices. This is zero-LLM and uses delayed/proxy yfinance data until OPRA history is wired.",
        "",
    ]
    summary = payload.get("summary") or {}
    lines += [
        "## Summary",
        f"- Signals tracked: {summary.get('tracked', 0)}",
        f"- Target hits: {summary.get('target_hit', 0)}",
        f"- Stop hits: {summary.get('stop_hit', 0)}",
        f"- Working: {summary.get('working', 0)}",
        f"- Against: {summary.get('against', 0)}",
        "",
        "## Rows",
        "| Symbol | Grade | Move | Progress | Entry | Current | Target | Stop | Setup | Source |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    for row in rows[:30]:
        lines.append(
            "| {symbol} | {risk_grade} | {move} | {progress} | {entry} | {current} | {target} | {stop} | {setup} | `{source}` |".format(
                symbol=row.get("symbol", ""),
                risk_grade=row.get("risk_grade", ""),
                move="—" if row.get("move_pct") is None else f"{row['move_pct']:.2f}%",
                progress="—" if row.get("progress_to_target_pct") is None else f"{row['progress_to_target_pct']:.1f}%",
                entry=row.get("entry") or "—",
                current=row.get("current") or "—",
                target=row.get("target") or "—",
                stop=row.get("stop") or "—",
                setup=str(row.get("setup") or "").replace("|", "/"),
                source=row.get("source_file", ""),
            )
        )
    return "\n".join(lines) + "\n"


def summarize(rows: list[OutcomeRow]) -> dict[str, Any]:
    counts: dict[str, int] = {"tracked": len(rows), "target_hit": 0, "stop_hit": 0, "working": 0, "against": 0, "flat": 0, "untracked": 0}
    for row in rows:
        counts[row.status] = counts.get(row.status, 0) + 1
    avg_move = [r.move_pct for r in rows if r.move_pct is not None]
    counts["avg_move_pct"] = round(sum(avg_move) / len(avg_move), 2) if avg_move else None
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--markdown-out", type=Path, default=DEFAULT_MD)
    args = parser.parse_args()

    RUNS.mkdir(parents=True, exist_ok=True)
    rows = build_rows(args.limit)
    payload = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "data_source": "yfinance underlying close/current proxy; no LLM calls",
        "summary": summarize(rows),
        "outcomes": [asdict(r) for r in rows],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    args.markdown_out.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_out.write_text(format_markdown(payload), encoding="utf-8")
    print(json.dumps(payload, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
