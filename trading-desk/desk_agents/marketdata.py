"""Deterministic data layer — gathered once, before any sub-agent runs.

No LLM ever triggers a tool loop here: the orchestrator fetches
everything up front and injects compact text briefs into agent prompts.
That makes per-run LLM call counts exact and keeps prompts small.

Two data sources, selected by FLIP_DESK_DATA_SOURCE (auto|alpaca|yahoo):
- alpaca: Alpaca Market Data REST API (stdlib urllib, no SDK). Uses the
  same ALPACA_API_KEY / ALPACA_SECRET_KEY / ALPACA_DATA_FEED env vars as
  the repo's Alpaca bot. Stocks/ETFs only.
- yahoo: yfinance fallback; also covers symbols Alpaca can't (BTC-USD).
- auto (default): alpaca when keys are set and the symbol qualifies,
  else yahoo.
"""

from __future__ import annotations

import json
import math
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

ALPACA_DATA_URL = os.getenv("ALPACA_DATA_URL", "https://data.alpaca.markets")
LOOKBACK_DAYS = {"1mo": 31, "3mo": 92, "6mo": 184, "1y": 366, "2y": 731}


@dataclass(frozen=True)
class OHLCV:
    symbol: str
    source: str
    closes: list[float]
    highs: list[float]
    lows: list[float]
    volumes: list[float]
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and len(self.closes) >= 55


@dataclass(frozen=True)
class MarketBrief:
    symbol: str
    ok: bool
    source: str = "none"
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
            f"{self.symbol} daily OHLCV snapshot (source: {self.source}):\n"
            f"- close: {fmt(self.close)}\n"
            f"- 20-day avg: {fmt(self.ma20)} | 50-day avg: {fmt(self.ma50)}\n"
            f"- RSI(14): {fmt(self.rsi14)}\n"
            f"- ATR(14): {fmt(self.atr_pct, '%')} of price\n"
            f"- volume vs 20-day avg: {fmt(self.volume_ratio, 'x')}\n"
            f"- 5-day return: {fmt(self.ret5_pct, '%')} | 20-day return: {fmt(self.ret20_pct, '%')}"
        )


def _alpaca_keys() -> tuple[str, str]:
    return os.getenv("ALPACA_API_KEY", ""), os.getenv("ALPACA_SECRET_KEY", "")


def _alpaca_eligible(symbol: str) -> bool:
    """Alpaca stock bars cover equities/ETFs; route crypto-style symbols to yahoo."""
    return "-" not in symbol and "=" not in symbol


def resolve_source(symbol: str, requested: str | None = None) -> str:
    requested = (requested or os.getenv("FLIP_DESK_DATA_SOURCE", "auto")).lower()
    if requested == "alpaca":
        return "alpaca"
    if requested == "yahoo":
        return "yahoo"
    key, secret = _alpaca_keys()
    if key and secret and _alpaca_eligible(symbol):
        return "alpaca"
    return "yahoo"


def _alpaca_get(path: str, params: dict[str, str]) -> dict:
    key, secret = _alpaca_keys()
    if not key or not secret:
        raise RuntimeError("ALPACA_API_KEY / ALPACA_SECRET_KEY not set")
    url = f"{ALPACA_DATA_URL}{path}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(
        url,
        headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def _fetch_alpaca_ohlcv(symbol: str, lookback: str) -> OHLCV:
    days = LOOKBACK_DAYS.get(lookback, 184)
    start = (datetime.now(UTC) - timedelta(days=days)).date().isoformat()
    bars: list[dict] = []
    params = {
        "timeframe": "1Day",
        "start": start,
        "limit": "1000",
        "adjustment": "split",
        "feed": os.getenv("ALPACA_DATA_FEED", "iex"),
    }
    try:
        while True:
            payload = _alpaca_get(f"/v2/stocks/{symbol.upper()}/bars", params)
            bars.extend(payload.get("bars") or [])
            token = payload.get("next_page_token")
            if not token:
                break
            params["page_token"] = token
    except Exception as exc:
        return OHLCV(symbol.upper(), "alpaca", [], [], [], [], error=f"alpaca fetch failed: {exc!r}")
    if not bars:
        return OHLCV(symbol.upper(), "alpaca", [], [], [], [], error="alpaca returned no bars")
    return OHLCV(
        symbol=symbol.upper(),
        source="alpaca",
        closes=[float(b["c"]) for b in bars],
        highs=[float(b["h"]) for b in bars],
        lows=[float(b["l"]) for b in bars],
        volumes=[float(b["v"]) for b in bars],
    )


def _fetch_yahoo_ohlcv(symbol: str, lookback: str) -> OHLCV:
    try:
        import yfinance as yf

        hist = yf.Ticker(symbol).history(period=lookback, interval="1d", auto_adjust=True)
    except Exception as exc:
        return OHLCV(symbol.upper(), "yahoo", [], [], [], [], error=f"yahoo fetch failed: {exc!r}")
    if hist is None or hist.empty:
        return OHLCV(symbol.upper(), "yahoo", [], [], [], [], error="yahoo returned no bars")
    return OHLCV(
        symbol=symbol.upper(),
        source="yahoo",
        closes=[float(x) for x in hist["Close"].tolist()],
        highs=[float(x) for x in hist["High"].tolist()],
        lows=[float(x) for x in hist["Low"].tolist()],
        volumes=[float(x) for x in hist["Volume"].tolist()],
    )


def fetch_ohlcv(symbol: str, lookback: str = "6mo", source: str | None = None) -> OHLCV:
    resolved = resolve_source(symbol, source)
    if resolved == "alpaca":
        data = _fetch_alpaca_ohlcv(symbol, lookback)
        # In auto mode a dead Alpaca response still gets a second chance on yahoo.
        if not data.ok and (source or os.getenv("FLIP_DESK_DATA_SOURCE", "auto")).lower() == "auto":
            fallback = _fetch_yahoo_ohlcv(symbol, lookback)
            return fallback if fallback.ok else data
        return data
    return _fetch_yahoo_ohlcv(symbol, lookback)


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


def fetch_market_brief(symbol: str, lookback: str = "6mo", source: str | None = None) -> MarketBrief:
    data = fetch_ohlcv(symbol, lookback=lookback, source=source)
    if not data.ok:
        notes = [data.error] if data.error else ["insufficient price history"]
        return MarketBrief(symbol=data.symbol, ok=False, source=data.source, notes=notes)

    closes, highs, lows, volumes = data.closes, data.highs, data.lows, data.volumes
    avg_vol20 = sum(volumes[-21:-1]) / 20 if len(volumes) >= 21 else 0.0

    def clean(value: float | None) -> float | None:
        return value if value is not None and math.isfinite(value) else None

    return MarketBrief(
        symbol=data.symbol,
        ok=True,
        source=data.source,
        close=clean(closes[-1]),
        ma20=clean(_sma(closes, 20)),
        ma50=clean(_sma(closes, 50)),
        rsi14=clean(_rsi(closes)),
        atr_pct=clean(_atr_pct(highs, lows, closes)),
        volume_ratio=clean(volumes[-1] / avg_vol20 if avg_vol20 else None),
        ret5_pct=clean((closes[-1] / closes[-6] - 1) * 100 if len(closes) >= 6 and closes[-6] else None),
        ret20_pct=clean((closes[-1] / closes[-21] - 1) * 100 if len(closes) >= 21 and closes[-21] else None),
    )


def _alpaca_headlines(symbol: str, limit: int) -> list[str]:
    payload = _alpaca_get("/v1beta1/news", {"symbols": symbol.upper(), "limit": str(max(limit, 1))})
    lines = []
    for item in payload.get("news") or []:
        headline = (item.get("headline") or "").strip()
        source_name = item.get("source") or ""
        if headline:
            lines.append(f"- {headline}" + (f" ({source_name})" if source_name else ""))
    return lines[:limit]


def _yahoo_headlines(symbol: str, limit: int) -> list[str]:
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


def fetch_headlines(symbol: str, limit: int = 5, source: str | None = None) -> list[str]:
    """Best-effort recent headlines; empty list is a valid answer."""
    if resolve_source(symbol, source) == "alpaca":
        try:
            lines = _alpaca_headlines(symbol, limit)
            if lines:
                return lines
        except Exception:
            pass
    return _yahoo_headlines(symbol, limit)


def fetch_fundamentals(symbol: str) -> dict[str, object]:
    """Small, guarded subset of fundamentals; missing keys simply drop out.

    Always yahoo — Alpaca's data API does not expose company fundamentals.
    """
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
