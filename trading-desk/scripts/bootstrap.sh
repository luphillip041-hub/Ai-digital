#!/usr/bin/env bash
# One-command install + first live run for Flip's trading desk.
#
#   curl -fsSL https://raw.githubusercontent.com/luphillip041-hub/Ai-digital/claude/repo-review-zw3n26/trading-desk/scripts/bootstrap.sh \
#     | DEEPSEEK_API_KEY=... ALPACA_API_KEY=... ALPACA_SECRET_KEY=... bash -s -- AAPL
#
# Pass keys as env vars (they land only in the gitignored .env). The
# optional argument is the ticker for the first analysis (default AAPL).
# Works on a stock Mac (Python 3.9 from Xcode Command Line Tools) and Linux.
set -euo pipefail

REPO_URL="https://github.com/luphillip041-hub/Ai-digital.git"
BRANCH="claude/repo-review-zw3n26"
DIR="${FLIP_DESK_HOME:-$HOME/flip-trading-desk}"
TICKER="${1:-AAPL}"

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }

command -v git >/dev/null 2>&1 || {
  echo "git is required. On macOS run:  xcode-select --install  (then re-run this command)"; exit 1; }
command -v python3 >/dev/null 2>&1 || {
  echo "python3 is required. On macOS run:  xcode-select --install  (then re-run this command)"; exit 1; }

PYVER=$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' || {
  echo "Python $PYVER found; 3.9+ required. On macOS: brew install python3"; exit 1; }

say "① Fetching the desk (branch $BRANCH) → $DIR"
if [ -d "$DIR/.git" ]; then
  git -C "$DIR" fetch origin "$BRANCH"
  git -C "$DIR" checkout "$BRANCH"
  git -C "$DIR" pull --ff-only origin "$BRANCH"
else
  git clone --depth 1 -b "$BRANCH" "$REPO_URL" "$DIR"
fi
cd "$DIR/trading-desk"

say "② Python env (python $PYVER)"
python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --quiet --upgrade pip
python -m pip install --quiet python-dotenv certifi
# Optional extras: yahoo fallback + discord bot. The desk runs Alpaca-only fine.
python -m pip install --quiet yfinance || echo "  (yfinance skipped — Yahoo fallback off, Alpaca covers stocks/ETFs)"
python -m pip install --quiet "discord.py>=2.4.0" || echo "  (discord.py skipped — bot optional)"
# Stock macOS python sometimes lacks root certs for urllib; point it at certifi.
SSL_CERT_FILE="$(python -c 'import certifi; print(certifi.where())')"
export SSL_CERT_FILE

say "③ Writing keys to gitignored .env"
[ -f .env ] || cp .env.example .env
python - <<'PYEOF'
import os, re, pathlib
env = pathlib.Path(".env")
text = env.read_text()
for var in ("DEEPSEEK_API_KEY", "ALPACA_API_KEY", "ALPACA_SECRET_KEY", "DISCORD_BOT_TOKEN"):
    val = os.environ.get(var)
    if not val:
        continue
    line = f"{var}={val}"
    if re.search(rf"^{var}=", text, flags=re.M):
        text = re.sub(rf"^{var}=.*$", line, text, flags=re.M)
    else:
        text += "\n" + line
env.write_text(text)
print("  keys set:", ", ".join(v for v in ("DEEPSEEK_API_KEY","ALPACA_API_KEY","ALPACA_SECRET_KEY","DISCORD_BOT_TOKEN") if os.environ.get(v)) or "none (edit .env manually)")
PYEOF

say "④ Zero-LLM watchlist scan (free)"
python scripts/scan_watchlist.py --max-finalists 3 | tail -5 || true

say "⑤ Live multi-agent analysis: $TICKER (8 LLM calls)"
python scripts/run_desk_analysis.py "$TICKER"

say "Done. Next runs:"
echo "  cd $DIR/trading-desk && source .venv/bin/activate"
echo "  python scripts/scan_watchlist.py            # free"
echo "  python scripts/run_desk_analysis.py TSLA    # 8 calls"
