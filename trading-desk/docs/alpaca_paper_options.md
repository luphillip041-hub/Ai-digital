# Alpaca PAPER Options Desk

This integration keeps Flip's Alpaca account isolated from every other trading bot/account on the VPS.

## Safety model

```text
scanner → option signal → guarded Alpaca PAPER dry-run → optional paper submit → EOD report
```

Defaults:

- paper endpoint only: `https://paper-api.alpaca.markets`
- dry-run by default
- limit orders only
- single-leg long options only for first rollout
- max debit cap
- market-open check before submit
- account/options-level/buying-power checks
- no real-money execution path

## Env

Put keys only in:

```text
/root/flip/projects/trading-desk/Ai-digital/trading-desk/.env
```

Do **not** paste keys into Discord once this is deployed.

```env
APCA_API_KEY_ID=...
APCA_API_SECRET_KEY=...
ALPACA_PAPER_BASE_URL=https://paper-api.alpaca.markets
ALPACA_DATA_BASE_URL=https://data.alpaca.markets
ALPACA_PAPER_MAX_ORDER_DEBIT=250
ALPACA_PAPER_OPTION_QTY=1
FLIP_DESK_PAPER_OPTIONS_AUTO_SUBMIT=false
```

## Commands

Dry-run one full paper-options pass:

```bash
python scripts/paper_options_daily.py run-iteration --symbols SPY,QQQ,NVDA,TSLA,SMH,AAPL,MSFT
```

Submit to Alpaca paper only after the dry-run proves clean:

```bash
python scripts/paper_options_daily.py run-iteration --symbols SPY,QQQ,NVDA,TSLA --submit
```

Build EOD report:

```bash
python scripts/paper_options_daily.py eod-report
```

Manual adapter checks:

```bash
python scripts/alpaca_paper_options.py account
python scripts/alpaca_paper_options.py clock
python scripts/alpaca_paper_options.py positions
python scripts/alpaca_paper_options.py orders
python scripts/alpaca_paper_options.py fills
```

## Discord

```text
!paperopts
!paperopts SPY,QQQ,NVDA,TSLA
!eod
```

`!paperopts` is dry-run unless `FLIP_DESK_PAPER_OPTIONS_AUTO_SUBMIT=true` is explicitly set in `.env`.

## Scheduler examples

Market-hours dry-run every 30 minutes:

```bash
*/30 9-15 * * 1-5 cd /root/flip/projects/trading-desk/Ai-digital/trading-desk && /usr/local/bin/python scripts/paper_options_daily.py run-iteration >> runs/paper_options_cron.log 2>&1
```

EOD report at 4:10 PM ET:

```bash
10 16 * * 1-5 cd /root/flip/projects/trading-desk/Ai-digital/trading-desk && /usr/local/bin/python scripts/paper_options_daily.py eod-report >> runs/paper_options_eod_cron.log 2>&1
```

Use Hermes cron or system cron depending on where you want the final message delivered.
