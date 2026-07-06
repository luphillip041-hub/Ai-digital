#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python3 scripts/paper_options_daily.py run-iteration "$@"
