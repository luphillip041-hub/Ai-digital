# Options Scanner Playbook

This scanner turns the screenshot-style signal card into a repeatable desk process:

```text
setup → chart levels → option chain → liquidity/risk filter → management plan → Discord signal
```

It is research/paper-only. It does **not** stage or execute broker orders.

## What the boys care about

Most Discord options traders need the signal in one clean card:

- setup name: bullish reversal, bearish reversal, breakout, trend pullback
- symbol, entry, target, stop
- suggested contract: call/put, expiry, strike, bid/ask, volume, OI
- why the setup exists
- how to manage it after entry

The scanner outputs exactly that in `runs/options_signal_example.md` and full JSON in `runs/options_signals_latest.json`.

## Signal stack

### 1. Underlying chart review

The scanner checks:

| Layer | Why it matters |
|---|---|
| 20DMA / 50DMA | trend direction and reclaim/loss levels |
| RSI(14) | avoids blindly buying exhausted names |
| ATR(14) | sizes target/stop and filters untradeable volatility |
| 20-day support/resistance | objective invalidation and target context |
| Relative volume | confirms break/reversal participation |
| 5D / 20D momentum | separates real trend from one candle noise |
| Candle behavior | bullish/bearish engulfing, wick reversal, reclaim/loss |

Recognized setups:

- **Bullish Reversal** — reclaim, engulfing, or hammer-like lower wick after weakness.
- **Bearish Reversal** — bearish engulfing, 20DMA loss, or bearish MA stack.
- **Trend Pullback** — price still above trend, RSI reset, near 20DMA.
- **Breakout Continuation** — near 20-day resistance with volume confirmation.

### 2. Options contract selection

Default chain window: **7–45 DTE**.

The scanner chooses a contract by ranking:

- strike near the underlying technical target
- approximate delta around 0.30–0.55 when IV is available
- bid/ask spread quality
- contract volume
- open interest
- premium sanity
- DTE near ~21 days by default

The current implementation uses `yfinance`, so data can be delayed. Upgrade path:

1. Tradier option quotes/snapshots + Greeks
2. Alpaca option snapshots/contracts
3. OPRA-grade paid feed later if needed

### 3. Strategy taxonomy

The first scanner version picks simple directional contracts because that is easiest for a group Discord card. The strategy layer should expand into:

| View | Beginner contract | Better defined-risk version |
|---|---|---|
| Bullish | Call | Bull call debit spread |
| Bearish | Put | Bear put debit spread |
| Neutral / pin | ATM butterfly | Iron butterfly if collateral allows |
| High IV event | Butterfly | Broken-wing fly / credit spread |
| Direction + low IV | Long call/put | Debit spread |
| Direction + high IV | Debit spread | Credit spread / fly |
| Hedge | Put | Collar / put spread |

Capital rule: filter on **capital required**, not just max loss. Credit spreads, butterflies, condors, and collars can require collateral beyond the displayed debit/max loss.

### 4. Risk and management rules

Default management baked into every signal:

- Trim 50% at +35% to +50% contract gain.
- Stop at -25% to -30% premium loss.
- Respect underlying invalidation even if the option has not hit stop yet.
- Avoid holding weak contracts inside 3 DTE.
- Never size a long option as if the stop is guaranteed; gaps can skip stops.
- Use 0.5%–1.0% account risk per idea; small accounts should use one contract or defined-risk spreads.

### 5. Quality flags

Signals can include flags:

- `wide_spread` / `very_wide_spread`
- `low_contract_volume`
- `low_open_interest`
- `premium_expensive`
- `lottery_premium`
- `rsi_overheated`
- `weak_volume`
- `atr_too_wide`

A pretty setup with bad option liquidity is not a good Discord signal.

## CLI

```bash
cd /root/flip/projects/trading-desk/Ai-digital/trading-desk
python scripts/options_signal_scanner.py \
  --symbols SPY,QQQ,NVDA,TSLA,AMD,AAPL,MSFT,COIN,MSTR \
  --max-signals 3
```

Outputs:

- `runs/options_signals_latest.json`
- `runs/options_signal_example.md`

## Discord command

```text
!optionscan SPY,QQQ,NVDA,TSLA,AMD,AAPL
```

The bot replies with the top signal card and saves the full scan JSON.

## Example card format

```text
🟢 Bullish Reversal — AAPL
Score 77.5 | Direction long | R/R 1.59

Symbol AAPL  Entry $211.00  Position long
Target $217.40  Stoploss $206.95  Potential Profit $6.40

Suggested Contract
> Type: CALL
> Expiration: 2026-07-17
> Strike: $215
> Bid/Ask: $2.16 / $2.27
> Vol/OI: 1,136 / 1,633
> IV/Δ: 31.2% / +0.41
> BE: $217.27 | Est cost: $227/contract

Why: bullish_engulfing_candle, reclaimed_20dma, volume_confirmation
Management: +35-50% trim, -25-30% stop, respect underlying stop.
```

## Next build after this

1. Add spread construction: verticals, butterflies, condors.
2. Add IV Rank/IV Percentile history.
3. Add earnings/FOMC/calendar filter.
4. Add exact Tradier/Alpaca Greeks instead of Black-Scholes approximation.
5. Add dashboard tiles for signal lifecycle: first alert, current value, MFE/MAE, missed runner %, outcome.
