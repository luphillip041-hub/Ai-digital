#!/usr/bin/env bash
set -euo pipefail

# Install/run OpenAlice alongside Flip's trading-desk without vendoring AGPL code
# into Ai-digital. OpenAlice lives as a sibling checkout and keeps state under
# trading-desk/.openalice by default.

DESK_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE_ROOT="$(cd "$DESK_ROOT/../.." && pwd)"
OPENALICE_DIR="${OPENALICE_DIR:-$BASE_ROOT/OpenAlice-upstream}"
export OPENALICE_HOME="${OPENALICE_HOME:-$DESK_ROOT/.openalice}"

mkdir -p "$OPENALICE_HOME"

if ! command -v node >/dev/null 2>&1; then
  echo "node is required; install Node.js 22+ first" >&2
  exit 1
fi

NODE_MAJOR="$(node -p "process.versions.node.split('.')[0]")"
if [ "$NODE_MAJOR" -lt 22 ]; then
  echo "OpenAlice requires Node.js 22+; found $(node -v)" >&2
  exit 1
fi

if ! command -v pnpm >/dev/null 2>&1; then
  echo "pnpm not found; installing pnpm globally with npm"
  npm install -g pnpm
fi

if [ ! -d "$OPENALICE_DIR/.git" ]; then
  git clone https://github.com/TraderAlice/OpenAlice.git "$OPENALICE_DIR"
else
  git -C "$OPENALICE_DIR" pull --ff-only
fi

cd "$OPENALICE_DIR"

# Skip Electron desktop shell on server/agent boxes; browser UI still works.
pnpm install --filter='!@traderalice/desktop'

cat <<EOF

OpenAlice is installed.

Start it with:
  cd "$OPENALICE_DIR"
  OPENALICE_HOME="$OPENALICE_HOME" pnpm dev

Then open the UI URL printed by OpenAlice, usually:
  http://127.0.0.1:5173

Flip desk bridge prompt:
  cd "$DESK_ROOT"
  python scripts/openalice_bridge.py --symbols SPY,QQQ,NVDA,TSLA --max-finalists 3

If you create an OpenAlice workspace and want a headless dispatch:
  OPENALICE_WORKSPACE_ID=<workspace-id> python scripts/openalice_bridge.py --agent shell
EOF
