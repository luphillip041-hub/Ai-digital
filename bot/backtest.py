"""Backtester: replays the live strategies over Alpaca historical data.

Run from the repository root:  python -m bot.backtest [--months 6]

Fidelity notes — this reuses the *live* code paths, not reimplementations:
  * the exact Strategy classes generate signals from completed bars,
  * RiskManager does the sizing (1 ATR = 1% equity), hard stops (1 ATR),
    trailing stops (2x/3x ATR), and the SPY+QQQ -> BTC correlation filter,
  * equity instruments only act on bars whose close falls inside regular
    market hours (crypto acts 24/7), matching the live loop's clock gating.

Simulation conventions:
  * entries/exits fill at the signal bar's close +/- 0.05% slippage
    (SLIPPAGE); commission is $0 (Alpaca),
  * stops are checked intrabar: a bar whose low (long) / high (short)
    crosses the stop fills at the stop level — or at the open if the bar
    gapped through it — with slippage applied,
  * position sizing uses mark-to-market equity at signal time.

Outputs: per-instrument stats table (standalone runs), combined portfolio
stats (all 5 sharing equity, correlation filter active), an equity-curve
chart (backtest_results.png), and flags for any strategy with a negative
Sharpe ratio or a max drawdown beyond -15%.
"""

import argparse
import logging
import math
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

import config
from bot import indicators
from bot.broker import Broker
from bot.portfolio import Position
from bot.risk_manager import RiskManager
from bot.strategies import STRATEGY_REGISTRY
from bot.strategies.base import EXIT, LONG, SHORT

logger = logging.getLogger("backtest")

SLIPPAGE = 0.0005          # 0.05% adverse price movement per fill
COMMISSION = 0.0           # Alpaca is commission-free
STARTING_EQUITY = 100_000.0
NY = ZoneInfo("America/New_York")


@dataclass
class Trade:
    symbol: str
    direction: str
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    entry_price: float
    exit_price: float
    qty: float
    pnl: float
    reason: str


class _Book:
    """Minimal portfolio stand-in with the interface RiskManager needs."""

    def __init__(self):
        self.positions: Dict[str, Position] = {}

    def is_long(self, symbol: str) -> bool:
        pos = self.positions.get(symbol)
        return pos is not None and pos.direction == "long"


class Backtester:
    """Replays one or more instruments chronologically over shared equity."""

    def __init__(self, data: Dict[str, pd.DataFrame], trade_start: pd.Timestamp,
                 use_correlation_filter: bool):
        self.data = data
        self.trade_start = trade_start
        self.use_correlation_filter = use_correlation_filter
        self.risk = RiskManager()
        self.strategies = {
            key: STRATEGY_REGISTRY[config.INSTRUMENTS[key]["strategy"]](
                key, config.INSTRUMENTS[key]["params"])
            for key in data
        }
        self.book = _Book()
        self.realized = 0.0
        self.last_price: Dict[str, float] = {}
        self.trades: List[Trade] = []
        self.blocked_by_correlation = 0
        self.equity_points: List[tuple] = []

    # ------------------------------------------------------------------
    def run(self) -> dict:
        order = {k: i for i, k in enumerate(config.INSTRUMENTS)}
        events = []
        for key, df in self.data.items():
            tf = timedelta(minutes=config.INSTRUMENTS[key]["timeframe_minutes"])
            warmup = self.strategies[key].required_bars
            for i in range(len(df)):
                close_time = df.index[i] + tf
                if i + 1 >= warmup and close_time >= self.trade_start:
                    events.append((close_time, order[key], key, i))
        events.sort(key=lambda e: (e[0], e[1]))

        for close_time, _, key, i in events:
            self._process(key, i, close_time)

        # Force-close anything still open at the end so results are realized.
        for key in list(self.book.positions):
            self._close(key, self.last_price[key],
                        self.data[key].index[-1], "end of backtest")

        equity = pd.Series(
            dict(self.equity_points), dtype=float).sort_index()
        return {
            "trades": self.trades,
            "equity": equity,
            "blocked": self.blocked_by_correlation,
        }

    # ------------------------------------------------------------------
    def _process(self, key: str, i: int, close_time: pd.Timestamp) -> None:
        cfg = config.INSTRUMENTS[key]
        df = self.data[key]
        bar = df.iloc[i]
        self.last_price[key] = float(bar["close"])

        # Live loop only touches equities while the market is open.
        if cfg["asset_class"] == "equity" and not self._market_hours(close_time):
            self._record_equity(close_time)
            return

        strategy = self.strategies[key]
        window = df.iloc[max(0, i - strategy.required_bars - 30): i + 1]
        atr = float(indicators.atr(window, config.ATR_PERIOD).iloc[-1])

        pos = self.book.positions.get(key)
        if pos is not None:
            pos = self._check_stops_intrabar(key, pos, bar, close_time)
        if pos is not None:
            if pos.direction == "long":
                pos.best_price = max(pos.best_price, float(bar["high"]))
            else:
                pos.best_price = min(pos.best_price, float(bar["low"]))
            self.risk.update_trailing_stop(pos, atr)

        direction = pos.direction if pos else None
        signal = strategy.evaluate(window, direction)
        if signal.action != "none":
            self._handle_signal(key, cfg, signal, atr, bar, close_time)

        self._record_equity(close_time)

    @staticmethod
    def _market_hours(close_time: pd.Timestamp) -> bool:
        t = close_time.tz_convert(NY)
        if t.weekday() >= 5:
            return False
        minutes = t.hour * 60 + t.minute
        return 9 * 60 + 30 <= minutes <= 16 * 60

    # ------------------------------------------------------------------
    def _check_stops_intrabar(self, key: str, pos: Position, bar,
                              close_time) -> Optional[Position]:
        if pos.direction == "long":
            stop = pos.hard_stop
            if pos.trail_stop is not None:
                stop = max(stop, pos.trail_stop)
            if float(bar["low"]) <= stop:
                level = min(stop, float(bar["open"]))  # gap-through fills worse
                which = ("trailing stop" if pos.trail_stop is not None
                         and pos.trail_stop >= pos.hard_stop else "hard stop")
                self._close(key, level, close_time, which)
                return None
        else:
            stop = pos.hard_stop
            if pos.trail_stop is not None:
                stop = min(stop, pos.trail_stop)
            if float(bar["high"]) >= stop:
                level = max(stop, float(bar["open"]))
                which = ("trailing stop" if pos.trail_stop is not None
                         and pos.trail_stop <= pos.hard_stop else "hard stop")
                self._close(key, level, close_time, which)
                return None
        return pos

    # ------------------------------------------------------------------
    def _handle_signal(self, key, cfg, signal, atr, bar, close_time) -> None:
        pos = self.book.positions.get(key)
        price = float(bar["close"])

        if signal.action == EXIT:
            if pos is not None:
                self._close(key, price, close_time, f"strategy exit: {signal.reason}")
            return

        if signal.action == LONG:
            if pos is not None and pos.direction == "long":
                return
            if pos is not None:
                self._close(key, price, close_time, "reversing to long")
            if (self.use_correlation_filter
                    and self.risk.correlation_blocks_long(key, self.book)):
                self.blocked_by_correlation += 1
                return
            self._open(key, cfg, "long", atr, price, close_time, signal.reason)
            return

        if signal.action == SHORT:
            if pos is not None and pos.direction == "short":
                return
            if pos is not None:
                self._close(key, price, close_time, f"short signal: {signal.reason}")
            if not cfg["shortable"]:
                return
            self._open(key, cfg, "short", atr, price, close_time, signal.reason)

    # ------------------------------------------------------------------
    def _mtm_equity(self) -> float:
        equity = STARTING_EQUITY + self.realized
        for key, pos in self.book.positions.items():
            last = self.last_price.get(key, pos.entry_price)
            if pos.direction == "long":
                equity += (last - pos.entry_price) * pos.qty
            else:
                equity += (pos.entry_price - last) * pos.qty
        return equity

    def _record_equity(self, ts) -> None:
        self.equity_points.append((ts, self._mtm_equity()))

    def _open(self, key, cfg, direction, atr, price, ts, reason) -> None:
        equity = self._mtm_equity()
        qty = self.risk.position_size(equity, atr, price, cfg["asset_class"])
        if qty <= 0:
            return
        fill = price * (1 + SLIPPAGE) if direction == "long" else price * (1 - SLIPPAGE)
        stop_distance = self.risk.hard_stop_distance(equity, qty, atr)
        self.book.positions[key] = Position(
            symbol=key, direction=direction, qty=qty, entry_price=fill,
            entry_time=str(ts), atr_at_entry=atr,
            hard_stop=self.risk.hard_stop_price(fill, stop_distance, direction),
            trail_atr_mult=cfg["trail_atr_mult"], best_price=fill,
            strategy=cfg["strategy"],
        )

    def _close(self, key, level, ts, reason) -> None:
        pos = self.book.positions.pop(key)
        fill = level * (1 - SLIPPAGE) if pos.direction == "long" else level * (1 + SLIPPAGE)
        if pos.direction == "long":
            pnl = (fill - pos.entry_price) * pos.qty - COMMISSION
        else:
            pnl = (pos.entry_price - fill) * pos.qty - COMMISSION
        self.realized += pnl
        self.trades.append(Trade(
            symbol=key, direction=pos.direction,
            entry_time=pd.Timestamp(pos.entry_time), exit_time=ts,
            entry_price=pos.entry_price, exit_price=fill,
            qty=pos.qty, pnl=pnl, reason=reason,
        ))


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------
def compute_stats(trades: List[Trade], equity: pd.Series,
                  periods_per_year: int) -> dict:
    pnls = np.array([t.pnl for t in trades])
    wins, losses = pnls[pnls > 0], pnls[pnls <= 0]
    gross_win, gross_loss = wins.sum(), -losses.sum()

    if len(equity) >= 2:
        total_return = equity.iloc[-1] / equity.iloc[0] - 1
        max_dd = float((equity / equity.cummax() - 1).min())
        daily = equity.resample("1D").last().dropna().pct_change().dropna()
        sharpe = (float(daily.mean() / daily.std() * math.sqrt(periods_per_year))
                  if len(daily) > 5 and daily.std() > 0 else float("nan"))
    else:
        total_return, max_dd, sharpe = 0.0, 0.0, float("nan")

    return {
        "trades": len(trades),
        "win_rate": len(wins) / len(pnls) if len(pnls) else float("nan"),
        "avg_win": wins.mean() if len(wins) else float("nan"),
        "avg_loss": losses.mean() if len(losses) else float("nan"),
        "profit_factor": (gross_win / gross_loss if gross_loss > 0
                          else float("inf") if gross_win > 0 else float("nan")),
        "max_dd": max_dd,
        "sharpe": sharpe,
        "total_return": total_return,
    }


# ---------------------------------------------------------------------------
# Chart (palette + specs per the dataviz reference system, light mode)
# ---------------------------------------------------------------------------
CHART = {
    "surface": "#fcfcfb", "ink": "#0b0b0b", "ink2": "#52514e",
    "muted": "#898781", "grid": "#e1e0d9", "baseline": "#c3c2b7",
    # categorical slots 1-6, fixed order (validated for CVD separation)
    "series": ["#2a78d6", "#1baf7a", "#eda100", "#008300", "#4a3aa7", "#e34948"],
}


def plot_equity_curves(combined: pd.Series, singles: Dict[str, pd.Series],
                       months: int, out_path: str) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(11.5, 6.2), dpi=160)
    fig.set_facecolor(CHART["surface"])
    ax.set_facecolor(CHART["surface"])

    curves = [("Combined", combined)] + [
        (k, s) for k, s in singles.items()
    ]
    ends = []
    for idx, (name, series) in enumerate(curves):
        daily = series.resample("1D").last().dropna()
        color = CHART["series"][idx % len(CHART["series"])]
        lw = 2.4 if name == "Combined" else 1.5
        ax.plot(daily.index, daily.values, color=color, lw=lw,
                solid_capstyle="round", zorder=3 if name == "Combined" else 2)
        ends.append((name, daily.index[-1], float(daily.iloc[-1]), color))

    # Direct end labels in ink (relief for low-contrast hues), anti-collision.
    lo, hi = ax.get_ylim()
    min_gap = (hi - lo) * 0.04
    ends.sort(key=lambda e: e[2])
    label_y = []
    for _, _, y, _ in ends:
        if label_y and y - label_y[-1] < min_gap:
            y = label_y[-1] + min_gap
        label_y.append(y)
    for (name, x, _, color), y in zip(ends, label_y):
        ax.annotate(f"  {name}", xy=(x, y), xycoords="data",
                    fontsize=9, color=CHART["ink2"], va="center",
                    fontweight="bold" if name == "Combined" else "normal")
        ax.plot([x], [y], marker="o", ms=4, color=color, clip_on=False,
                zorder=4)

    ax.grid(axis="y", color=CHART["grid"], lw=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(CHART["baseline"])
    ax.tick_params(colors=CHART["muted"], labelcolor=CHART["ink2"], length=0)
    ax.yaxis.set_major_formatter(
        plt.FuncFormatter(lambda v, _: f"${v / 1000:,.0f}k"))
    ax.margins(x=0.01)
    ax.set_xlim(right=ax.get_xlim()[1] * 1.0)

    ax.set_title(f"Backtest equity curves — {months} months, "
                 f"${STARTING_EQUITY:,.0f} start",
                 color=CHART["ink"], fontsize=13, loc="left", pad=14)
    ax.text(0, 1.015, "Combined = all 5 instruments, shared equity, "
            "correlation filter on. Instrument lines = standalone runs. "
            "0.05% slippage per fill.",
            transform=ax.transAxes, fontsize=9, color=CHART["ink2"])
    ax.legend([name for name, _ in curves], loc="upper left", frameon=False,
              fontsize=9, labelcolor=CHART["ink2"])

    fig.tight_layout()
    fig.savefig(out_path, facecolor=CHART["surface"], bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------
def _fmt_row(name, strat, s) -> str:
    def pct(x):
        return f"{x * 100:+.1f}%" if x == x else "  n/a"

    def usd(x):
        return f"${x:,.0f}" if x == x else "n/a"

    pf = ("inf" if s["profit_factor"] == float("inf")
          else f"{s['profit_factor']:.2f}" if s["profit_factor"] == s["profit_factor"]
          else "n/a")
    sharpe = f"{s['sharpe']:+.2f}" if s["sharpe"] == s["sharpe"] else "  n/a"
    win = f"{s['win_rate'] * 100:.0f}%" if s["win_rate"] == s["win_rate"] else "n/a"
    return (f"{name:<10} {strat:<18} {s['trades']:>6} {win:>7} "
            f"{usd(s['avg_win']):>9} {usd(s['avg_loss']):>9} {pf:>6} "
            f"{pct(s['max_dd']):>8} {sharpe:>7} {pct(s['total_return']):>8}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest the live strategies")
    parser.add_argument("--months", type=int, default=6)
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING)
    broker = Broker()

    end = datetime.now(timezone.utc)
    trade_start = pd.Timestamp(end - timedelta(days=round(args.months * 30.44)))

    print(f"Backtest window: {trade_start.date()} -> {end.date()} "
          f"({args.months} months), ${STARTING_EQUITY:,.0f} starting equity, "
          f"{SLIPPAGE * 100:.2f}% slippage, ${COMMISSION:.0f} commission\n")

    # ------------------------------------------------------------- data
    data: Dict[str, pd.DataFrame] = {}
    for key, cfg in config.INSTRUMENTS.items():
        strategy_cls = STRATEGY_REGISTRY[cfg["strategy"]]
        minutes = cfg["timeframe_minutes"]
        per_day = (24 * 60 if cfg["asset_class"] == "crypto" else 390) / minutes
        warmup_days = math.ceil(strategy_cls.required_bars / per_day * 1.6) + 7
        fetch_start = (trade_start - timedelta(days=warmup_days)).isoformat()
        df = broker.get_bars_range(cfg, fetch_start, end.isoformat())
        # keep only bars fully closed
        tf = timedelta(minutes=minutes)
        df = df[df.index + tf <= pd.Timestamp(end)]
        data[key] = df
        n_window = int((df.index + tf > trade_start).sum())
        print(f"  {key:<8} {len(df):>6} bars fetched "
              f"({n_window} in trade window, {len(df) - n_window} warm-up)")
        if len(df) - n_window < strategy_cls.required_bars:
            print(f"           WARNING: warm-up shorter than required "
                  f"{strategy_cls.required_bars} bars — early signals skipped")
    print()

    # ------------------------------------------- standalone per instrument
    singles_stats, singles_equity = {}, {}
    for key in config.INSTRUMENTS:
        result = Backtester({key: data[key]}, trade_start,
                            use_correlation_filter=False).run()
        ppy = 365 if config.INSTRUMENTS[key]["asset_class"] == "crypto" else 252
        singles_stats[key] = compute_stats(result["trades"], result["equity"], ppy)
        singles_equity[key] = result["equity"]

    # ------------------------------------------------- combined portfolio
    combined = Backtester(dict(data), trade_start,
                          use_correlation_filter=True).run()
    combined_stats = compute_stats(combined["trades"], combined["equity"], 252)

    # ------------------------------------------------------------- report
    header = (f"{'Instrument':<10} {'Strategy':<18} {'Trades':>6} {'Win%':>7} "
              f"{'AvgWin':>9} {'AvgLoss':>9} {'PF':>6} {'MaxDD':>8} "
              f"{'Sharpe':>7} {'Return':>8}")
    print(header)
    print("-" * len(header))
    for key, s in singles_stats.items():
        print(_fmt_row(key, config.INSTRUMENTS[key]["strategy"], s))
    print("-" * len(header))
    print(_fmt_row("COMBINED", "all + corr filter", combined_stats))
    print(f"\nCorrelation filter blocked {combined['blocked']} BTC/USD long "
          f"entr{'y' if combined['blocked'] == 1 else 'ies'} in the combined run.")

    # -------------------------------------------------------------- flags
    flags = []
    for key, s in singles_stats.items():
        if s["sharpe"] == s["sharpe"] and s["sharpe"] < 0:
            flags.append(f"{key} ({config.INSTRUMENTS[key]['strategy']}): "
                         f"NEGATIVE SHARPE {s['sharpe']:+.2f} — adjust parameters")
        if s["max_dd"] < -0.15:
            flags.append(f"{key} ({config.INSTRUMENTS[key]['strategy']}): "
                         f"max drawdown {s['max_dd'] * 100:.1f}% exceeds -15%")
        if s["trades"] == 0:
            flags.append(f"{key} ({config.INSTRUMENTS[key]['strategy']}): "
                         f"ZERO TRADES — strategy never triggered in window")
    if combined_stats["sharpe"] == combined_stats["sharpe"] and combined_stats["sharpe"] < 0:
        flags.append(f"COMBINED portfolio: NEGATIVE SHARPE "
                     f"{combined_stats['sharpe']:+.2f}")
    if combined_stats["max_dd"] < -0.15:
        flags.append(f"COMBINED portfolio: max drawdown "
                     f"{combined_stats['max_dd'] * 100:.1f}% exceeds -15%")

    print()
    if flags:
        print("⚠️  FLAGS — review before going live:")
        for f in flags:
            print(f"   - {f}")
    else:
        print("✅ No flags: every strategy has non-negative Sharpe and "
              "drawdown within -15%.")

    # -------------------------------------------------------------- chart
    if len(combined["equity"]) >= 2:
        plot_equity_curves(combined["equity"], singles_equity, args.months,
                           "backtest_results.png")
        print("\nEquity curve chart saved to backtest_results.png")
    else:
        print("\nNot enough equity points to chart.")

    sys.exit(2 if flags else 0)


if __name__ == "__main__":
    main()
