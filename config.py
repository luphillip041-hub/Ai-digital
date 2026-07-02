"""Central configuration for the multi-strategy Alpaca trading bot.

API credentials are loaded from a .env file (see .env.example).
All strategy parameters, instrument definitions, and risk settings live here
so no magic numbers are buried inside strategy code.
"""

import os

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Alpaca credentials / endpoints
# ---------------------------------------------------------------------------
ALPACA_API_KEY = os.getenv("ALPACA_API_KEY", "")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "")
ALPACA_BASE_URL = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
# "iex" is the free equities data feed; "sip" requires a paid subscription.
ALPACA_DATA_FEED = os.getenv("ALPACA_DATA_FEED", "iex")

# ---------------------------------------------------------------------------
# Notifications (all optional — every configured channel gets every message)
# ---------------------------------------------------------------------------
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
NOTIFY_EMAIL = os.getenv("NOTIFY_EMAIL", "")

# ---------------------------------------------------------------------------
# Risk management
# ---------------------------------------------------------------------------
ATR_PERIOD = 14
# A 1-ATR adverse move must equal exactly this fraction of account equity.
RISK_PER_TRADE = 0.01
# Hard stop: every trade is stopped out at a loss of 1% of equity. Because
# position size is (equity * RISK_PER_TRADE) / ATR, this is a 1-ATR move.
HARD_STOP_EQUITY_FRACTION = 0.01

# Correlation filter: if every symbol in "requires_long" is already long,
# block new long entries on "blocked_symbol" (avoids stacking risk-on bets).
CORRELATION_FILTER = {
    "blocked_symbol": "BTC/USD",
    "requires_long": ["SPY", "QQQ"],
}

# Minimum notional (USD) for a crypto order — Alpaca rejects dust orders.
CRYPTO_MIN_NOTIONAL = 10.0

# ---------------------------------------------------------------------------
# Instruments and per-strategy parameters
# ---------------------------------------------------------------------------
# asset_class:  "equity" trades only during market hours; "crypto" trades 24/7.
# timeframe_minutes: the candle size the strategy evaluates on.
# trail_atr_mult: trailing-stop distance in ATR multiples (None = no trail,
#                 only the hard stop and the strategy's own exit rule apply).
INSTRUMENTS = {
    "SPY": {
        "asset_class": "equity",
        "data_symbol": "SPY",
        "trade_symbol": "SPY",
        "strategy": "mean_reversion",
        "timeframe_minutes": 15,
        "shortable": True,
        "trail_atr_mult": None,
        # band_mult raised from the original 1.5 after the 6-month backtest:
        # tighter bands churned 189 trades with PF 0.58; 2.5 cut the trade
        # count ~70% and halved max drawdown (see bot/backtest.py).
        "params": {"sma_period": 20, "band_mult": 2.5},
    },
    "QQQ": {
        "asset_class": "equity",
        "data_symbol": "QQQ",
        "trade_symbol": "QQQ",
        "strategy": "mean_reversion",
        "timeframe_minutes": 15,
        "shortable": True,
        "trail_atr_mult": None,
        # band_mult raised from the original 1.8 after the 6-month backtest
        # (same churn/slippage rationale as SPY).
        "params": {"sma_period": 20, "band_mult": 2.5},
    },
    "BTC/USD": {
        "asset_class": "crypto",
        "data_symbol": "BTC/USD",
        "trade_symbol": "BTC/USD",
        "strategy": "momentum_breakout",
        "timeframe_minutes": 60,
        # Alpaca does not support shorting crypto: a "short" signal exits longs.
        "shortable": False,
        "trail_atr_mult": 2.0,
        "params": {"lookback": 20, "volume_mult": 1.5},
    },
    "GLD": {
        "asset_class": "equity",
        "data_symbol": "GLD",
        "trade_symbol": "GLD",
        "strategy": "trend_following",
        "timeframe_minutes": 240,
        "shortable": True,
        "trail_atr_mult": 3.0,
        "params": {"fast_ema": 50, "slow_ema": 200},
    },
    "USO": {
        "asset_class": "equity",
        "data_symbol": "USO",
        "trade_symbol": "USO",
        "strategy": "trend_following",
        "timeframe_minutes": 240,
        "shortable": True,
        "trail_atr_mult": 3.0,
        "params": {"fast_ema": 50, "slow_ema": 200},
    },
}

# ---------------------------------------------------------------------------
# Runtime / logging
# ---------------------------------------------------------------------------
# How often the main loop wakes up to check stops and bar boundaries (seconds).
POLL_INTERVAL_SECONDS = 60

TRADES_CSV = "trades.csv"
DAILY_PNL_CSV = "daily_pnl.csv"
STATE_FILE = "bot_state.json"
LOG_FILE = "bot.log"

# API retry policy for transient failures (disconnects, timeouts, 5xx).
API_MAX_RETRIES = 4
API_RETRY_BASE_DELAY = 2  # seconds; doubles each retry: 2, 4, 8, 16

# ---------------------------------------------------------------------------
# Backtest baseline (6-month run 2025-12-30 -> 2026-07-01, 2.5σ bands,
# corrected stop). bot/reports.py compares live performance against these
# to answer "is the bot on track with backtest expectations".
# ---------------------------------------------------------------------------
BACKTEST_BASELINE = {
    "SPY": {"win_rate": 0.52, "profit_factor": 0.69, "trades_per_week": 2.2},
    "QQQ": {"win_rate": 0.45, "profit_factor": 0.66, "trades_per_week": 2.4},
    "BTC/USD": {"win_rate": 0.14, "profit_factor": 0.21, "trades_per_week": 1.9},
    "GLD": {"win_rate": 0.33, "profit_factor": 0.37, "trades_per_week": 0.1},
    "USO": {"win_rate": 0.00, "profit_factor": 0.00, "trades_per_week": 0.1},
}
