#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env — fill API keys before running."
fi
python -m py_compile scripts/run_desk_analysis.py scripts/scan_watchlist.py scripts/options_signal_scanner.py scripts/vibe_research_bridge.py scripts/openalice_bridge.py bot/discord_bot.py ui/dashboard.py
echo "Setup complete. Activate with: source trading-desk/.venv/bin/activate"
echo "Run Discord bot locally with: bash scripts/run_discord_bot.sh"
echo "Or 24/7 via Docker: docker compose up -d --build"
