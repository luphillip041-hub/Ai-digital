"""Deterministic data layer — gathered once, before any sub-agent runs.

No LLM ever triggers a tool loop here: the orchestrator fetches
everything up front and injects compact text briefs into agent prompts.
That makes per-run LLM call counts exact and keeps prompts small.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass(frozen=True)
class MarketBrief:
    symbol: str
    ok: bool
    close: float | None = None
    ma20: float | None = None
    ma50: float | None = None
    rsi14: float | None = None
    atr_pct: float | None = None
    volume_ratio: float | None = None
    ret5_pct: float | None = None
    ret20_pct: float | None = None
    notes: list[str] = field(default_factory=list)

    def to_prompt(self) -> str:
        if not self.ok:
            return f"{self.symbol}: no usable price history ({'; '.join(self.notes) or 'unknown reason'})."
        def fmt(value: float | None, suffix: str = "") -> str:
            return f"{value:.2f}{suffix}" if value is not None else "n/a"
        return (
            f"{self.symbol} daily OHLCV snapshot:\n"
            f"- close: {fmt(self.close)}\n"
            f"- 20-day avg: {fmt(self.ma20)} | 50-day avg: {fmt(self.ma50)}\n"
            f"- RSI(14): {fmt(self.rsi14)}\n"
            f"- ATR(14): {fmt(self.atr_pct, '%')} of price\n"
            f"- volume vs 20-day avg: {fmt(self.volume_ratio, 'x')}\n"
            f"- 5-day return: {fmt(self.ret5_pct, '%')} | 20-day return: {fmt(self.ret20_pct, '%')}"
        )


def _sma(values: list[float], n: int) -> float | None:
    if len(values) < n:
        return None
    return sum(values[-n:]) / n


def _rsi(values: list[float], period: int = 14) -> float | None:
    if len(values) <= period:
        return None
    gains, losses = [], []
    for prev, curr in zip(values[-period - 1 : -1], values[-period:], strict=False):
        diff = curr - prev
        gains.append(max(diff, 0.0))
        losses.append(max(-diff, 0.0))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    return 100 - (100 / (1 + avg_gain / avg_loss))


def _atr_pct(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> float | None:
    if len(closes) <= period:
        return None
    true_ranges = []
    for i in range(len(closes) - period, len(closes)):
        prev_close = closes[i - 1]
        true_ranges.append(max(highs[i] - lows[i], abs(highs[i] - prev_close), abs(lows[i] - prev_close)))
    if closes[-1] <= 0:
        return None
    return (sum(true_ranges) / len(true_ranges)) / closes[-1] * 100


def fetch_market_brief(symbol: str, lookback: str = "6mo") -> MarketBrief:
    try:
        import yfinance as yf
    except Exception as exc:
        return MarketBrief(symbol=symbol.upper(), ok=False, notes=[f"yfinance unavailable: {exc!r}"])
    try:
        hist = yf.Ticker(symbol).history(period=lookback, interval="1d", auto_adjust=True)
    except Exception as exc:
        return MarketBrief(symbol=symbol.upper(), ok=False, notes=[f"price fetch failed: {exc!r}"])
    if hist is None or hist.empty or len(hist) < 55:
        return MarketBrief(symbol=symbol.upper(), ok=False, notes=["insufficient price history"])

    closes = [float(x) for x in hist["Close"].tolist()]
    highs = [float(x) for x in hist["High"].tolist()]
    lows = [float(x) for x in hist["Low"].tolist()]
    volumes = [float(x) for x in hist["Volume"].tolist()]

    avg_vol20 = sum(volumes[-21:-1]) / 20 if len(volumes) >= 21 else 0.0

    def clean(value: float | None) -> float | None:
        return value if value is not None and math.isfinite(value) else None

    return MarketBrief(
        symbol=symbol.upper(),
        ok=True,
        close=clean(closes[-1]),
        ma20=clean(_sma(closes, 20)),
        ma50=clean(_sma(closes, 50)),
        rsi14=clean(_rsi(closes)),
        atr_pct=clean(_atr_pct(highs, lows, closes)),
        volume_ratio=clean(volumes[-1] / avg_vol20 if avg_vol20 else None),
        ret5_pct=clean((closes[-1] / closes[-6] - 1) * 100 if len(closes) >= 6 and closes[-6] else None),
        ret20_pct=clean((closes[-1] / closes[-21] - 1) * 100 if len(closes) >= 21 and closes[-21] else None),
    )


def fetch_headlines(symbol: str, limit: int = 5) -> list[str]:
    """Best-effort recent headlines; empty list is a valid answer."""
    try:
        import yfinance as yf

        raw = yf.Ticker(symbol).news or []
    except Exception:
        return []
    lines: list[str] = []
    for item in raw[: max(limit, 0)]:
        content = item.get("content") or item
        title = (content.get("title") or "").strip()
        publisher = ""
        provider = content.get("provider") or {}
        if isinstance(provider, dict):
            publisher = provider.get("displayName") or ""
        publisher = publisher or item.get("publisher") or ""
        if title:
            lines.append(f"- {title}" + (f" ({publisher})" if publisher else ""))
    return lines


def fetch_fundamentals(symbol: str) -> dict[str, object]:
    """Small, guarded subset of fundamentals; missing keys simply drop out."""
    try:
        import yfinance as yf

        info = yf.Ticker(symbol).info or {}
    except Exception:
        return {}
    keys = (
        "marketCap", "trailingPE", "forwardPE", "priceToSalesTrailing12Months",
        "profitMargins", "revenueGrowth", "earningsGrowth", "debtToEquity",
        "freeCashflow", "totalCash",
    )
    return {k: info[k] for k in keys if info.get(k) is not None}
