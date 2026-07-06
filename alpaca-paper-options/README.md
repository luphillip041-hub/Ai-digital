# Flip Alpaca PAPER Options

Standalone paper-options research/trading service. This is intentionally separate from `trading-desk/`.

## What it does

```text
broad market scan → options signal scan → guarded Alpaca PAPER dry-run/submit → EOD report
```

Default behavior is **dry-run only**. Paper submit requires either:

```bash
python scripts/paper_options_daily.py run-iteration --submit
```

or:

```env
ALPACA_PAPER_OPTIONS_AUTO_SUBMIT=true
```

## Safety guardrails

- uses only this directory's `.env`
- paper endpoint only: `https://paper-api.alpaca.markets`
- limit orders only
- no real-money execution path
- market-open check before submit
- account active / options level / buying-power checks
- max debit cap
- option bid/ask and spread checks
- generated JSON + Markdown audit trail in `runs/`

## Setup

```bash
cd alpaca-paper-options
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# fill APCA_API_KEY_ID and APCA_API_SECRET_KEY for the paper account
```

## Run

```bash
# Full dry-run pass
python scripts/paper_options_daily.py run-iteration --symbols SPY,QQQ,NVDA,TSLA,SMH,AAPL

# EOD report
python scripts/paper_options_daily.py eod-report

# Account checks
python scripts/alpaca_paper_options.py account
python scripts/alpaca_paper_options.py positions
python scripts/alpaca_paper_options.py orders
python scripts/alpaca_paper_options.py fills
```

## Docker

```bash
cd alpaca-paper-options
docker compose config
docker compose build
```

This compose file is intentionally one-shot/report oriented. Use cron/systemd/Hermes cron for scheduling.

## Scheduling

Market-hours dry-run every 30 minutes, 10:00 AM–3:30 PM ET during EDT:

```cron
*/30 14-19 * * 1-5 cd /root/flip/projects/trading-desk/Ai-digital/alpaca-paper-options && python3 scripts/paper_options_daily.py run-iteration >> runs/cron.log 2>&1
```

EOD report at 4:10 PM ET during EDT:

```cron
10 20 * * 1-5 cd /root/flip/projects/trading-desk/Ai-digital/alpaca-paper-options && python3 scripts/paper_options_daily.py eod-report >> runs/eod_cron.log 2>&1
```

On this host/scheduler, current cron is UTC+2, so Hermes cron uses:

```text
intraday: */30 16-21 * * 1-5
EOD:      10 22 * * 1-5
```

## Files

```text
scripts/scan_watchlist.py          # zero-LLM underlying scanner
scripts/options_signal_scanner.py  # zero-LLM options signal scanner
scripts/alpaca_paper_options.py    # Alpaca PAPER guard/order adapter
scripts/paper_options_daily.py     # daily cycle + EOD reports
runs/                              # JSON/Markdown artifacts
```
