"""Command-line interface.

    python -m mltrader.cli backtest --symbol SPY
    python -m mltrader.cli backtest --synthetic          # no API keys needed
    python -m mltrader.cli train --symbol SPY --out models/SPY.joblib
    python -m mltrader.cli trade --dry-run               # one rebalance cycle
    python -m mltrader.cli bot                           # daily rebalance loop
    python -m mltrader.cli serve --port 8000             # web dashboard
    python -m mltrader.cli status
"""

from __future__ import annotations

import argparse
import time
from datetime import date

from . import engine
from .backtest import walk_forward_backtest
from .config import Settings
from .data import fetch_daily_bars, synthetic_daily_bars
from .features import build_dataset
from .model import save_model, train


def _load_bars(settings: Settings, symbol: str, synthetic: bool, years: float):
    if synthetic:
        return synthetic_daily_bars(n_days=int(years * 252))
    return fetch_daily_bars(settings, symbol, years=years)


def cmd_backtest(args, settings: Settings) -> None:
    bars = _load_bars(settings, args.symbol, args.synthetic, args.years)
    result = walk_forward_backtest(
        bars,
        entry_threshold=args.threshold if args.threshold is not None else settings.entry_threshold,
    )
    label = "synthetic data" if args.synthetic else args.symbol
    print(f"Walk-forward backtest — {label}")
    print(result.summary())


def cmd_train(args, settings: Settings) -> None:
    bars = _load_bars(settings, args.symbol, args.synthetic, args.years)
    dataset = build_dataset(bars)
    model = train(dataset)
    save_model(model, args.out)
    print(f"Trained on {len(dataset)} rows, saved to {args.out}")


def _run_cycle(broker, settings: Settings, years: float, dry_run: bool) -> None:
    mode = "PAPER" if settings.paper else "LIVE"
    print(f"[{mode}] rebalance cycle for {', '.join(settings.symbols)}")

    if not dry_run and not broker.market_is_open():
        print("Market is closed — orders would not fill at expected prices. "
              "Use --dry-run to preview, or run during market hours.")
        return

    report = engine.rebalance(broker, settings, years=years, dry_run=dry_run)
    for symbol, p in report["signals"].items():
        print(f"  {symbol}: P(up) = {p:.3f}")
    if not report["orders"]:
        print("Portfolio already at target — no orders.")
        return
    tag = "[dry-run]" if dry_run else "[sent]  "
    for o in report["orders"]:
        print(f"{tag}  {o['side'].upper():4s} {o['symbol']} ${o['notional']:,.2f}")


def cmd_trade(args, settings: Settings) -> None:
    from .broker import AlpacaBroker

    _run_cycle(AlpacaBroker(settings), settings, args.years, args.dry_run)


def cmd_bot(args, settings: Settings) -> None:
    """Long-running loop: one rebalance per market day, then idle."""
    from .broker import AlpacaBroker

    broker = AlpacaBroker(settings)
    last_run: date | None = None
    print(f"bot started — checking every {args.every}s, one rebalance per market day")
    while True:
        try:
            if last_run != date.today() and broker.market_is_open():
                _run_cycle(broker, settings, args.years, dry_run=False)
                last_run = date.today()
        except Exception as exc:  # keep the loop alive through transient API errors
            print(f"cycle failed, will retry next check: {exc}")
        time.sleep(args.every)


def cmd_serve(args, settings: Settings) -> None:
    import uvicorn

    from .server import create_app

    uvicorn.run(create_app(settings), host=args.host, port=args.port)


def cmd_status(args, settings: Settings) -> None:
    from .broker import AlpacaBroker

    broker = AlpacaBroker(settings)
    print(f"mode:   {'PAPER' if settings.paper else 'LIVE'}")
    print(f"equity: ${broker.equity():,.2f}")
    positions = broker.positions_notional()
    if positions:
        for symbol, notional in sorted(positions.items()):
            print(f"  {symbol}: ${notional:,.2f}")
    else:
        print("  (no open positions)")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="mltrader", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_bt = sub.add_parser("backtest", help="walk-forward backtest one symbol")
    p_bt.add_argument("--symbol", default="SPY")
    p_bt.add_argument("--years", type=float, default=6.0)
    p_bt.add_argument("--threshold", type=float, default=None)
    p_bt.add_argument("--synthetic", action="store_true", help="use synthetic bars (no keys)")
    p_bt.set_defaults(func=cmd_backtest)

    p_tr = sub.add_parser("train", help="train and save a model for one symbol")
    p_tr.add_argument("--symbol", default="SPY")
    p_tr.add_argument("--years", type=float, default=6.0)
    p_tr.add_argument("--out", default="models/model.joblib")
    p_tr.add_argument("--synthetic", action="store_true")
    p_tr.set_defaults(func=cmd_train)

    p_td = sub.add_parser("trade", help="run one rebalance cycle on Alpaca")
    p_td.add_argument("--years", type=float, default=6.0)
    p_td.add_argument("--dry-run", action="store_true", help="print orders without sending")
    p_td.set_defaults(func=cmd_trade)

    p_bot = sub.add_parser("bot", help="run the daily rebalance loop")
    p_bot.add_argument("--years", type=float, default=6.0)
    p_bot.add_argument("--every", type=int, default=1800, help="seconds between checks")
    p_bot.set_defaults(func=cmd_bot)

    p_sv = sub.add_parser("serve", help="run the web dashboard")
    p_sv.add_argument("--host", default="127.0.0.1")
    p_sv.add_argument("--port", type=int, default=8000)
    p_sv.set_defaults(func=cmd_serve)

    p_st = sub.add_parser("status", help="show account equity and positions")
    p_st.set_defaults(func=cmd_status)

    args = parser.parse_args(argv)
    settings = Settings()
    args.func(args, settings)


if __name__ == "__main__":
    main()
