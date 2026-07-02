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
python -m py_compile scripts/run_desk_analysis.py
echo "Setup complete. Activate with: source trading-desk/.venv/bin/activate"
