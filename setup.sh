#!/usr/bin/env bash
# One-shot setup: virtualenv, dependencies, and .env creation.
#
# Usage:
#   ALPACA_API_KEY=PK... ALPACA_SECRET_KEY=... ./setup.sh
# or run bare and it will prompt for the keys:
#   ./setup.sh
set -euo pipefail
cd "$(dirname "$0")"

echo "==> Creating virtualenv (.venv)"
python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --quiet --upgrade pip

echo "==> Installing dependencies"
# alpaca-trade-api pins msgpack==1.0.3 which won't build on Python 3.11+,
# so install its deps unpinned first, then the library without deps.
pip install --quiet msgpack aiohttp websockets websocket-client PyYAML \
    deprecation requests urllib3 pandas numpy python-dotenv
pip install --quiet --no-deps alpaca-trade-api

if [ -f .env ]; then
    echo "==> .env already exists — leaving it untouched"
else
    if [ -z "${ALPACA_API_KEY:-}" ]; then
        read -r -p "Alpaca API key ID: " ALPACA_API_KEY
    fi
    if [ -z "${ALPACA_SECRET_KEY:-}" ]; then
        read -r -s -p "Alpaca secret key: " ALPACA_SECRET_KEY; echo
    fi
    cat > .env <<EOF
ALPACA_API_KEY=${ALPACA_API_KEY}
ALPACA_SECRET_KEY=${ALPACA_SECRET_KEY}
ALPACA_BASE_URL=${ALPACA_BASE_URL:-https://paper-api.alpaca.markets}
ALPACA_DATA_FEED=${ALPACA_DATA_FEED:-iex}
DISCORD_WEBHOOK_URL=${DISCORD_WEBHOOK_URL:-}
EOF
    chmod 600 .env
    echo "==> Wrote .env (gitignored, mode 600)"
fi

echo "==> Verifying credentials against Alpaca"
python - <<'EOF'
import config
from bot.broker import Broker
b = Broker()
print(f"    OK — account equity: ${b.get_equity():,.2f} "
      f"({config.ALPACA_BASE_URL})")
EOF

echo
echo "Setup complete. Start the bot with:  ./run.sh start"
