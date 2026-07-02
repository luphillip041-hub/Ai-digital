#!/usr/bin/env bash
# Manage the trading bot as a background process.
#
#   ./run.sh start    launch in the background (survives terminal close)
#   ./run.sh stop     graceful shutdown (state is saved on exit)
#   ./run.sh status   is it running? plus open positions and today's trades
#   ./run.sh log      follow the live log
set -euo pipefail
cd "$(dirname "$0")"
PIDFILE=bot.pid

is_running() {
    [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null
}

case "${1:-}" in
    start)
        if is_running; then
            echo "Bot already running (pid $(cat "$PIDFILE"))"
            exit 0
        fi
        # shellcheck disable=SC1091
        source .venv/bin/activate
        nohup python -m bot.main >> bot.out 2>&1 &
        echo $! > "$PIDFILE"
        echo "Bot started (pid $(cat "$PIDFILE")). Follow with: ./run.sh log"
        ;;
    stop)
        if ! is_running; then
            echo "Bot is not running"
            exit 0
        fi
        kill -INT "$(cat "$PIDFILE")"   # SIGINT -> graceful, saves state
        sleep 2
        if is_running; then kill "$(cat "$PIDFILE")"; fi
        rm -f "$PIDFILE"
        echo "Bot stopped"
        ;;
    status)
        if is_running; then
            echo "RUNNING (pid $(cat "$PIDFILE"))"
        else
            echo "NOT RUNNING"
        fi
        echo "--- open positions (bot_state.json):"
        [ -f bot_state.json ] && cat bot_state.json || echo "  none"
        echo "--- last 5 trades:"
        [ -f trades.csv ] && tail -5 trades.csv || echo "  none"
        ;;
    log)
        tail -f bot.log
        ;;
    *)
        echo "usage: $0 {start|stop|status|log}"
        exit 1
        ;;
esac
