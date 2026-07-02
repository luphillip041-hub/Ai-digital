# Ai-digital

This repo currently contains the original Next.js app under `app/` plus a new isolated trading desk under `trading-desk/`.

## Projects

| Folder | Purpose |
|---|---|
| `app/` | Existing Next.js AI revenue webapp. |
| `trading-desk/` | Flip's low-burn TradingAgents-based research desk. |

## Trading desk quick start

```bash
cd trading-desk
bash scripts/setup.sh
cp .env.example .env
# add API keys
source .venv/bin/activate
python scripts/run_desk_analysis.py AAPL --date 2026-07-01
```

See `trading-desk/README.md` for the full operating guide, API key list, cost controls, and GitHub push instructions.
