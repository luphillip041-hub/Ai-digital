"""Deterministic scan scoring — shared by the live scanner and the backtester.

One implementation on purpose: what the backtest replays is bar-for-bar
identical to what the live scanner scores today.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from desk_agents.marketdata import _atr_pct, _rsi, _sma

DISQUALIFYING_FLAGS = {"atr_too_wide", "low_relative_volume"}


@dataclass(frozen=True)
class ScoreCard:
    score: float
    bias: str
    eligible: bool
    close: float | None = None
    rsi14: float | None = None
    volume_ratio: float | None = None
    atr_pct: float | None = None
    ma20: float | None = None
    ma50: float | None = None
    ret5_pct: float | None = None
    ret20_pct: float | None = None
    why: list = field(default_factory=list)
    risk_flags: list = field(default_factory=list)


def _pct(curr: float, prev: float) -> float | None:
    if prev == 0:
        return None
    return (curr / prev - 1) * 100


def score_window(
    closes: list,
    highs: list,
    lows: list,
    volumes: list,
    *,
    min_score: float = 60,
) -> ScoreCard:
    """Score the most recent bar of the given window (>= 55 bars required)."""
    if len(closes) < 55:
        return ScoreCard(score=0, bias="neutral", eligible=False,
                         risk_flags=["insufficient_price_history"])

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
    why: list = []
    flags: list = []

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
    eligible = score >= min_score and not DISQUALIFYING_FLAGS.intersection(flags)

    def clean(value, ndigits=2):
        return round(value, ndigits) if value is not None and math.isfinite(value) else None

    return ScoreCard(
        score=score, bias=bias, eligible=eligible,
        close=clean(close, 4), rsi14=clean(rsi14), volume_ratio=clean(volume_ratio),
        atr_pct=clean(atr), ma20=clean(ma20, 4), ma50=clean(ma50, 4),
        ret5_pct=clean(ret5), ret20_pct=clean(ret20),
        why=why, risk_flags=flags,
    )
