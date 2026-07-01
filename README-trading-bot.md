# Multi-Strategy Alpaca Trading Bot

A Python bot that trades 5 instruments simultaneously on Alpaca Markets with
three strategy modules and unified ATR-based risk management.

> **Disclaimer:** For educational use. Trading involves substantial risk of
> loss. Run against Alpaca **paper trading** first (the default endpoint).

## Instruments & Strategies

| Instrument | Strategy | Timeframe | Rules |
|---|---|---|---|
| SPY | Mean Reversion | 15 min | Long < SMA20 − 1.5σ, short > SMA20 + 1.5σ, exit at SMA |
| QQQ | Mean Reversion | 15 min | Same, with 1.8σ bands |
| BTC/USD | Momentum Breakout | 1 hour | Break of 20-bar high/low with volume ≥ 1.5× 20-bar avg; 2×ATR trail |
| GLD | Trend Following | 4 hour | 50/200 EMA cross; 3×ATR trail |
| USO | Trend Following | 4 hour | 50/200 EMA cross; 3×ATR trail |

## Risk management (all strategies)

- **ATR sizing:** 14-period ATR; qty = (1% of equity) / ATR, so a 1-ATR
  adverse move always costs exactly 1% of equity — quiet instruments get
  bigger positions, volatile ones smaller.
- **Hard stop:** every trade is cut at a 1%-of-equity loss (a 1-ATR move,
  given the sizing rule). No exceptions.
- **Trailing stops:** 2×ATR on BTC/USD, 3×ATR on GLD/USO, ratcheted each
  completed bar; only ever tighten.
- **Correlation filter:** if SPY **and** QQQ are both long, new BTC/USD
  longs are blocked (no stacked risk-on exposure).
- Alpaca does not support shorting crypto, so BTC/USD "short" signals act
  as exit-long only. Equity shorts use whole-share quantities.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env        # then edit .env with your Alpaca keys
python -m bot.main          # run from the repository root
```

## Files

```
bot/
  strategies/
    base.py               # Strategy interface + Signal type
    mean_reversion.py     # Strategy 1 (SPY, QQQ)
    momentum_breakout.py  # Strategy 2 (BTC/USD)
    trend_following.py    # Strategy 3 (GLD, USO)
  risk_manager.py         # sizing, hard/trailing stops, correlation filter
  portfolio.py            # positions, trades.csv, daily_pnl.csv, state file
  broker.py               # Alpaca wrapper: retries, bars, orders
  indicators.py           # SMA / EMA / σ / ATR / rolling high-low
  main.py                 # event loop, scheduling, market-hours handling
config.py                 # all parameters in one place
.env                      # your API keys (never committed)
```

Runtime artifacts (gitignored): `trades.csv` (one row per closed trade:
timestamp, instrument, direction, entry, exit, P&L, size), `daily_pnl.csv`
(date, realized P&L, equity, written at UTC midnight), `bot_state.json`
(open positions — survives restarts and is reconciled against the broker on
startup), `bot.log`.

## Behavior notes

- The loop wakes every 60 s: it checks stops on open positions every wake,
  and evaluates each strategy exactly once per completed candle of its
  timeframe (15 m / 1 h / 4 h).
- Equities are only touched while the market is open (`GET /clock`);
  BTC/USD runs 24/7.
- Transient API failures retry with exponential backoff (2 s → 16 s); any
  per-instrument error is logged and skipped so the loop never dies.
- Trend following needs ~600 four-hour bars of history for a stable 200 EMA;
  until enough history is fetched it logs "waiting" and does nothing.
