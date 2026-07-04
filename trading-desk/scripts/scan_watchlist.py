#!/usr/bin/env python3
"""Zero-LLM market scanner for Flip's trading desk.

Run this across a watchlist before spending tokens on the multi-agent desk.
It pulls daily OHLCV from the shared data layer (Alpaca when keys are set,
Yahoo otherwise), scores candidates deterministically, and writes a compact
JSON shortlist that `run_desk_analysis.py` can consume manually.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import timezone, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from desk_agents.marketdata import fetch_ohlcv  # noqa: E402
from desk_agents.scoring import score_window  # noqa: E402

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    load_dotenv(ROOT / ".env.local")
except Exception:  # pragma: no cover - optional during static checks
    pass


@dataclass(frozen=True)
class ScanResult:
    symbol: str
    score: float
    bias: str
    eligible: bool
    close: float | None = None
    rsi14: float | None = None
    volume_ratio: float | None = None
    atr_pct: float | None = None
    ma20: float | None = None
    ma50: float | None = None
    five_day_return_pct: float | None = None
    twenty_day_return_pct: float | None = None
    why: list[str] = field(default_factory=list)
    risk_flags: list[str] = field(default_factory=list)
    source: str = "none"


def scan_symbol(symbol: str, *, lookback: str, min_score: float, source: str | None = None) -> ScanResult:
    data = fetch_ohlcv(symbol, lookback=lookback, source=source)
    if not data.ok:
        return ScanResult(
            symbol=symbol.upper(),
            score=0,
            bias="neutral",
            eligible=False,
            risk_flags=[data.error or "insufficient_price_history"],
            source=data.source,
        )
    card = score_window(data.closes, data.highs, data.lows, data.volumes, min_score=min_score)
    return ScanResult(
        symbol=symbol.upper(),
        score=card.score,
        bias=card.bias,
        eligible=card.eligible,
        close=card.close,
        rsi14=card.rsi14,
        volume_ratio=card.volume_ratio,
        atr_pct=card.atr_pct,
        ma20=card.ma20,
        ma50=card.ma50,
        five_day_return_pct=card.ret5_pct,
        twenty_day_return_pct=card.ret20_pct,
        why=card.why,
        risk_flags=card.risk_flags,
        source=data.source,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Zero-LLM watchlist scanner")
    parser.add_argument("--symbols", default="SPY,QQQ,NVDA,TSLA,SMH,AAPL,MSFT,AMZN,GOOGL,META")
    parser.add_argument("--lookback", default="6mo")
    parser.add_argument("--min-score", type=float, default=60)
    parser.add_argument("--max-finalists", type=int, default=5)
    parser.add_argument("--data-source", choices=("auto", "alpaca", "yahoo"), default=None,
                        help="Market data source; default auto (Alpaca when keys are set)")
    parser.add_argument("--out", default=str(ROOT / "runs" / "scanner_latest.json"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    results = [scan_symbol(s, lookback=args.lookback, min_score=args.min_score, source=args.data_source) for s in symbols]
    results.sort(key=lambda r: r.score, reverse=True)
    finalists = [r for r in results if r.eligible][: args.max_finalists]
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "lookback": args.lookback,
        "min_score": args.min_score,
        "data_sources": sorted({r.source for r in results}),
        "max_finalists": args.max_finalists,
        "finalists": [asdict(r) for r in finalists],
        "ranked": [asdict(r) for r in results],
        "next_step": "Run run_desk_analysis.py on finalists only; scanner itself used zero LLM calls.",
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
