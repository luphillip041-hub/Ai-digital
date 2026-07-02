"""Morning briefing and evening performance report.

Usage (from the repository root):
    python -m bot.reports morning    # 7am pre-market briefing
    python -m bot.reports evening    # market-close performance report
    python -m bot.reports morning --no-send   # print only, skip notifier

Reads trades.csv / daily_pnl.csv / bot_state.json plus live Alpaca data,
prints the report, and pushes it through every configured notification
channel (Discord/Telegram/email). Designed to be run from cron:
    58 6 * * *   cd /path/to/repo && .venv/bin/python -m bot.reports morning
    5 16 * * 1-5 cd /path/to/repo && .venv/bin/python -m bot.reports evening
"""

import argparse
import csv
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import pandas as pd

import config
from bot import indicators
from bot.broker import Broker
from bot.notifier import Notifier, _money
from bot.portfolio import Portfolio

logger = logging.getLogger("reports")

VIX_PROXY = "VIXY"  # Alpaca has no VIX index feed; VIXY tracks ST VIX futures


# ---------------------------------------------------------------------------
# Data access helpers
# ---------------------------------------------------------------------------
def load_trades() -> pd.DataFrame:
    if not os.path.exists(config.TRADES_CSV):
        return pd.DataFrame()
    df = pd.read_csv(config.TRADES_CSV)
    if df.empty:
        return df
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, format="ISO8601")
    if "reason" not in df.columns:  # rows written before the column existed
        df["reason"] = ""
    return df


def trades_between(df: pd.DataFrame, start, end) -> pd.DataFrame:
    if df.empty:
        return df
    return df[(df["timestamp"] >= start) & (df["timestamp"] < end)]


def win_stats(df: pd.DataFrame) -> Optional[dict]:
    if df.empty:
        return None
    pnl = df["pnl"].astype(float)
    wins, losses = pnl[pnl > 0], pnl[pnl <= 0]
    return {
        "trades": len(pnl),
        "win_rate": len(wins) / len(pnl),
        "profit_factor": (wins.sum() / -losses.sum()) if losses.sum() < 0
        else float("inf"),
        "net": pnl.sum(),
    }


def _bars_cfg(symbol: str, minutes: int) -> dict:
    return {"asset_class": "equity" if symbol != "BTC/USD" else "crypto",
            "data_symbol": symbol, "timeframe_minutes": minutes}


# ---------------------------------------------------------------------------
# Shared sections
# ---------------------------------------------------------------------------
def positions_section(broker: Broker, portfolio: Portfolio) -> List[str]:
    lines = []
    if not portfolio.positions:
        return ["  none — bot is flat on all 5 instruments"]
    for key, pos in portfolio.positions.items():
        cfg = config.INSTRUMENTS[key]
        price = broker.get_latest_price(cfg)
        if price is None:
            lines.append(f"  {key}: {pos.direction} {pos.qty} @ "
                         f"${pos.entry_price:,.2f} (price unavailable)")
            continue
        upnl = ((price - pos.entry_price) if pos.direction == "long"
                else (pos.entry_price - price)) * pos.qty
        stop = pos.hard_stop
        if pos.trail_stop is not None:
            stop = (max(stop, pos.trail_stop) if pos.direction == "long"
                    else min(stop, pos.trail_stop))
        lines.append(
            f"  {key}: {pos.direction.upper()} {pos.qty} @ ${pos.entry_price:,.2f}"
            f" | now ${price:,.2f} | unrealized {_money(upnl)}"
            f" | stop ${stop:,.2f}")
    return lines


def risk_flags(broker: Broker, portfolio: Portfolio,
               equity: Optional[float]) -> List[str]:
    flags = []
    # 1. Positions approaching the 1%-equity hard stop
    for key, pos in portfolio.positions.items():
        price = broker.get_latest_price(config.INSTRUMENTS[key])
        if price is None:
            continue
        full = abs(pos.entry_price - pos.hard_stop)
        left = ((price - pos.hard_stop) if pos.direction == "long"
                else (pos.hard_stop - price))
        if full > 0 and left / full <= 0.25:
            flags.append(f"⚠️ {key} has used {100 - left / full * 100:.0f}% of "
                         f"its stop distance (price ${price:,.2f}, "
                         f"stop ${pos.hard_stop:,.2f})")
    # 2. Correlation filter state
    cf = config.CORRELATION_FILTER
    if all(portfolio.is_long(s) for s in cf["requires_long"]):
        flags.append(f"⚠️ correlation filter ACTIVE: "
                     f"{' + '.join(cf['requires_long'])} both long — new "
                     f"{cf['blocked_symbol']} longs are blocked")
    # 3. Drawdown from peak equity (peak from daily_pnl history + now)
    if equity is not None and os.path.exists(config.DAILY_PNL_CSV):
        hist = pd.read_csv(config.DAILY_PNL_CSV)
        peaks = pd.to_numeric(hist.get("account_equity"), errors="coerce").dropna()
        peak = max(peaks.max() if len(peaks) else equity, equity)
        dd = equity / peak - 1
        if dd < -0.05:
            flags.append(f"⚠️ portfolio drawdown {dd * 100:.1f}% from peak "
                         f"${peak:,.0f} exceeds 5%")
    return flags or ["  none"]


# ---------------------------------------------------------------------------
# Morning briefing
# ---------------------------------------------------------------------------
def market_conditions(broker: Broker) -> List[str]:
    lines = []
    # VIX proxy: VIXY vs its own 20-day average
    try:
        vixy = broker.get_bars_range(
            _bars_cfg(VIX_PROXY, 1440),
            (datetime.now(timezone.utc) - timedelta(days=60)).isoformat(),
            datetime.now(timezone.utc).isoformat())
        last, avg = float(vixy["close"].iloc[-1]), float(vixy["close"].iloc[-21:-1].mean())
        state = ("ELEVATED" if last > avg * 1.10
                 else "subdued" if last < avg * 0.90 else "normal")
        lines.append(f"  volatility ({VIX_PROXY} as VIX proxy): {state} — "
                     f"${last:.2f} vs 20d avg ${avg:.2f}")
    except Exception as exc:
        lines.append(f"  volatility check unavailable ({exc})")
    # Index regime: 20 vs 50 EMA on hourly bars
    for sym in ("SPY", "QQQ"):
        try:
            bars = broker.get_bars_range(
                _bars_cfg(sym, 60),
                (datetime.now(timezone.utc) - timedelta(days=30)).isoformat(),
                datetime.now(timezone.utc).isoformat())
            fast = indicators.ema(bars["close"], 20).iloc[-1]
            slow = indicators.ema(bars["close"], 50).iloc[-1]
            spread = (fast - slow) / float(bars["close"].iloc[-1])
            regime = ("trending UP" if spread > 0.0015
                      else "trending DOWN" if spread < -0.0015 else "RANGING")
            lines.append(f"  {sym}: {regime} (20/50 EMA spread "
                         f"{spread * 100:+.2f}%)")
        except Exception as exc:
            lines.append(f"  {sym} regime unavailable ({exc})")
    # Crypto volume vs its 20-day average
    try:
        bars = broker.get_bars_range(
            _bars_cfg("BTC/USD", 60),
            (datetime.now(timezone.utc) - timedelta(days=22)).isoformat(),
            datetime.now(timezone.utc).isoformat())
        vol24 = float(bars["volume"].iloc[-24:].sum())
        avg24 = float(bars["volume"].iloc[:-24].sum() / max((len(bars) - 24) / 24, 1))
        ratio = vol24 / avg24 if avg24 > 0 else float("nan")
        state = "UNUSUALLY HIGH" if ratio > 1.5 else \
                "unusually low" if ratio < 0.5 else "normal"
        lines.append(f"  BTC/USD 24h volume: {state} ({ratio:.1f}x 20d average)")
    except Exception as exc:
        lines.append(f"  BTC volume check unavailable ({exc})")
    return lines


def morning_report(broker: Broker, portfolio: Portfolio) -> str:
    now = datetime.now(timezone.utc)
    trades = load_trades()
    equity = None
    try:
        equity = broker.get_equity()
    except Exception as exc:
        logger.error("equity unavailable: %s", exc)

    # Yesterday's P&L, total and per instrument (UTC day, matching daily_pnl)
    y_start = pd.Timestamp((now - timedelta(days=1)).date(), tz="UTC")
    y_end = pd.Timestamp(now.date(), tz="UTC")
    y_trades = trades_between(trades, y_start, y_end)
    if y_trades.empty:
        yesterday_lines = ["  no trades closed yesterday"]
    else:
        yesterday_lines = [f"  total: {_money(y_trades['pnl'].sum())} over "
                           f"{len(y_trades)} trade(s)"]
        for sym, grp in y_trades.groupby("instrument"):
            yesterday_lines.append(f"    {sym}: {_money(grp['pnl'].sum())} "
                                   f"({len(grp)} trade(s))")

    week = win_stats(trades_between(trades, pd.Timestamp(now - timedelta(days=7)),
                                    pd.Timestamp(now)))
    week_line = (f"  {week['win_rate'] * 100:.0f}% over {week['trades']} trades "
                 f"(net {_money(week['net'])})" if week
                 else "  no trades in the last 7 days")

    sections = [
        f"OPEN POSITIONS",
        *positions_section(broker, portfolio),
        f"\nACCOUNT EQUITY\n  " + (f"${equity:,.2f}" if equity else "unavailable"),
        f"\nYESTERDAY'S P&L",
        *yesterday_lines,
        f"\nMARKET CONDITIONS",
        *market_conditions(broker),
        f"\n7-DAY WIN RATE\n{week_line}",
        f"\nRISK FLAGS",
        *risk_flags(broker, portfolio, equity),
    ]
    return "\n".join(sections)


# ---------------------------------------------------------------------------
# Evening report
# ---------------------------------------------------------------------------
def _trade_detail(row) -> str:
    return (f"{row['instrument']} {row['direction']} x{row['position_size']}: "
            f"in ${float(row['entry_price']):,.2f} -> out "
            f"${float(row['exit_price']):,.2f} = {_money(float(row['pnl']))}"
            + (f" ({row['reason']})" if str(row.get('reason', '')) not in ("", "nan") else ""))


def backtest_tracking(trades: pd.DataFrame) -> List[str]:
    lines = []
    for key, base in config.BACKTEST_BASELINE.items():
        sub = trades[trades["instrument"] == key] if not trades.empty else trades
        s = win_stats(sub)
        if s is None or s["trades"] < 5:
            n = s["trades"] if s else 0
            lines.append(f"  {key}: too few live trades ({n}) to compare "
                         f"(backtest: {base['win_rate'] * 100:.0f}% win, "
                         f"PF {base['profit_factor']:.2f})")
            continue
        dw = s["win_rate"] - base["win_rate"]
        verdict = ("in line with" if abs(dw) <= 0.15 else
                   "BETTER than" if dw > 0 else "WORSE than")
        lines.append(f"  {key}: {s['win_rate'] * 100:.0f}% win / PF "
                     f"{s['profit_factor']:.2f} over {s['trades']} trades — "
                     f"{verdict} backtest ({base['win_rate'] * 100:.0f}% / "
                     f"{base['profit_factor']:.2f})")
    return lines


def evening_report(broker: Broker, portfolio: Portfolio) -> str:
    now = datetime.now(timezone.utc)
    trades = load_trades()
    equity = None
    try:
        equity = broker.get_equity()
    except Exception as exc:
        logger.error("equity unavailable: %s", exc)

    t_start = pd.Timestamp(now.date(), tz="UTC")
    today = trades_between(trades, t_start, pd.Timestamp(now))

    if today.empty:
        today_lines = ["  no trades closed today"]
        best_worst = ["  n/a"]
        stop_lines = ["  no stop-loss exits today"]
        pnl_line = "  $0.00 realized today"
    else:
        today_lines = [f"  {len(today)} trade(s):"]
        for sym, grp in today.groupby("instrument"):
            today_lines.append(f"    {sym}: {len(grp)} trade(s), "
                               f"net {_money(grp['pnl'].sum())}")
        pnl = today["pnl"].sum()
        pct = f" ({pnl / equity * 100:+.2f}% of equity)" if equity else ""
        pnl_line = f"  {_money(pnl)}{pct}"
        best = today.loc[today["pnl"].idxmax()]
        worst = today.loc[today["pnl"].idxmin()]
        best_worst = [f"  best:  {_trade_detail(best)}",
                      f"  worst: {_trade_detail(worst)}"]
        stops = today[today["reason"].astype(str).str.contains("stop", case=False)]
        if stops.empty:
            stop_lines = ["  no stop-loss exits today"]
        else:
            stop_lines = []
            for _, row in stops.iterrows():
                loss_pct = (abs(float(row["pnl"])) / equity * 100) if equity else None
                ok = (loss_pct is not None and loss_pct <= 1.4)
                stop_lines.append(
                    f"  {_trade_detail(row)} — "
                    + (f"stop worked correctly (loss {loss_pct:.2f}% of equity, "
                       f"within 1% + slippage)" if ok else
                       f"REVIEW: loss {loss_pct:.2f}% of equity exceeds the "
                       f"1% rule" if loss_pct is not None else
                       "equity unavailable to verify"))

    sections = [
        "TRADES TODAY",
        *today_lines,
        f"\nTODAY'S P&L\n{pnl_line}",
        "\nBEST / WORST TRADE",
        *best_worst,
        f"\nCURRENT EQUITY\n  " + (f"${equity:,.2f}" if equity else "unavailable"),
        "\nBACKTEST TRACKING (all live trades vs 6-month backtest)",
        *backtest_tracking(trades),
        "\nSTOP-LOSS AUDIT",
        *stop_lines,
        "\nOPEN POSITIONS GOING INTO THE CLOSE",
        *positions_section(broker, portfolio),
    ]
    return "\n".join(sections)


# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="Generate bot reports")
    parser.add_argument("kind", choices=["morning", "evening"])
    parser.add_argument("--no-send", action="store_true",
                        help="print only; skip notification channels")
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING)
    broker = Broker()
    portfolio = Portfolio()

    if args.kind == "morning":
        title = f"☀️ Morning briefing — {datetime.now(timezone.utc):%Y-%m-%d}"
        body = morning_report(broker, portfolio)
    else:
        title = f"🌙 Evening report — {datetime.now(timezone.utc):%Y-%m-%d}"
        body = evening_report(broker, portfolio)

    print(title, body, sep="\n")
    if not args.no_send:
        Notifier().send(title, body)


if __name__ == "__main__":
    main()
