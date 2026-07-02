#!/usr/bin/env python3
"""Zero-LLM market scanner for Flip's trading desk.

Run this across a watchlist before spending tokens on TradingAgents. It uses
Yahoo Finance OHLCV only, scores candidates deterministically, and writes a
compact JSON shortlist that `run_desk_analysis.py` can consume manually.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


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


def _load_yfinance():
    try:
        import yfinance as yf  # type: ignore
    except Exception as exc:  # pragma: no cover - dependency/environment specific
        raise SystemExit(
            "yfinance is required. Run `bash trading-desk/scripts/setup.sh` first. "
            f"Original error: {exc!r}"
        ) from exc
    return yf


def _sma(values: list[float], n: int) -> float | None:
    if len(values) < n:
        return None
    return sum(values[-n:]) / n


def _rsi(values: list[float], period: int = 14) -> float | None:
    if len(values) <= period:
        return None
    gains: list[float] = []
    losses: list[float] = []
    for prev, curr in zip(values[-period - 1 : -1], values[-period:], strict=False):
        diff = curr - prev
        gains.append(max(diff, 0.0))
        losses.append(max(-diff, 0.0))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _atr_pct(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> float | None:
    if len(closes) <= period:
        return None
    true_ranges: list[float] = []
    for i in range(len(closes) - period, len(closes)):
        prev_close = closes[i - 1]
        true_ranges.append(max(highs[i] - lows[i], abs(highs[i] - prev_close), abs(lows[i] - prev_close)))
    if closes[-1] <= 0:
        return None
    return (sum(true_ranges) / len(true_ranges)) / closes[-1] * 100


def _pct(curr: float, prev: float) -> float | None:
    if prev == 0:
        return None
    return (curr / prev - 1) * 100


def scan_symbol(symbol: str, *, lookback: str, min_score: float) -> ScanResult:
    yf = _load_yfinance()
    hist = yf.Ticker(symbol).history(period=lookback, interval="1d", auto_adjust=True)
    if hist is None or hist.empty or len(hist) < 55:
        return ScanResult(
            symbol=symbol.upper(),
            score=0,
            bias="neutral",
            eligible=False,
            risk_flags=["insufficient_price_history"],
        )

    closes = [float(x) for x in hist["Close"].tolist()]
    highs = [float(x) for x in hist["High"].tolist()]
    lows = [float(x) for x in hist["Low"].tolist()]
    volumes = [float(x) for x in hist["Volume"].tolist()]
    close = closes[-1]
    ma20 = _sma(closes, 20)
    ma50 = _sma(closes, 50)
    rsi14 = _rsi(closes, 14)
    atr = _atr_pct(highs, lows, closes, 14)
    avg_vol20 = sum(volumes[-21:-1]) / 20 if len(volumes) >= 21 else 0.0
    volume_ratio = volumes[-1] / avg_vol20 if avg_vol20 else None
    ret5 = _pct(closes[-1], closes[-6]) if len(closes) >= 6 else None
    ret20 = _pct(closes[-1], closes[-21]) if len(closes) >= 21 else None

    score = 0.0
    why: list[str] = []
    flags: list[str] = []

    if ma20 and close > ma20:
        score += 15
        why.append("close>20dma")
    if ma50 and close > ma50:
        score += 15
        why.append("close>50dma")
    if ma20 and ma50 and ma20 > ma50:
        score += 10
        why.append("20dma>50dma")
    if rsi14 is not None:
        if 45 <= rsi14 <= 68:
            score += 15
            why.append("rsi_constructive")
        elif rsi14 > 78:
            score -= 10
            flags.append("rsi_overheated")
        elif rsi14 < 35:
            flags.append("rsi_weak_or_oversold")
    if volume_ratio is not None:
        if volume_ratio >= 1.5:
            score += 15
            why.append("volume_expansion")
        elif volume_ratio < 0.65:
            score -= 5
            flags.append("low_relative_volume")
    if atr is not None:
        if 1.0 <= atr <= 5.5:
            score += 10
            why.append("tradable_atr")
        elif atr > 8:
            score -= 15
            flags.append("atr_too_wide")
    if ret5 is not None and ret20 is not None:
        if ret5 > 0 and ret20 > 0:
            score += 15
            why.append("positive_5d_20d_momentum")
        elif ret5 < -4 and ret20 < 0:
            score -= 10
            flags.append("downtrend_pressure")

    score = round(max(0, min(100, score)), 2)
    bias = "long" if score >= min_score and close > (ma20 or close) else "neutral"
    eligible = score >= min_score and not {"atr_too_wide", "low_relative_volume"}.intersection(flags)

    def clean(value: float | None, ndigits: int = 2) -> float | None:
        return round(value, ndigits) if value is not None and math.isfinite(value) else None

    return ScanResult(
        symbol=symbol.upper(),
        score=score,
        bias=bias,
        eligible=eligible,
        close=clean(close, 4),
        rsi14=clean(rsi14),
        volume_ratio=clean(volume_ratio),
        atr_pct=clean(atr),
        ma20=clean(ma20, 4),
        ma50=clean(ma50, 4),
        five_day_return_pct=clean(ret5),
        twenty_day_return_pct=clean(ret20),
        why=why,
        risk_flags=flags,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Zero-LLM watchlist scanner")
    parser.add_argument("--symbols", default="SPY,QQQ,NVDA,TSLA,SMH,AAPL,MSFT,AMZN,GOOGL,META")
    parser.add_argument("--lookback", default="6mo")
    parser.add_argument("--min-score", type=float, default=60)
    parser.add_argument("--max-finalists", type=int, default=5)
    parser.add_argument("--out", default=str(ROOT / "runs" / "scanner_latest.json"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    results = [scan_symbol(s, lookback=args.lookback, min_score=args.min_score) for s in symbols]
    results.sort(key=lambda r: r.score, reverse=True)
    finalists = [r for r in results if r.eligible][: args.max_finalists]
    payload = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "lookback": args.lookback,
        "min_score": args.min_score,
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
