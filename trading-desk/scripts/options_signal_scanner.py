#!/usr/bin/env python3
"""Options signal scanner for Flip's trading desk.

Zero-LLM scanner that combines:
- underlying technical setup detection
- chart levels / ATR risk bands
- option-chain liquidity filters
- IV / expected-move context
- basic Black-Scholes delta approximation
- management plan output

It produces JSON plus a Discord-ready markdown signal card inspired by the
example image: setup, symbol, entry/target/stop, suggested contract, bid/ask,
volume, OI, risk, and management rules.

Data source: yfinance delayed/free data. Treat output as research/paper signal,
not live execution advice. Upgrade path is Tradier/Alpaca/OPRA snapshots.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from statistics import NormalDist
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
NORM = NormalDist()


@dataclass(frozen=True)
class UnderlyingSetup:
    symbol: str
    setup: str
    direction: str
    score: float
    close: float
    entry: float
    target: float
    stop: float
    potential_profit: float
    reward_risk: float | None
    rsi14: float | None
    atr: float | None
    atr_pct: float | None
    sma20: float | None
    sma50: float | None
    volume_ratio: float | None
    support: float | None
    resistance: float | None
    five_day_return_pct: float | None
    twenty_day_return_pct: float | None
    why: list[str] = field(default_factory=list)
    risk_flags: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class OptionContract:
    type: str
    expiration: str
    dte: int
    strike: float
    bid: float
    ask: float
    mid: float
    last: float | None
    volume: int
    open_interest: int
    implied_volatility: float | None
    spread_pct: float | None
    approx_delta: float | None
    expected_move: float | None
    breakeven: float
    liquidity_score: float
    risk_flags: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Signal:
    symbol: str
    rank: int
    total_score: float
    setup: UnderlyingSetup
    contract: OptionContract | None
    management: dict[str, Any]
    signal_text: str


def _load_yfinance():
    try:
        import yfinance as yf  # type: ignore
    except Exception as exc:
        raise SystemExit("yfinance is required. Run `bash scripts/setup.sh` first.") from exc
    return yf


def _clean_float(value: Any, ndigits: int = 4) -> float | None:
    try:
        f = float(value)
        if not math.isfinite(f):
            return None
        return round(f, ndigits)
    except Exception:
        return None


def _clean_int(value: Any) -> int:
    try:
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return 0
        return int(value)
    except Exception:
        return 0


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
    return 100 - (100 / (1 + avg_gain / avg_loss))


def _atr(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> float | None:
    if len(closes) <= period:
        return None
    trs: list[float] = []
    for i in range(len(closes) - period, len(closes)):
        prev_close = closes[i - 1]
        trs.append(max(highs[i] - lows[i], abs(highs[i] - prev_close), abs(lows[i] - prev_close)))
    return sum(trs) / len(trs)


def _pct(curr: float, prev: float) -> float | None:
    if prev == 0:
        return None
    return (curr / prev - 1) * 100


def _bs_delta(spot: float, strike: float, iv: float | None, dte: int, contract_type: str) -> float | None:
    if not iv or iv <= 0 or spot <= 0 or strike <= 0 or dte <= 0:
        return None
    t = max(dte / 365.0, 1 / 365)
    r = 0.04
    try:
        d1 = (math.log(spot / strike) + (r + 0.5 * iv * iv) * t) / (iv * math.sqrt(t))
        call_delta = NORM.cdf(d1)
        return call_delta if contract_type == "CALL" else call_delta - 1
    except Exception:
        return None


def _support_resistance(closes: list[float], highs: list[float], lows: list[float], window: int = 20) -> tuple[float | None, float | None]:
    if len(closes) < window:
        return None, None
    support = min(lows[-window:])
    resistance = max(highs[-window:])
    return support, resistance


def analyze_underlying(symbol: str, *, lookback: str, min_underlying_score: float) -> UnderlyingSetup:
    yf = _load_yfinance()
    ticker = yf.Ticker(symbol)
    hist = ticker.history(period=lookback, interval="1d", auto_adjust=True)
    symbol = symbol.upper()
    if hist is None or hist.empty or len(hist) < 55:
        return UnderlyingSetup(
            symbol=symbol,
            setup="No Signal",
            direction="neutral",
            score=0,
            close=0,
            entry=0,
            target=0,
            stop=0,
            potential_profit=0,
            reward_risk=None,
            rsi14=None,
            atr=None,
            atr_pct=None,
            sma20=None,
            sma50=None,
            volume_ratio=None,
            support=None,
            resistance=None,
            five_day_return_pct=None,
            twenty_day_return_pct=None,
            risk_flags=["insufficient_price_history"],
        )

    closes = [float(x) for x in hist["Close"].tolist()]
    highs = [float(x) for x in hist["High"].tolist()]
    lows = [float(x) for x in hist["Low"].tolist()]
    opens = [float(x) for x in hist["Open"].tolist()]
    volumes = [float(x) for x in hist["Volume"].tolist()]

    close = closes[-1]
    open_ = opens[-1]
    prev_close = closes[-2]
    prev_open = opens[-2]
    sma20 = _sma(closes, 20)
    sma50 = _sma(closes, 50)
    rsi14 = _rsi(closes, 14)
    atr = _atr(highs, lows, closes, 14)
    support, resistance = _support_resistance(closes, highs, lows, 20)
    avg_vol20 = sum(volumes[-21:-1]) / 20 if len(volumes) >= 21 else 0
    volume_ratio = volumes[-1] / avg_vol20 if avg_vol20 else None
    ret5 = _pct(closes[-1], closes[-6]) if len(closes) >= 6 else None
    ret20 = _pct(closes[-1], closes[-21]) if len(closes) >= 21 else None

    why: list[str] = []
    flags: list[str] = []
    score = 0.0
    setup = "No Signal"
    direction = "neutral"

    bullish_engulf = close > open_ and prev_close < prev_open and close > prev_open and open_ < prev_close
    hammerish = atr is not None and close > open_ and (min(open_, close) - lows[-1]) > 0.45 * atr
    reclaimed_20 = bool(sma20 and prev_close < sma20 <= close)
    trend_pullback = bool(sma20 and sma50 and close > sma50 and abs(close - sma20) / close < 0.025 and 40 <= (rsi14 or 50) <= 62)
    breakout = bool(resistance and close >= resistance * 0.995 and volume_ratio and volume_ratio >= 1.1)

    bearish_reversal = close < open_ and prev_close > prev_open and close < prev_open and open_ > prev_close
    lost_20 = bool(sma20 and prev_close > sma20 >= close)
    bearish_trend = bool(sma20 and sma50 and close < sma20 < sma50)

    if bullish_engulf or hammerish or reclaimed_20:
        score += 30
        setup = "Bullish Reversal"
        direction = "long"
        if bullish_engulf:
            why.append("bullish_engulfing_candle")
        if hammerish:
            why.append("long_lower_wick_reversal")
        if reclaimed_20:
            why.append("reclaimed_20dma")
    if trend_pullback:
        score += 24
        setup = "Trend Pullback"
        direction = "long"
        why.append("constructive_pullback_to_20dma")
    if breakout:
        score += 24
        setup = "Breakout Continuation"
        direction = "long"
        why.append("near_20d_resistance_break_with_volume")

    if bearish_reversal or lost_20 or bearish_trend:
        bear_score = 0.0
        bear_why: list[str] = []
        if bearish_reversal:
            bear_score += 26
            bear_why.append("bearish_engulfing_candle")
        if lost_20:
            bear_score += 20
            bear_why.append("lost_20dma")
        if bearish_trend:
            bear_score += 22
            bear_why.append("bearish_ma_stack")
        if bear_score > score:
            score = bear_score
            setup = "Bearish Reversal" if bearish_reversal or lost_20 else "Bearish Continuation"
            direction = "short"
            why = bear_why

    if sma20 and sma50:
        if direction == "long" and close > sma20 > sma50:
            score += 14
            why.append("bullish_ma_stack")
        elif direction == "short" and close < sma20 < sma50:
            score += 14
            why.append("bearish_ma_stack_confirmed")
    if rsi14 is not None:
        if direction == "long" and 38 <= rsi14 <= 68:
            score += 12
            why.append("rsi_supportive")
        elif direction == "short" and 32 <= rsi14 <= 62:
            score += 12
            why.append("rsi_supportive")
        elif rsi14 > 78:
            flags.append("rsi_overheated")
            score -= 10
        elif rsi14 < 24:
            flags.append("rsi_extremely_oversold")
            score -= 6
    if volume_ratio is not None:
        if volume_ratio >= 1.25:
            score += 10
            why.append("volume_confirmation")
        elif volume_ratio < 0.55:
            flags.append("weak_volume")
            score -= 8
    if atr and close > 0:
        atr_pct = atr / close * 100
        if 1.0 <= atr_pct <= 7.0:
            score += 10
            why.append("optionable_atr_range")
        elif atr_pct > 10:
            flags.append("atr_too_wide")
            score -= 12
    else:
        atr_pct = None

    if not why:
        setup = "No Signal"
        direction = "neutral"

    score = round(max(0, min(100, score)), 2)
    if score < min_underlying_score:
        flags.append("below_underlying_score_threshold")

    risk_unit = atr or max(close * 0.015, 0.01)
    if direction == "short":
        entry = close
        target = close - 1.35 * risk_unit
        stop = close + 0.85 * risk_unit
        potential_profit = max(entry - target, 0)
        risk = max(stop - entry, 0)
    elif direction == "long":
        entry = close
        target = close + 1.35 * risk_unit
        stop = close - 0.85 * risk_unit
        potential_profit = max(target - entry, 0)
        risk = max(entry - stop, 0)
    else:
        entry = close
        target = close
        stop = close
        potential_profit = 0
        risk = 0
    reward_risk = potential_profit / risk if risk else None

    return UnderlyingSetup(
        symbol=symbol,
        setup=setup,
        direction=direction,
        score=score,
        close=round(close, 4),
        entry=round(entry, 4),
        target=round(target, 4),
        stop=round(stop, 4),
        potential_profit=round(potential_profit, 4),
        reward_risk=round(reward_risk, 2) if reward_risk is not None else None,
        rsi14=_clean_float(rsi14, 2),
        atr=_clean_float(atr, 4),
        atr_pct=_clean_float(atr_pct, 2),
        sma20=_clean_float(sma20, 4),
        sma50=_clean_float(sma50, 4),
        volume_ratio=_clean_float(volume_ratio, 2),
        support=_clean_float(support, 4),
        resistance=_clean_float(resistance, 4),
        five_day_return_pct=_clean_float(ret5, 2),
        twenty_day_return_pct=_clean_float(ret20, 2),
        why=why[:8],
        risk_flags=flags,
    )


def _choose_expirations(options: list[str], *, min_dte: int, max_dte: int, max_expirations: int) -> list[str]:
    today = date.today()
    chosen: list[tuple[int, str]] = []
    for exp in options:
        try:
            dte = (date.fromisoformat(exp) - today).days
        except ValueError:
            continue
        if min_dte <= dte <= max_dte:
            chosen.append((dte, exp))
    chosen.sort()
    return [exp for _, exp in chosen[:max_expirations]]


def _liquidity_score(volume: int, oi: int, spread_pct: float | None, mid: float) -> tuple[float, list[str]]:
    flags: list[str] = []
    score = 0.0
    if volume >= 500:
        score += 25
    elif volume >= 100:
        score += 18
    elif volume >= 25:
        score += 10
    else:
        flags.append("low_contract_volume")
    if oi >= 1000:
        score += 25
    elif oi >= 250:
        score += 18
    elif oi >= 50:
        score += 10
    else:
        flags.append("low_open_interest")
    if spread_pct is not None:
        if spread_pct <= 8:
            score += 25
        elif spread_pct <= 15:
            score += 16
        elif spread_pct <= 25:
            score += 8
            flags.append("wide_spread")
        else:
            flags.append("very_wide_spread")
    if 0.15 <= mid <= 8:
        score += 15
    elif mid > 12:
        flags.append("premium_expensive")
    elif mid < 0.05:
        flags.append("lottery_premium")
    return round(min(100, score), 2), flags


def find_contract(setup: UnderlyingSetup, *, min_dte: int, max_dte: int, max_expirations: int) -> OptionContract | None:
    if setup.direction not in {"long", "short"} or setup.close <= 0:
        return None
    yf = _load_yfinance()
    ticker = yf.Ticker(setup.symbol)
    expirations = _choose_expirations(list(ticker.options or []), min_dte=min_dte, max_dte=max_dte, max_expirations=max_expirations)
    if not expirations:
        return None
    contract_type = "CALL" if setup.direction == "long" else "PUT"
    target_strike = setup.target
    candidates: list[tuple[float, OptionContract]] = []
    today = date.today()

    for exp in expirations:
        try:
            chain = ticker.option_chain(exp)
        except Exception:
            continue
        dte = max((date.fromisoformat(exp) - today).days, 0)
        table = chain.calls if contract_type == "CALL" else chain.puts
        if table is None or table.empty:
            continue
        for _, row in table.iterrows():
            strike = _clean_float(row.get("strike"), 4)
            bid = _clean_float(row.get("bid"), 4)
            ask = _clean_float(row.get("ask"), 4)
            last = _clean_float(row.get("lastPrice"), 4)
            if strike is None or bid is None or ask is None:
                continue
            mid = (bid + ask) / 2 if bid > 0 and ask > 0 else (last or 0)
            if mid <= 0:
                continue
            volume = _clean_int(row.get("volume"))
            oi = _clean_int(row.get("openInterest"))
            iv = _clean_float(row.get("impliedVolatility"), 6)
            spread_pct = ((ask - bid) / mid * 100) if mid > 0 and ask >= bid else None
            delta = _bs_delta(setup.close, strike, iv, dte, contract_type)
            expected_move = setup.close * iv * math.sqrt(max(dte, 1) / 365.0) if iv and iv > 0 else None
            breakeven = strike + mid if contract_type == "CALL" else strike - mid
            liq_score, flags = _liquidity_score(volume, oi, spread_pct, mid)

            # Prefer strikes near the technical target but still with usable delta/liquidity.
            target_distance = abs(strike - target_strike) / setup.close * 100
            delta_abs = abs(delta) if delta is not None else 0.35
            delta_penalty = abs(delta_abs - 0.42) * 35
            dte_penalty = abs(dte - 21) * 0.25
            spread_penalty = max((spread_pct or 30) - 12, 0) * 0.45
            rank_score = liq_score + setup.score - target_distance * 2.2 - delta_penalty - dte_penalty - spread_penalty

            if "very_wide_spread" in flags:
                rank_score -= 20
            if volume == 0 and oi < 50:
                rank_score -= 25

            candidates.append(
                (
                    rank_score,
                    OptionContract(
                        type=contract_type,
                        expiration=exp,
                        dte=dte,
                        strike=round(strike, 4),
                        bid=round(bid, 4),
                        ask=round(ask, 4),
                        mid=round(mid, 4),
                        last=last,
                        volume=volume,
                        open_interest=oi,
                        implied_volatility=_clean_float(iv, 4),
                        spread_pct=_clean_float(spread_pct, 2),
                        approx_delta=_clean_float(delta, 3),
                        expected_move=_clean_float(expected_move, 4),
                        breakeven=round(breakeven, 4),
                        liquidity_score=liq_score,
                        risk_flags=flags,
                    ),
                )
            )
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def management_plan(setup: UnderlyingSetup, contract: OptionContract | None) -> dict[str, Any]:
    plan = {
        "underlying_invalidation": setup.stop,
        "underlying_target": setup.target,
        "take_profit": "Scale 50% at +35% to +50% contract gain; trail runner if underlying clears target.",
        "stop_loss": "Cut at -25% to -30% contract loss or if underlying closes through invalidation.",
        "time_stop": "Avoid holding inside 3 DTE unless thesis is actively working; close weak contracts before final-hour theta burn.",
        "position_size": "Risk 0.5%-1.0% account per idea; for small accounts, 1 contract or defined-risk spread only.",
    }
    if contract:
        plan.update(
            {
                "estimated_contract_cost": round(contract.ask * 100, 2),
                "mid_contract_value": round(contract.mid * 100, 2),
                "breakeven": contract.breakeven,
                "expiry": contract.expiration,
                "dte": contract.dte,
            }
        )
    return plan


def format_signal(signal: Signal) -> str:
    s = signal.setup
    c = signal.contract
    icon = "🟢" if s.direction == "long" else "🔴" if s.direction == "short" else "⚪"
    lines = [
        f"{icon} **{s.setup} — {s.symbol}**",
        f"Score `{signal.total_score:.1f}` | Direction `{s.direction}` | R/R `{s.reward_risk or 'n/a'}`",
        "",
        f"**Symbol** `{s.symbol}`  **Entry** `${s.entry:.2f}`  **Position** `{s.direction}`",
        f"**Target** `${s.target:.2f}`  **Stoploss** `${s.stop:.2f}`  **Potential Profit** `${s.potential_profit:.2f}`",
        "",
    ]
    if c:
        iv_txt = f"{c.implied_volatility * 100:.1f}%" if c.implied_volatility else "n/a"
        delta_txt = f"{c.approx_delta:+.2f}" if c.approx_delta is not None else "n/a"
        lines.extend(
            [
                "**Suggested Contract**",
                f"> **Type:** `{c.type}`",
                f"> **Expiration:** `{c.expiration}` (`{c.dte}` DTE)",
                f"> **Strike:** `${c.strike:g}`",
                f"> **Bid/Ask:** `${c.bid:.2f}` / `${c.ask:.2f}`  mid `${c.mid:.2f}`",
                f"> **Vol/OI:** `{c.volume:,}` / `{c.open_interest:,}`",
                f"> **IV/Δ:** `{iv_txt}` / `{delta_txt}`",
                f"> **BE:** `${c.breakeven:.2f}` | **Est cost:** `${c.ask * 100:.0f}`/contract",
                "",
            ]
        )
    else:
        lines.extend(["**Suggested Contract:** none — no liquid chain candidate found", ""])
    why = ", ".join(s.why[:5]) or "no confirmed edge"
    flags = sorted(set((s.risk_flags or []) + ((c.risk_flags if c else []) or [])))
    lines.append(f"**Why:** {why}")
    if c and c.expected_move:
        lines.append(f"**Expected move:** ±`${c.expected_move:.2f}` by expiry from selected contract IV proxy")
    if flags:
        lines.append(f"**Flags:** {', '.join(flags[:5])}")
    lines.extend(
        [
            "**Management:** +35-50% trim, -25-30% stop, respect underlying stop, avoid dead contracts near 3 DTE.",
            "_Research/paper signal only — no auto-execution._",
        ]
    )
    return "\n".join(lines)


def scan_symbols(
    symbols: list[str],
    *,
    lookback: str,
    min_underlying_score: float,
    min_total_score: float,
    min_dte: int,
    max_dte: int,
    max_expirations: int,
    max_signals: int,
) -> list[Signal]:
    signals: list[Signal] = []
    for symbol in symbols:
        setup = analyze_underlying(symbol, lookback=lookback, min_underlying_score=min_underlying_score)
        contract = find_contract(setup, min_dte=min_dte, max_dte=max_dte, max_expirations=max_expirations)
        contract_bonus = 0.0
        if contract:
            contract_bonus += min(contract.liquidity_score, 80) * 0.25
            if contract.spread_pct is not None and contract.spread_pct <= 15:
                contract_bonus += 5
            if contract.volume >= 100 and contract.open_interest >= 250:
                contract_bonus += 5
        total_score = round(min(100, setup.score * 0.72 + contract_bonus), 2)
        if setup.direction == "neutral" or setup.score < min_underlying_score or total_score < min_total_score:
            continue
        signal = Signal(
            symbol=setup.symbol,
            rank=0,
            total_score=total_score,
            setup=setup,
            contract=contract,
            management=management_plan(setup, contract),
            signal_text="",
        )
        signal = Signal(**{**asdict(signal), "setup": setup, "contract": contract, "signal_text": ""})  # type: ignore[arg-type]
        signals.append(signal)
    signals.sort(key=lambda sig: sig.total_score, reverse=True)
    ranked: list[Signal] = []
    for idx, sig in enumerate(signals[:max_signals], start=1):
        ranked_sig = Signal(
            symbol=sig.symbol,
            rank=idx,
            total_score=sig.total_score,
            setup=sig.setup,
            contract=sig.contract,
            management=sig.management,
            signal_text="",
        )
        ranked.append(
            Signal(
                symbol=ranked_sig.symbol,
                rank=ranked_sig.rank,
                total_score=ranked_sig.total_score,
                setup=ranked_sig.setup,
                contract=ranked_sig.contract,
                management=ranked_sig.management,
                signal_text=format_signal(ranked_sig),
            )
        )
    return ranked


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Options signal scanner")
    parser.add_argument("--symbols", default="SPY,QQQ,NVDA,TSLA,AMD,SMH,AAPL,MSFT,AMZN,GOOGL,META,COIN,MSTR,IWM")
    parser.add_argument("--lookback", default="6mo")
    parser.add_argument("--min-underlying-score", type=float, default=55)
    parser.add_argument("--min-total-score", type=float, default=55)
    parser.add_argument("--min-dte", type=int, default=7)
    parser.add_argument("--max-dte", type=int, default=45)
    parser.add_argument("--max-expirations", type=int, default=4)
    parser.add_argument("--max-signals", type=int, default=3)
    parser.add_argument("--out", default=str(ROOT / "runs" / "options_signals_latest.json"))
    parser.add_argument("--markdown-out", default=str(ROOT / "runs" / "options_signal_example.md"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    signals = scan_symbols(
        symbols,
        lookback=args.lookback,
        min_underlying_score=args.min_underlying_score,
        min_total_score=args.min_total_score,
        min_dte=args.min_dte,
        max_dte=args.max_dte,
        max_expirations=args.max_expirations,
        max_signals=args.max_signals,
    )
    payload = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "data_source": "yfinance delayed/free data; upgrade path Tradier/Alpaca/OPRA snapshots",
        "symbols": symbols,
        "methodology": {
            "underlying": [
                "setup pattern: bullish/bearish reversal, trend pullback, breakout/continuation",
                "chart levels: 20/50DMA, 20-day support/resistance, ATR stop/target",
                "confirmation: RSI, relative volume, 5D/20D momentum",
            ],
            "options": [
                "expiration 7-45 DTE by default",
                "strike near technical target with approximate 0.30-0.55 delta preference",
                "liquidity: bid/ask spread, volume, open interest, premium sanity",
                "risk: expected move, breakeven, contract cost, DTE, IV",
            ],
            "management": [
                "+35-50% trim zone",
                "-25-30% premium stop",
                "underlying invalidation stop",
                "avoid weak contracts inside 3 DTE",
            ],
        },
        "signals": [asdict(sig) for sig in signals],
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    md = Path(args.markdown_out)
    md.parent.mkdir(parents=True, exist_ok=True)
    if signals:
        md.write_text(signals[0].signal_text + "\n", encoding="utf-8")
    else:
        md.write_text("No qualifying options signal found with current filters.\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
