# Ai-digital

This repo contains the original Next.js app under `app/`, the Alpaca multi-strategy bot under `bot/`, and an isolated trading-research desk under `trading-desk/`.

## Projects

| Folder | Purpose |
|---|---|
| `app/` | Existing Next.js AI revenue webapp. |
| `bot/` | Alpaca multi-strategy paper-trading bot. |
| `trading-desk/` | Flip's low-burn research desk with a native multi-agent engine (`desk_agents/`). |

## Trading desk quick start

```bash
cd trading-desk
bash scripts/setup.sh
cp .env.example .env
# add API keys
source .venv/bin/activate
python scripts/run_desk_analysis.py AAPL --date 2026-07-01

# or try the whole pipeline with zero keys/network:
python scripts/run_desk_analysis.py AAPL --model-profile offline
```

See `trading-desk/README.md` for the full operating guide, sub-agent architecture, cost controls, and Discord bot setup.
