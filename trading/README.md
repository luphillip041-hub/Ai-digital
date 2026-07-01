# mltrader — ML trading system on the Alpaca API

A machine-learning trading system: it fetches daily bars from Alpaca, engineers
technical features, trains a gradient-boosted classifier to estimate the
probability that a symbol closes up tomorrow, validates the strategy with a
walk-forward backtest, and rebalances an Alpaca **paper** account from the
resulting signals.

## How it works

```
Alpaca daily bars ──▶ features.py ──▶ model.py (HistGradientBoosting)
                                          │
                       backtest.py ◀──────┤ P(next day up)
                     (walk-forward)       │
                                          ▼
                       risk.py (weights, caps) ──▶ broker.py ──▶ Alpaca orders
```

- **`data.py`** — daily OHLCV from Alpaca's data API, plus a synthetic
  generator so everything runs without API keys.
- **`features.py`** — 12 leakage-safe features (multi-horizon returns, SMA/EMA
  ratios, RSI, Bollinger z-score, realized vol, volume z-score, range). The
  label is next-day direction; the no-lookahead property is unit-tested.
- **`model.py`** — a small, heavily regularized `HistGradientBoostingClassifier`.
- **`backtest.py`** — walk-forward evaluation: retrain on a rolling 2-year
  window, trade the next quarter out-of-sample, repeat. Long/flat with
  transaction costs. Reports total return vs buy & hold, CAGR, Sharpe, max
  drawdown, hit rate, exposure.
- **`risk.py`** — converts signals into target weights with per-symbol and
  gross-exposure caps, then diffs against current holdings into orders.
- **`broker.py`** — thin Alpaca `TradingClient` wrapper, paper mode by default.

## Setup

```bash
cd trading
pip install -r requirements.txt
cp .env.example .env          # fill in your Alpaca PAPER keys
export $(grep -v '^#' .env | xargs)
```

## Usage

```bash
# No keys needed — sanity-check the pipeline on synthetic data
python -m mltrader.cli backtest --synthetic

# Backtest a real symbol (needs keys)
python -m mltrader.cli backtest --symbol SPY --years 6

# Preview what a rebalance would do, without sending orders
python -m mltrader.cli trade --dry-run

# Actually rebalance the paper account (market hours only)
python -m mltrader.cli trade

# Account equity and open positions
python -m mltrader.cli status
```

Run `trade` once per day near the close (e.g. via cron) — the model is built
on daily bars, so more frequent runs add cost without adding signal.

## Tests

```bash
cd trading && python -m pytest tests/ -q
```

All tests run offline against synthetic data.

## Risk disclaimer

Daily equity direction is a very low signal-to-noise problem; a good-looking
backtest is not evidence of future profit. This code defaults to paper
trading for a reason — do not point it at a live account until you have
watched it trade paper money through different market conditions, and never
trade money you cannot afford to lose. Nothing here is financial advice.
