# Vibe-Trading Integration Plan

Vibe-Trading is useful as an **analyst lab**, not as the trade desk's source of truth.

This desk integrates it through `scripts/vibe_research_bridge.py` without vendoring HKUDS/Vibe-Trading code.

## Rule

```text
Vibe-Trading = research/backtest/shadow-account sidecar
Flip Trade Desk = scanner/risk/run-card/Discord source of truth
```

## Current bridge

```bash
python scripts/vibe_research_bridge.py TSLA --refresh
```

Outputs:

- normalized JSON research packet
- Markdown report
- desk scanner context
- matched options signal when available
- optional Vibe-Trading CLI output tail when `--run-vibe` is enabled

## Discord

```text
!vibe TSLA
```

This builds a research packet from desk scanner context. It does **not** place orders and does **not** bypass desk risk rules.

## UI

Open the Streamlit dashboard and use:

```text
Research Lab
```

The view can build a packet, show matched option context, and optionally call the external `vibe-trading` CLI if installed.

## Optional sidecar install

```bash
pip install vibe-trading-ai
vibe-trading --help
```

Set in `.env` if the executable name/path is custom:

```env
VIBE_TRADING_BIN=vibe-trading
FLIP_DESK_VIBE_TIMEOUT_SECONDS=900
```

If Vibe-Trading is not installed, the bridge still works as a deterministic desk research packet.

## Next upgrades

1. Shadow Account import for Y4Y trade logs.
2. Sidecar API mode against `vibe-trading serve` instead of CLI-only.
3. Attach research packet to every scanner/option signal as a run card.
4. Backtest template commands: `!backtest TSLA rsi`, `!shadow flip`.
5. Never enable live execution through Vibe-Trading; broker execution remains staged/human-confirmed only.
