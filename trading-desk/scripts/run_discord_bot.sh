#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

if [ ! -f .env ]; then
  echo "Missing .env. Copy .env.example to .env and fill DISCORD_BOT_TOKEN + model keys." >&2
  exit 1
fi

mkdir -p runs .cache memory
exec python -u bot/discord_bot.py
